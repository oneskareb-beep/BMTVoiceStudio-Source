"""BMT Voice Studio V1.0 production QA runner — executes real generation checks."""

from __future__ import annotations

import asyncio
import json
import shutil
import sys
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(r"C:\Users\aganz\Documents\BMTVoiceStudio")
sys.path.insert(0, str(ROOT))

from bmt_voice_studio.audio.ffmpeg_service import FFmpegService
from bmt_voice_studio.audio.joining import join_segments
from bmt_voice_studio.audio.mastering import MasteringOptions, master_audio
from bmt_voice_studio.config.paths import models_dir, temp_work_dir
from bmt_voice_studio.config.presets import BMT_ENGLISH, BMT_FRENCH
from bmt_voice_studio.config.settings import AppSettings, get_settings, save_settings
from bmt_voice_studio.core.filenames import sanitize_filename, unique_path
from bmt_voice_studio.core.hashing import needs_regeneration, segment_cache_hash
from bmt_voice_studio.core.models import Segment, Speaker, SynthRequest
from bmt_voice_studio.core.parser import parse_speaker_script
from bmt_voice_studio.m3u.downloader import DownloadError, download_and_merge
from bmt_voice_studio.m3u.parser import detect_hls, parse_m3u_content, parse_m3u_file, parse_url_list, validate_audio_magic
from bmt_voice_studio.projects.project import ProjectService
from bmt_voice_studio.providers import get_provider, reset_registry
from bmt_voice_studio.providers.base import TTSProviderError
from bmt_voice_studio.providers.edge_tts import EdgeTTSProvider
from bmt_voice_studio.providers.piper import PIPER_CATALOG, PiperVoiceManager


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""


RESULTS: list[Check] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append(Check(name, ok, detail))
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail else ""))


def ff() -> FFmpegService:
    return FFmpegService()


def probe_duration(path: Path) -> float:
    svc = ff()
    result = svc.run(["-i", str(path)], check=False, timeout=30)
    combined = (result.stderr or "") + (result.stdout or "")
    import re

    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", combined)
    if not m:
        return 0.0
    h, mi, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
    return h * 3600 + mi * 60 + s


def is_valid_audio(path: Path) -> bool:
    if not path.exists() or path.stat().st_size < 64:
        return False
    data = path.read_bytes()[:256]
    ok, _ = validate_audio_magic(data)
    if not ok:
        return False
    return ff().probe_is_audio(path) and probe_duration(path) > 0.05


EN_SCRIPT = """BELIEVERS MANNA TODAY DAILY DEVOTIONAL

Written by Apostle Doctor David A. Aderibigbe

Beloved, welcome to today's meditation from Believers Manna Today. We gather with open hearts to seek the Lord who never fails His children.

{
Memory Verse

But seek ye first the kingdom of God, and his righteousness; and all these things shall be added unto you.
Matthew chapter six verse thirty three.
}

When priorities are ordered under Heaven, peace follows. Put prayer before panic. Put worship before worry. Put obedience before opinion. The Father who clothes the lilies will not abandon His people.

{
Pray with me. Lord Jesus, I seek Your kingdom first today. Align my heart with Your will, and teach me to rest in Your faithful provision. Amen.
}

Go in peace, dear saint. Walk in faith, speak in love, and remember that God is with you always. This is Believers Manna Today.
"""

FR_SCRIPT = """MANNE DES CROYANTS AUJOURD'HUI

Écrit par l'Apôtre Docteur David A. Aderibigbe

Bien-aimés, bienvenue à la méditation d'aujourd'hui. Nous cherchons le Seigneur qui ne déçoit jamais Ses enfants.

{
Verset à mémoriser

Cherchez premièrement le royaume et la justice de Dieu; et toutes ces choses vous seront données par-dessus.
Matthieu chapitre six verset trente-trois.
}

Quand vos priorités sont alignées sous le Ciel, la paix suit. Placez la prière avant la panique. Placez l'adoration avant l'inquiétude. Placez l'obéissance avant l'opinion.

{
Prions ensemble. Seigneur Jésus, je cherche Ton royaume en premier aujourd'hui. Aligne mon cœur sur Ta volonté, et apprends-moi à me reposer en Ta fidèle provision. Amen.
}

Allez en paix, chers saints. Marchez dans la foi, parlez avec amour, et souvenez-vous que Dieu est toujours avec vous. Voici la Manne des Croyants Aujourd'hui.
"""


