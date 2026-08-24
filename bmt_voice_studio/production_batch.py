"""August 13 (and similar) real production batch via packaged EXE."""

from __future__ import annotations

import asyncio
import json
import re
import traceback
from pathlib import Path

from bmt_voice_studio.audio.ffmpeg_service import FFmpegService
from bmt_voice_studio.audio.joining import join_segments
from bmt_voice_studio.audio.mastering import MasteringOptions, master_audio
from bmt_voice_studio.audio.source_export import export_original_pipeline
from bmt_voice_studio.config.presets import BMT_ENGLISH, BMT_FRENCH
from bmt_voice_studio.core.hashing import segment_cache_hash
from bmt_voice_studio.core.models import Speaker, SynthRequest
from bmt_voice_studio.core.parser import parse_speaker_script_source
from bmt_voice_studio.m3u.parser import validate_audio_magic
from bmt_voice_studio.projects.project import ProjectService
from bmt_voice_studio.providers import get_provider, reset_registry


def _probe(path: Path) -> dict:
    ff = FFmpegService()
    r = ff.run(["-i", str(path)], check=False)
    err = r.stderr or ""
    dur = 0.0
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", err)
    if m:
        dur = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    br = None
    bm = re.search(r"bitrate:\s*(\d+)\s*kb/s", err)
    if bm:
        br = int(bm.group(1))
    sr = None
    sm = re.search(r",\s*(\d+)\s*Hz", err)
    if sm:
        sr = int(sm.group(1))
    ch = "mono" if "mono" in err else ("stereo" if "stereo" in err else "unknown")
    codec = "mp3" if "Audio: mp3" in err else ("pcm" if "pcm_" in err or "Audio: pcm" in err else "unknown")
    return {
        "duration_sec": round(dur, 3),
        "bitrate_kbps": br,
        "sample_rate": sr,
        "channels": ch,
        "codec": codec,
        "size_bytes": path.stat().st_size if path.exists() else 0,
        "ffmpeg_line": next((ln.strip() for ln in err.splitlines() if "Audio:" in ln), ""),
    }


