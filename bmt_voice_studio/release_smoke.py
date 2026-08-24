"""Headless release-smoke checks for packaged EXE / clean-machine gate."""

from __future__ import annotations

import json
import re
import sys
import traceback
from pathlib import Path


def _probe_duration(path: Path) -> float:
    from bmt_voice_studio.audio.ffmpeg_service import FFmpegService

    r = FFmpegService().run(["-i", str(path)], check=False)
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", r.stderr or "")
    if not m:
        return 0.0
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


def run_release_smoke(report_path: Path | None = None) -> int:
    """Run end-to-end smoke without GUI. Returns process exit code."""
    import asyncio
    import os

    # Ensure Qt is initialized before any QPixmap/QIcon usage (packaged EXE).
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    qt_app = QApplication.instance() or QApplication(["BMTVoiceStudio-smoke"])

    from bmt_voice_studio.audio.ffmpeg_service import FFmpegService
    from bmt_voice_studio.audio.joining import join_segments
    from bmt_voice_studio.audio.mastering import MasteringOptions, master_audio
    from bmt_voice_studio.config.paths import default_exports_dir, temp_work_dir
    from bmt_voice_studio.core.models import Segment, Speaker, SynthRequest
    from bmt_voice_studio.core.parser import parse_speaker_script
    from bmt_voice_studio.m3u.downloader import download_and_merge
    from bmt_voice_studio.m3u.parser import parse_m3u_file
    from bmt_voice_studio.projects.project import ProjectService
    from bmt_voice_studio.providers import get_provider, reset_registry
    from bmt_voice_studio.resources import load_app_icon, logo_path

    report: dict = {"checks": []}

    def check(name: str, ok: bool, detail: str = "") -> None:
        report["checks"].append({"name": name, "ok": bool(ok), "detail": detail})
        line = f"{'PASS' if ok else 'FAIL'} {name} {detail}"
        try:
            print(line, flush=True)
        except Exception:
            pass
        # Always mirror to a log file for windowed EXE
        try:
            log = temp_work_dir() / "release_smoke.log"
            with log.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except Exception:
            pass

    _ = qt_app  # keep alive

    try:
        check("logo_resource", logo_path() is not None and logo_path().exists(), str(logo_path()))
        icon = load_app_icon()
        check("bbnet_icon", not icon.isNull())

        ff_ok, ff_msg = FFmpegService().health_check()
        check("packaged_ffmpeg", ff_ok, ff_msg)
        # Ensure ffmpeg path is from imageio or local, not requiring system install message ERROR
        try:
            ff_path = FFmpegService().find()
            check("ffmpeg_path_resolved", bool(ff_path), ff_path)
        except Exception as exc:
            check("ffmpeg_path_resolved", False, str(exc))

        reset_registry()
        edge = get_provider("edge")

        async def _run() -> None:
            out_root = default_exports_dir() / "RELEASE_SMOKE"
            out_root.mkdir(parents=True, exist_ok=True)

            # English brace parse + generate
            en = "Welcome to BMT Voice Studio.\n{\nThis is the female section.\n}\nClosing male line."
            parsed = parse_speaker_script(en)
            check("brace_parse", parsed.ok and len(parsed.segments) == 3, str([s.speaker.value for s in parsed.segments]))
            en_dir = out_root / "en"
            en_dir.mkdir(exist_ok=True)
            for seg in parsed.segments:
                voice = "en-NG-AbeoNeural" if seg.speaker == Speaker.MALE else "en-NG-EzinneNeural"
                path = en_dir / f"{seg.index:03d}.mp3"
                r = await edge.synthesize(
                    SynthRequest(text=seg.text, voice=voice, rate="-10%", pitch="-3Hz", output_path=str(path))
                )
                check(f"en_seg_{seg.index}", r.success, r.error or str(path))
                seg.audio_path = str(path)
                seg.voice = voice
            en_mp3 = en_dir / "final.mp3"
            en_wav = en_dir / "final.wav"
            join_segments(parsed.segments, en_mp3, pause_ms=250, bitrate_kbps=128, also_wav=False)
            mastered = en_dir / "final_mastered.mp3"
            master_audio(en_mp3, mastered, MasteringOptions(bitrate_kbps=128), overwrite=True)
            FFmpegService().convert(mastered, en_wav)
            check("en_final_mp3", mastered.exists() and _probe_duration(mastered) > 1, f"{_probe_duration(mastered):.2f}s")
            check("en_final_wav", en_wav.exists() and _probe_duration(en_wav) > 1, f"{_probe_duration(en_wav):.2f}s")

            # French short
            fr_text = "Bienvenue.\n{\nSection féminine avec café et français.\n}"
            fr_parsed = parse_speaker_script(fr_text)
            check("fr_accents_parse", "é" in fr_text and fr_parsed.ok)
            fr_dir = out_root / "fr"
            fr_dir.mkdir(exist_ok=True)
            for seg in fr_parsed.segments:
                voice = (
                    "fr-FR-HenriNeural"
                    if seg.speaker == Speaker.MALE
                    else "fr-FR-DeniseNeural"
                )
                path = fr_dir / f"{seg.index:03d}.mp3"
                r = await edge.synthesize(
                    SynthRequest(text=seg.text, voice=voice, rate="-8%", pitch="-1Hz", output_path=str(path))
                )
                check(f"fr_seg_{seg.index}", r.success, r.error or str(path))
                seg.audio_path = str(path)
            fr_mp3 = fr_dir / "final.mp3"
            join_segments(fr_parsed.segments, fr_mp3, pause_ms=250, bitrate_kbps=128, also_wav=False)
            check("fr_final_mp3", fr_mp3.exists() and _probe_duration(fr_mp3) > 0.8, f"{_probe_duration(fr_mp3):.2f}s")

            # Project save/load
            svc = ProjectService()
            proj = svc.new_project("BMT_RELEASE_SMOKE")
            proj.source_text = en
            proj.set_segments(parsed.segments)
            root = svc.ensure_layout(proj, out_root)
            path = svc.save(proj)
            loaded = svc.load(path)
            check("project_save_restore", loaded.name == "BMT_RELEASE_SMOKE" and "Welcome" in loaded.source_text, str(path))

            # M3U if available
            pl = Path.home() / "Downloads" / "BMT_English_Neural_Playlist.m3u"
            if pl.exists():
                items = parse_m3u_file(pl).items[:3]
                m3u_out = out_root / "m3u_smoke.mp3"
                await download_and_merge(items, m3u_out, bitrate_kbps=128)
                check("m3u_merge", m3u_out.exists() and _probe_duration(m3u_out) > 1, f"{_probe_duration(m3u_out):.2f}s")
            else:
                check("m3u_merge", True, "SKIPPED_NO_PLAYLIST")

        asyncio.run(_run())
    except Exception as exc:
        check("smoke_exception", False, f"{exc}\n{traceback.format_exc()[-800:]}")

    failed = sum(1 for c in report["checks"] if not c["ok"])
    report["passed"] = sum(1 for c in report["checks"] if c["ok"])
    report["failed"] = failed
    target = report_path or (temp_work_dir() / "release_smoke_report.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("SMOKE_REPORT", target)
    print("SMOKE_SUMMARY", report["passed"], "passed,", failed, "failed")
    return 0 if failed == 0 else 1