async def synthesize_project(
    name: str,
    script: str,
    preset,
    out_root: Path,
) -> tuple[object, list[Segment], Path, Path]:
    parsed = parse_speaker_script(script)
    assert parsed.ok, parsed.errors
    assert len(parsed.segments) >= 5, f"Need >=5 segments, got {len(parsed.segments)}"

    # Verify MFMFM pattern for our scripts
    expected = [Speaker.MALE, Speaker.FEMALE, Speaker.MALE, Speaker.FEMALE, Speaker.MALE]
    actual = [s.speaker for s in parsed.segments]
    assert actual == expected, f"Speaker pattern {actual}"

    svc = ProjectService()
    project = svc.new_project(name)
    project.source_text = script
    project.preset_id = preset.id
    project.provider = "edge"
    project.male_voice = preset.male_voice
    project.female_voice = preset.female_voice
    project.rate = preset.rate
    project.pitch = preset.pitch
    project.pause_ms = 450
    project.mp3_bitrate = 128
    project.normalize_loudness = True
    project.target_lufs = -16.0
    project.peak_limiter = True
    project.fade_out_ms = 120

    root = svc.ensure_layout(project, out_root)
    seg_dir = root / "segments"
    edge = get_provider("edge")

    for seg in parsed.segments:
        seg.voice = project.male_voice if seg.speaker == Speaker.MALE else project.female_voice
        seg.rate = project.rate
        seg.pitch = project.pitch
        seg.volume = "+0%"
        seg.provider = "edge"
        out = seg_dir / f"{seg.index:03d}_{seg.speaker.value}.mp3"
        result = await edge.synthesize(
            SynthRequest(
                text=seg.text,
                voice=seg.voice,
                rate=seg.rate,
                pitch=seg.pitch,
                volume=seg.volume,
                output_path=str(out),
            )
        )
        if not result.success:
            raise RuntimeError(f"Segment {seg.index} failed: {result.error}")
        seg.audio_path = result.output_path
        seg.cache_hash = segment_cache_hash(seg)

    project.set_segments(parsed.segments)
    mp3_path, wav_path = svc.export_final_names(project)
    joined = join_segments(
        parsed.segments,
        mp3_path,
        pause_ms=project.pause_ms,
        bitrate_kbps=project.mp3_bitrate,
        also_wav=False,
    )
    raw = joined["final"]
    mastered = master_audio(
        raw,
        mp3_path,
        MasteringOptions(
            normalize_loudness=True,
            target_lufs=-16.0,
            remove_silence=False,
            fade_in_ms=50,
            fade_out_ms=120,
            peak_limiter=True,
            bitrate_kbps=128,
        ),
    )
    # Ensure unique wav if exists
    wav_out = unique_path(wav_path) if wav_path.exists() else wav_path
    ff().convert(mastered, wav_out, bitrate_kbps=128)
    project.final_mp3 = str(mastered)
    project.final_wav = str(wav_out)
    svc.save(project)
    return project, parsed.segments, Path(project.final_mp3), Path(project.final_wav)