def _loudness(path: Path) -> dict:
    """Measure integrated loudness via ffmpeg loudnorm print_format=json (first pass)."""
    ff = FFmpegService()
    try:
        r = ff.run(
            [
                "-i",
                str(path),
                "-af",
                "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json",
                "-f",
                "null",
                "-",
            ],
            check=False,
            timeout=300,
        )
        text = (r.stderr or "") + (r.stdout or "")
        # JSON block at end
        start = text.rfind("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            data = json.loads(text[start : end + 1])
            return {
                "input_i": data.get("input_i"),
                "input_tp": data.get("input_tp"),
                "input_lra": data.get("input_lra"),
                "input_thresh": data.get("input_thresh"),
            }
    except Exception as exc:
        return {"error": str(exc)}
    return {"error": "loudness parse failed"}


async def _generate_language(
    *,
    name: str,
    source_file: Path,
    preset,
    out_root: Path,
    pause_ms: int = 450,
    target_lufs: float = -16.0,
) -> dict:
    text = source_file.read_text(encoding="utf-8")
    parsed = parse_speaker_script_source(text)
    result: dict = {
        "name": name,
        "source": str(source_file),
        "ok": False,
        "errors": [],
        "segments": [],
        "final_mp3": "",
        "final_wav": "",
    }
    if not parsed.ok:
        result["errors"] = [e.message for e in parsed.errors]
        return result

    svc = ProjectService()
    project = svc.new_project(name)
    project.source_text = text
    project.preset_id = preset.id
    project.provider = "edge"
    project.male_voice = preset.male_voice
    project.female_voice = preset.female_voice
    project.rate = preset.rate
    project.pitch = preset.pitch
    project.volume = preset.volume
    project.pause_ms = preset.pipeline.pause_ms
    project.mp3_bitrate = preset.pipeline.mp3_bitrate_kbps or 128
    project.normalize_loudness = preset.pipeline.apply_bmt_mastering
    project.target_lufs = target_lufs
    project.peak_limiter = True
    project.fade_out_ms = 120
    project.remove_silence = False

    root = svc.ensure_layout(project, out_root)
    seg_dir = root / "segments"
    edge = get_provider("edge")
    retries: list[str] = []

    for seg in parsed.segments:
        seg.voice = project.male_voice if seg.speaker == Speaker.MALE else project.female_voice
        seg.rate = project.rate
        seg.pitch = project.pitch
        seg.volume = preset.volume
        seg.provider = "edge"
        out = seg_dir / f"{seg.index:03d}_{seg.speaker.value}.mp3"
        last_err = ""
        ok = False
        for attempt in range(1, 4):
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
            if r.success and out.exists() and out.stat().st_size > 64:
                magic_ok, kind = validate_audio_magic(out.read_bytes()[:256])
                if magic_ok:
                    ok = True
                    break
                last_err = f"invalid audio magic: {kind}"
            else:
                last_err = r.error or "empty output"
            retries.append(f"{name} seg {seg.index} attempt {attempt}: {last_err}")
            await asyncio.sleep(1.5 * attempt)
        if not ok:
            result["errors"].append(f"Segment {seg.index} failed: {last_err}")
            return result
        seg.audio_path = str(out)
        seg.cache_hash = segment_cache_hash(seg)
        info = _probe(out)
        result["segments"].append(
            {
                "index": seg.index,
                "role": seg.speaker.value.upper(),
                "voice": seg.voice,
                "rate": seg.rate,
                "pitch": seg.pitch,
                "path": str(out),
                "chars": len(seg.text),
                "probe": info,
                "valid": info["duration_sec"] > 0,
            }
        )

    # Join + master
    raw = root / "final" / "_raw_join.mp3"
    if raw.exists():
        raw.unlink()
    join_segments(
        parsed.segments,
        raw,
        pause_ms=preset.pipeline.pause_ms,
        bitrate_kbps=preset.pipeline.mp3_bitrate_kbps or 128,
        also_wav=False,
    )
    final_mp3 = root / "final" / f"{name}_FINAL.mp3"
    final_wav = root / "final" / f"{name}_FINAL.wav"
    for p in (final_mp3, final_wav):
        if p.exists():
            p.unlink()
    if preset.pipeline.apply_bmt_mastering:
        mastered = master_audio(
            raw,
            final_mp3,
            MasteringOptions(
                normalize_loudness=True,
                target_lufs=target_lufs,
                remove_silence=False,
                fade_in_ms=40,
                fade_out_ms=120,
                peak_limiter=True,
                bitrate_kbps=preset.pipeline.mp3_bitrate_kbps or 128,
                lowpass_hz=preset.pipeline.lowpass_hz,
            ),
            overwrite=True,
        )
        if preset.pipeline.export_wav:
            FFmpegService().convert(mastered, final_wav, bitrate_kbps=preset.pipeline.mp3_bitrate_kbps or 128)
    else:
        export_original_pipeline(
            raw,
            final_mp3 if preset.pipeline.export_mp3 else None,
            final_wav if preset.pipeline.export_wav else None,
            preset.pipeline,
            overwrite=True,
        )
        mastered = final_mp3 if final_mp3.exists() else raw
    project.set_segments(parsed.segments)
    project.final_mp3 = str(mastered)
    project.final_wav = str(final_wav)
    svc.save(project)

    result["final_mp3"] = str(mastered)
    result["final_wav"] = str(final_wav)
    result["mp3_probe"] = _probe(mastered)
    result["wav_probe"] = _probe(final_wav)
    result["loudness"] = _loudness(mastered) if mastered.exists() else {}
    result["retries"] = retries
    result["output_folder"] = str(root)
    result["ok"] = (
        all(s["valid"] for s in result["segments"])
        and result["mp3_probe"]["duration_sec"] > 10
        and result["wav_probe"]["duration_sec"] > 10
    )
    return result


async def run_aug13_production(input_dir: Path, output_dir: Path, report_json: Path) -> int:
    reset_registry()
    output_dir.mkdir(parents=True, exist_ok=True)
    en_src = input_dir / "BMT_13_AUG_2026_EN_TTS_READY.txt"
    fr_src = input_dir / "BMT_13_AUG_2026_FR_TTS_READY.txt"
    report = {
        "input_dir": str(input_dir),
        "output_dir": str(output_dir),
        "english": None,
        "french": None,
        "engine": "edge-tts via packaged/app EdgeTTSProvider (not eSpeak)",
    }
    report["english"] = await _generate_language(
        name="BMT_13_AUG_2026_ENGLISH",
        source_file=en_src,
        preset=BMT_ENGLISH,
        out_root=output_dir,
    )
    report["french"] = await _generate_language(
        name="BMT_13_AUG_2026_FRENCH",
        source_file=fr_src,
        preset=BMT_FRENCH,
        out_root=output_dir,
    )
    report_json.parent.mkdir(parents=True, exist_ok=True)
    report_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    ok = bool(report["english"]["ok"] and report["french"]["ok"])
    print("PRODUCTION_JSON", report_json)
    print("EN_OK", report["english"]["ok"], "FR_OK", report["french"]["ok"])
    return 0 if ok else 1


def run_production_batch(argv: list[str]) -> int:
    """CLI: --production-batch <input_dir> --out <output_dir> [--report path.json]"""
    try:
        input_dir = Path(argv[argv.index("--production-batch") + 1])
        out = Path(argv[argv.index("--out") + 1]) if "--out" in argv else Path.home() / "Documents" / "BMT Voice Studio" / "Exports" / "PRODUCTION_AUG13"
        report = (
            Path(argv[argv.index("--report") + 1])
            if "--report" in argv
            else out / "production_aug13_report.json"
        )
        return asyncio.run(run_aug13_production(input_dir, out, report))
    except Exception:
        print(traceback.format_exc())
        return 1