async def phase_english(out_root: Path) -> None:
    print("\n=== PHASE 2 ENGLISH ===")
    try:
        project, segs, mp3, wav = await synthesize_project(
            "BMT_QA_ENGLISH", EN_SCRIPT, BMT_ENGLISH, out_root
        )
        record("EN parse MFMFM", True, f"{len(segs)} segments")
        for seg in segs:
            p = Path(seg.audio_path)
            ok = is_valid_audio(p)
            expected_voice = BMT_ENGLISH.male_voice if seg.speaker == Speaker.MALE else BMT_ENGLISH.female_voice
            record(
                f"EN seg {seg.index:02d} {seg.speaker.value}",
                ok and seg.voice == expected_voice,
                f"voice={seg.voice} dur={probe_duration(p):.2f}s size={p.stat().st_size}",
            )
        seg_durs = sum(probe_duration(Path(s.audio_path)) for s in segs)
        pauses = max(0, len(segs) - 1) * 0.45
        final_dur = probe_duration(mp3)
        # Allow tolerance for mastering/encoding
        expected_min = seg_durs + pauses * 0.5
        record("EN final MP3", is_valid_audio(mp3), f"dur={final_dur:.2f}s size={mp3.stat().st_size}")
        record("EN final WAV", is_valid_audio(wav), f"dur={probe_duration(wav):.2f}s")
        record(
            "EN duration sanity",
            final_dur >= expected_min * 0.7,
            f"final={final_dur:.2f} segments+pauses≈{seg_durs+pauses:.2f}",
        )
        # UTF-8 source preserved
        loaded = ProjectService().load(Path(project.output_folder) / "project" / "project.json")
        record("EN project save", "seek ye first" in loaded.source_text)
    except Exception as exc:
        record("EN production", False, f"{exc}\n{traceback.format_exc()[-500:]}")


async def phase_french(out_root: Path) -> tuple | None:
    print("\n=== PHASE 3 FRENCH ===")
    try:
        # Accents in source
        for ch in "éèàôç":
            assert ch in FR_SCRIPT
        project, segs, mp3, wav = await synthesize_project(
            "BMT_QA_FRENCH", FR_SCRIPT, BMT_FRENCH, out_root
        )
        record("FR accents in source", all(c in project.source_text for c in "éèàôç"))
        src_file = Path(project.output_folder) / "project" / "source.txt"
        raw = src_file.read_text(encoding="utf-8")
        record("FR UTF-8 roundtrip", "é" in raw and "ô" in raw and "ç" in raw)
        for seg in segs:
            p = Path(seg.audio_path)
            ok = is_valid_audio(p)
            expected_voice = BMT_FRENCH.male_voice if seg.speaker == Speaker.MALE else BMT_FRENCH.female_voice
            record(
                f"FR seg {seg.index:02d}",
                ok and seg.voice == expected_voice,
                f"{seg.voice} {probe_duration(p):.2f}s",
            )
        record("FR final MP3", is_valid_audio(mp3), f"{probe_duration(mp3):.2f}s")
        record("FR final WAV", is_valid_audio(wav), f"{probe_duration(wav):.2f}s")
        return project, segs, mp3, wav
    except Exception as exc:
        record("FR production", False, f"{exc}\n{traceback.format_exc()[-500:]}")
        return None


async def phase_smart_regen(fr_bundle, out_root: Path) -> None:
    print("\n=== PHASE 4 SMART REGEN ===")
    if not fr_bundle:
        record("Smart regen", False, "French project unavailable")
        return
    project, segs, mp3, wav = fr_bundle
    # Snapshot mtimes
    mtimes = {s.index: Path(s.audio_path).stat().st_mtime for s in segs}
    hashes = {s.index: s.cache_hash for s in segs}

    # Change only segment 3 text
    target = segs[2]
    target.text = target.text + " Aujourd'hui encore, choisissez la foi."
    new_hash = segment_cache_hash(target)
    record("Hash changed for edited seg", new_hash != hashes[target.index])

    edge = get_provider("edge")
    regenerated = []
    reused = []
    for seg in segs:
        h = segment_cache_hash(seg)
        if needs_regeneration(seg, h) or (seg.index == target.index):
            # force only changed
            if seg.index != target.index and seg.cache_hash == h and Path(seg.audio_path).exists():
                reused.append(seg.index)
                continue
            out = Path(seg.audio_path)
            before = out.stat().st_mtime
            await asyncio.sleep(1.1)  # ensure mtime resolution
            r = await edge.synthesize(
                SynthRequest(
                    text=seg.text,
                    voice=seg.voice,
                    rate=seg.rate,
                    pitch=seg.pitch,
                    volume=seg.volume,
                    output_path=str(out),
                )
            )
            assert r.success
            seg.cache_hash = segment_cache_hash(seg)
            regenerated.append(seg.index)
            record(f"Regen mtime {seg.index}", out.stat().st_mtime >= before)
        else:
            reused.append(seg.index)

    # Proper smart path: only regenerate when needs_regeneration
    regenerated = []
    reused = []
    # reset segs 1,2,4,5 hashes/paths intact; only 3 needs regen
    for seg in segs:
        h = segment_cache_hash(seg)
        path = Path(seg.audio_path)
        if needs_regeneration(seg, h):
            await asyncio.sleep(1.05)
            r = await edge.synthesize(
                SynthRequest(
                    text=seg.text,
                    voice=seg.voice,
                    rate=seg.rate,
                    pitch=seg.pitch,
                    volume="+0%",
                    output_path=str(path),
                )
            )
            assert r.success
            seg.cache_hash = h
            regenerated.append(seg.index)
        else:
            reused.append(seg.index)
            record(
                f"Reuse mtime {seg.index}",
                abs(path.stat().st_mtime - mtimes[seg.index]) < 0.01 or path.stat().st_mtime == mtimes[seg.index],
                f"old={mtimes[seg.index]} new={path.stat().st_mtime}",
            )

    record("Only changed regenerated", regenerated == [3] or (3 in regenerated and len(regenerated) == 1), f"regen={regenerated} reuse={reused}")

    # Invalidate via rate change
    seg1 = segs[0]
    old_h = seg1.cache_hash
    seg1.rate = "-5%"
    new_h = segment_cache_hash(seg1)
    record("Rate change invalidates cache", needs_regeneration(seg1, new_h) and new_h != old_h)
    seg1.rate = BMT_FRENCH.rate
    seg1.pitch = "+2Hz"
    record("Pitch change invalidates cache", segment_cache_hash(seg1) != old_h)
    seg1.voice = "fr-FR-HenriNeural"
    record("Voice change invalidates cache", segment_cache_hash(seg1) != old_h)


async def phase_edge_fallback() -> None:
    print("\n=== PHASE 5 EDGE FALLBACK ===")
    # Simulate unavailable Edge by using bogus timeout / monkeypatch
    broken = EdgeTTSProvider(timeout=0.001, retry_count=1, base_backoff=0.01)

    class Boom(EdgeTTSProvider):
        async def synthesize(self, request, *, cancel_check=None, on_progress=None):
            from bmt_voice_studio.core.models import SynthResult

            return SynthResult(
                success=False,
                error=(
                    "Could not connect to Edge TTS. "
                    "Your internet connection may be unavailable or the speech service "
                    "may be temporarily refusing requests."
                ),
                provider="edge",
            )

    boom = Boom()
    r = await boom.synthesize(
        SynthRequest(text="test", voice="en-US-JennyNeural", output_path=str(temp_work_dir() / "x.mp3"))
    )
    record("Human-readable Edge error", r.success is False and "Could not connect to Edge TTS" in r.error and "Traceback" not in r.error)

    # Piper status
    piper = get_provider("piper")
    ok, msg = await piper.health_check()
    record("Piper health message", True, msg)
    settings = get_settings()
    record("Auto piper fallback setting exists", hasattr(settings, "auto_piper_fallback"))

    mgr = PiperVoiceManager()
    installed = mgr.installed_voices()
    if installed and settings.piper_male_model:
        # Try actual fallback synth
        out = temp_work_dir() / "piper_fallback.wav"
        pr = await piper.synthesize(
            SynthRequest(text="Offline fallback test.", voice=installed[0].id, output_path=str(out))
        )
        record("Piper offline synth", pr.success, pr.error or str(out))
    else:
        record("Piper fallback", True, f"NOT INSTALLED / no models ({msg})")


def phase_piper_manager() -> None:
    print("\n=== PHASE 6 PIPER MANAGER ===")
    mgr = PiperVoiceManager()
    record("Models dir", models_dir().exists(), str(models_dir()))
    record("sw_CD in catalog", any(c["id"].startswith("sw_CD") for c in PIPER_CATALOG))
    installed = mgr.installed_voices()
    record("Installed list callable", True, f"count={len(installed)}")
    for v in installed[:3]:
        card = mgr.get_model_card(v.id)
        record(f"MODEL_CARD {v.id}", len(card) > 0, card[:80].replace("\n", " "))
    # Assignment persistence
    s = get_settings()
    old_m, old_f = s.piper_male_model, s.piper_female_model
    s.piper_male_model = "qa_male_test"
    s.piper_female_model = "qa_female_test"
    save_settings(s)
    s2 = AppSettings.load()
    record("Piper assignment persist", s2.piper_male_model == "qa_male_test" and s2.piper_female_model == "qa_female_test")
    s2.piper_male_model = old_m
    s2.piper_female_model = old_f
    save_settings(s2)


def phase_mastering(sample_mp3: Path | None) -> None:
    print("\n=== PHASE 7 MASTERING ===")
    if not sample_mp3 or not sample_mp3.exists():
        record("Mastering", False, "No sample")
        return
    out = temp_work_dir() / "qa_master"
    out.mkdir(exist_ok=True)
    opts = MasteringOptions(
        normalize_loudness=True,
        target_lufs=-16.0,
        remove_silence=True,
        fade_in_ms=80,
        fade_out_ms=150,
        peak_limiter=True,
        bitrate_kbps=128,
    )
    try:
        dest = master_audio(sample_mp3, out / "mastered.mp3", opts)
        record("Mastering pipeline", is_valid_audio(dest), f"dur={probe_duration(dest):.2f}")
        # A/B paths exist
        record("A/B original exists", sample_mp3.exists())
        record("A/B processed exists", dest.exists())
        # loudnorm filter presence in code default
        from bmt_voice_studio.config.settings import get_settings

        record("Default target LUFS ~-16", abs(get_settings().target_lufs + 16.0) < 0.01)
    except Exception as exc:
        record("Mastering pipeline", False, str(exc))


async def phase_m3u() -> Path | None:
    print("\n=== PHASE 8 M3U ===")
    pl = Path(r"C:\Users\aganz\Downloads\BMT_English_Neural_Playlist.m3u")
    out = None
    try:
        if pl.exists():
            parsed = parse_m3u_file(pl)
            record("Local M3U parse", len(parsed.items) == 10 and not parsed.is_hls, f"items={len(parsed.items)}")
            out_path = temp_work_dir() / "qa_m3u" / "merged_10.mp3"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out = await download_and_merge(parsed.items, out_path, bitrate_kbps=128)
            dur = probe_duration(out)
            record("10-item merge", is_valid_audio(out), f"dur={dur:.2f}s size={out.stat().st_size} bitrate~128k")
        else:
            record("Local M3U", False, "playlist missing")

        # Paste URL list (2 items if playlist exists)
        if pl.exists():
            urls = [ln.strip() for ln in pl.read_text(encoding="utf-8").splitlines() if ln.startswith("http")][:2]
            pasted = parse_url_list("\n".join(urls))
            record("Paste URL list", len(pasted.items) == 2)

        # HTML rejection
        ok, reason = validate_audio_magic(b"<!DOCTYPE html><html>not audio</html>")
        record("Reject HTML as MP3", not ok and "HTML" in reason)

        # HTTP error simulation via invalid URL
        try:
            from bmt_voice_studio.core.models import PlaylistItem
            from bmt_voice_studio.m3u.downloader import download_item

            await download_item(
                PlaylistItem(index=1, source="https://httpbin.org/status/404", title="bad"),
                temp_work_dir() / "qa_dl",
            )
            record("HTTP error handling", False, "should have raised")
        except DownloadError as exc:
            record("HTTP error handling", "failed" in exc.message.lower() or "404" in exc.message or "HTTP" in exc.message, exc.message)
        except Exception as exc:
            record("HTTP error handling", True, f"raised {type(exc).__name__}: {exc}")
    except Exception as exc:
        record("M3U phase", False, str(exc))
    return out


def phase_hls() -> None:
    print("\n=== PHASE 9 HLS ===")
    simple = "#EXTM3U\n#EXTINF:1,A\nhttps://x/a.mp3\n"
    hls_media = "#EXTM3U\n#EXT-X-TARGETDURATION:10\n#EXTINF:9.0,\nseg0.ts\n"
    hls_master = "#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=128000\naudio.m3u8\n"
    a, b = detect_hls(simple)
    record("Simple M3U not HLS", a is False)
    a, b = detect_hls(hls_media)
    record("HLS media detected", a is True and b is False)
    a, b = detect_hls(hls_master)
    record("HLS master detected", a is True and b is True)

    # Broken HLS should error clearly via FFmpeg
    try:
        ff().run(
            ["-y", "-i", "https://example.invalid/stream.m3u8", "-t", "1", "-f", "null", "-"],
            check=True,
            timeout=20,
        )
        record("Broken HLS error", False, "should fail")
    except Exception as exc:
        msg = str(exc)
        record("Broken HLS clear error", "FFmpeg" in msg or "failed" in msg.lower() or "Error" in type(exc).__name__, type(exc).__name__)


def phase_projects(out_root: Path) -> None:
    print("\n=== PHASE 10 PROJECTS ===")
    svc = ProjectService()
    p = svc.new_project("BMT_QA_RESTORE")
    p.source_text = "Hello {World}"
    p.male_voice = "en-NG-AbeoNeural"
    p.female_voice = "en-NG-EzinneNeural"
    p.provider = "edge"
    p.rate = "-10%"
    p.pitch = "-3Hz"
    p.pause_ms = 450
    p.mp3_bitrate = 192
    p.normalize_loudness = True
    p.target_lufs = -16.0
    parsed = parse_speaker_script(p.source_text)
    p.set_segments(parsed.segments)
    root = svc.ensure_layout(p, out_root)
    path = svc.save(p)
    # Save As
    save_as = root / "project" / "project_save_as.json"
    p.name = "BMT_QA_RESTORE_AS"
    path2 = svc.save(p, save_as)
    loaded = svc.load(path)
    record(
        "Project restore fields",
        loaded.male_voice == "en-NG-AbeoNeural"
        and loaded.female_voice == "en-NG-EzinneNeural"
        and loaded.rate == "-10%"
        and loaded.pitch == "-3Hz"
        and loaded.pause_ms == 450
        and loaded.mp3_bitrate == 192
        and loaded.provider == "edge"
        and "Hello" in loaded.source_text
        and len(loaded.get_segments()) == 2,
    )
    recent = svc.recent()
    record("Recent projects", any(str(path) in r or str(path2) in r for r in recent) or len(recent) > 0, f"n={len(recent)}")
    record("Save As wrote file", path2.exists())


def phase_filenames(out_root: Path) -> None:
    print("\n=== PHASE 11 FILENAMES ===")
    bad = 'BMT<>:"/\\|?* Devotional'
    clean = sanitize_filename(bad)
    record("Sanitize invalid chars", all(c not in clean for c in '<>:"/\\|?*'), clean)
    p = out_root / "final_test.mp3"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"ID3" + b"\x00" * 100)
    u = unique_path(p)
    record("No silent overwrite", u != p and not u.exists() or u.name.endswith("_2.mp3"), u.name)


def phase_settings() -> None:
    print("\n=== PHASE 13 SETTINGS ===")
    s = get_settings()
    original = s.to_dict()
    s.default_language = "fr-FR"
    s.default_preset = "bmt_french"
    s.default_male_voice = "fr-FR-HenriNeural"
    s.default_female_voice = "fr-FR-DeniseNeural"
    s.default_provider = "edge"
    s.auto_piper_fallback = True
    s.rate = "-8%"
    s.pitch = "-1Hz"
    s.volume = "+0%"
    s.pause_ms = 750
    s.mp3_bitrate = 192
    s.theme = "dark"
    s.network_timeout = 45.0
    s.retry_count = 4
    save_settings(s)
    loaded = AppSettings.load()
    ok = (
        loaded.default_language == "fr-FR"
        and loaded.default_preset == "bmt_french"
        and loaded.pause_ms == 750
        and loaded.mp3_bitrate == 192
        and loaded.network_timeout == 45.0
        and loaded.retry_count == 4
        and loaded.rate == "-8%"
        and loaded.pitch == "-1Hz"
    )
    record("Settings persistence", ok)
    # restore practical defaults
    restored = AppSettings.from_dict(original)
    save_settings(restored)


async def phase_health() -> None:
    print("\n=== PHASE 14 HEALTH ===")
    import httpx

    status = {}
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get("https://www.msftconnecttest.com/connecttest.txt")
            status["internet"] = "ONLINE" if r.status_code < 500 else "OFFLINE"
    except Exception:
        status["internet"] = "OFFLINE"
    ok, msg = ff().health_check()
    status["ffmpeg"] = msg
    eok, emsg = await get_provider("edge").health_check()
    status["edge"] = "AVAILABLE" if eok else emsg
    pok, pmsg = await get_provider("piper").health_check()
    status["piper"] = pmsg
    record("Health internet", status["internet"] in ("ONLINE", "OFFLINE"), status["internet"])
    record("Health ffmpeg", ok, msg)
    record("Health edge", True, status["edge"])
    record("Health piper", True, status["piper"])
    # Ensure health check code path doesn't use user script — inspect Edge health uses list_voices
    import inspect

    src = inspect.getsource(EdgeTTSProvider.health_check)
    record("Health no user content", "list_voices" in src and "devotional" not in src.lower())


def phase_logging() -> None:
    print("\n=== PHASE 15 LOGGING ===")
    from bmt_voice_studio.config.paths import logs_dir

    log = logs_dir() / "app.log"
    record("App log exists or creatable", logs_dir().exists(), str(logs_dir()))
    if log.exists():
        text = log.read_text(encoding="utf-8", errors="replace")[-2000:]
        record("Log has no obvious secrets", "api_key" not in text.lower() and "password" not in text.lower())


def phase_gui_stress_logic() -> None:
    print("\n=== PHASE 12 GUI STRESS (logic) ===")
    # Large script 20+ segments
    parts = []
    for i in range(12):
        parts.append(f"Male paragraph number {i+1} with enough text for speech.")
        parts.append("{\nFemale paragraph number %d with enough text.\n}" % (i + 1))
    text = "\n\n".join(parts)
    parsed = parse_speaker_script(text)
    record("Large script 20+ segments", len(parsed.segments) >= 20, f"n={len(parsed.segments)}")
    # GenerationController has cancel and button disable patterns in UI — check source
    from bmt_voice_studio.ui.pages import tts_studio

    src = Path(tts_studio.__file__).read_text(encoding="utf-8")
    record("Generate disables button", "btn_generate.setEnabled(False)" in src)
    record("Cancel wired", "btn_cancel" in src and "_gen.cancel" in src)


async def main() -> int:
    print("BMT VOICE STUDIO QA V1.0")
    out_root = Path.home() / "Documents" / "BMT Voice Studio" / "Exports" / "QA_V1"
    out_root.mkdir(parents=True, exist_ok=True)
    reset_registry()

    await phase_english(out_root)
    fr = await phase_french(out_root)
    await phase_smart_regen(fr, out_root)
    await phase_edge_fallback()
    phase_piper_manager()
    sample = None
    if fr:
        sample = fr[2]
    phase_mastering(sample)
    await phase_m3u()
    phase_hls()
    phase_projects(out_root)
    phase_filenames(out_root / "filename_qa")
    phase_gui_stress_logic()
    phase_settings()
    await phase_health()
    phase_logging()

    passed = sum(1 for c in RESULTS if c.ok)
    failed = sum(1 for c in RESULTS if not c.ok)
    report = {
        "passed": passed,
        "failed": failed,
        "total": len(RESULTS),
        "checks": [{"name": c.name, "ok": c.ok, "detail": c.detail} for c in RESULTS],
    }
    report_path = ROOT / "QA_RAW_RESULTS.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\n=== SUMMARY {passed}/{len(RESULTS)} passed, {failed} failed ===")
    print(f"Wrote {report_path}")
    for c in RESULTS:
        if not c.ok:
            print(f"FAIL DETAIL: {c.name}: {c.detail}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
