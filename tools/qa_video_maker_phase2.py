"""Phase 2 QA: preview MP4 + real BMT audio renders for CLASSIC and NATURE."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _ffmpeg() -> str:
    from bmt_voice_studio.audio.ffmpeg_service import FFmpegService

    return FFmpegService().find()


def _run(cmd: list[str]) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "")[-1800:])


def probe_mp4(ffmpeg: str, path: Path) -> dict:
    result = subprocess.run([ffmpeg, "-hide_banner", "-i", str(path)], capture_output=True, text=True)
    blob = (result.stderr or "") + (result.stdout or "")
    from bmt_voice_studio.video.media_probe import parse_ffmpeg_duration, parse_ffmpeg_video_size

    w, h = parse_ffmpeg_video_size(blob)
    audio_streams = blob.lower().count("audio:")
    return {
        "path": str(path),
        "exists": path.is_file(),
        "size_bytes": path.stat().st_size if path.is_file() else 0,
        "width": w,
        "height": h,
        "duration": parse_ffmpeg_duration(blob),
        "h264": "h264" in blob.lower() or "avc" in blob.lower(),
        "aac": "aac" in blob.lower(),
        "fps30": "30 fps" in blob or "30 tbr" in blob or "30.00" in blob,
        "audio_stream_count": audio_streams,
        "raw": blob[-2500:],
    }


def locate_real_audio() -> Path | None:
    from bmt_voice_studio.video.discovery import find_generated_audio

    path = find_generated_audio(date(2026, 8, 14), "en")
    if path and path.is_file():
        return path
    path = find_generated_audio(date.today(), "en")
    if path and path.is_file():
        return path
    return None


def ensure_assets(ffmpeg: str, folder: Path) -> dict[str, Path]:
    import importlib.util

    phase1 = ROOT / "qa_outputs" / "video_maker_phase1" / "assets"
    needed = ("portrait_photo.png", "landscape_photo.png", "portrait_video.mp4", "landscape_video.mp4")
    if phase1.is_dir() and all((phase1 / name).is_file() for name in needed):
        folder.mkdir(parents=True, exist_ok=True)
        copied: dict[str, Path] = {}
        mapping = {
            "portrait_photo": "portrait_photo.png",
            "landscape_photo": "landscape_photo.png",
            "portrait_video": "portrait_video.mp4",
            "landscape_video": "landscape_video.mp4",
        }
        for key, name in mapping.items():
            dest = folder / name
            if not dest.exists():
                shutil.copy2(phase1 / name, dest)
            copied[key] = dest
        return copied
    spec = importlib.util.spec_from_file_location("qa_video_maker_phase1", ROOT / "tools" / "qa_video_maker_phase1.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod.make_assets(folder, ffmpeg)


def shorten_audio(ffmpeg: str, src: Path, dest: Path, seconds: float = 20.0) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            ffmpeg,
            "-y",
            "-i",
            str(src),
            "-t",
            f"{seconds:.3f}",
            "-c:a",
            "copy",
            str(dest),
        ]
    )
    if not dest.is_file() or dest.stat().st_size < 1000:
        _run(
            [
                ffmpeg,
                "-y",
                "-i",
                str(src),
                "-t",
                f"{seconds:.3f}",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                str(dest),
            ]
        )
    return dest


def render_project(project, dest: Path, temp: Path, job_id: str, preview: bool = False) -> Path:
    from bmt_voice_studio.video.composition import build_composition_plan, build_preview_plan
    from bmt_voice_studio.video.ffmpeg_renderer import VideoRenderer

    temp.mkdir(parents=True, exist_ok=True)
    if preview:
        plan = build_preview_plan(project, output_path=dest, temp_dir=temp, job_id=job_id)
    else:
        plan = build_composition_plan(project, output_path=dest, temp_dir=temp, job_id=job_id)
    return VideoRenderer().render(project, plan, keep_temp_on_success=True)


def main() -> int:
    from bmt_voice_studio.resources import logo_path
    from bmt_voice_studio.video.discovery import extract_metadata, load_source_text
    from bmt_voice_studio.video.media_probe import probe_audio_duration, probe_media
    from bmt_voice_studio.video.models import (
        TEMPLATE_BMT_CLASSIC,
        TEMPLATE_BMT_NATURE,
        VideoProject,
        output_profile_for,
    )

    ffmpeg = _ffmpeg()
    qa_root = ROOT / "qa_outputs" / "video_maker_phase2"
    qa_root.mkdir(parents=True, exist_ok=True)
    assets = ensure_assets(ffmpeg, qa_root / "assets")
    real_audio = locate_real_audio()
    if real_audio is None:
        raise SystemExit("No generated Daily BMT MP3 found for QA.")

    items = [probe_media(assets[k]) for k in ("portrait_photo", "landscape_photo", "portrait_video", "landscape_video")]
    meta = extract_metadata(load_source_text(date(2026, 8, 14), "en"))
    logo = logo_path()
    audio_dur = probe_audio_duration(real_audio)

    base_kwargs = dict(
        devotional_date="2026-08-14",
        language="en",
        topic=meta.get("topic") or "Kingdom Priorities",
        week_focus=meta.get("week_focus") or "Living With Eternal Values",
        month_theme=meta.get("month_theme") or "Purposeful Living",
        memory_verse=meta.get("memory_verse") or "",
        title=meta.get("title") or meta.get("topic") or "",
        logo_path=str(logo) if logo else "",
        media_items=items,
    )

    preview_out = qa_root / "BMT_14_AUG_2026_ENGLISH_PREVIEW.mp4"
    classic_out = qa_root / "BMT_CLASSIC_REAL_AUDIO_TEST.mp4"
    nature_out = qa_root / "BMT_NATURE_REAL_AUDIO_TEST.mp4"
    nature_audio = shorten_audio(ffmpeg, real_audio, qa_root / "nature_audio_copy.mp3", 22.0)

    preview_project = VideoProject(
        **base_kwargs,
        audio_path=str(real_audio),
        audio_duration=audio_dur,
        template_id=TEMPLATE_BMT_CLASSIC,
        output_profile=output_profile_for("preview"),
    )
    print("Rendering 12-second preview…")
    preview_path = render_project(preview_project, preview_out, qa_root / "temp_preview", "qa_preview", preview=True)

    classic_project = VideoProject(
        **base_kwargs,
        audio_path=str(real_audio),
        audio_duration=audio_dur,
        template_id=TEMPLATE_BMT_CLASSIC,
        output_profile=output_profile_for("standard_1080p"),
    )
    print("Rendering BMT CLASSIC full real-audio video…")
    classic_path = render_project(classic_project, classic_out, qa_root / "temp_classic", "qa_classic")

    nature_dur = probe_audio_duration(nature_audio)
    nature_project = VideoProject(
        **base_kwargs,
        audio_path=str(nature_audio),
        audio_duration=nature_dur,
        template_id=TEMPLATE_BMT_NATURE,
        output_profile=output_profile_for("standard_1080p"),
    )
    print("Rendering BMT NATURE shortened QA video…")
    nature_path = render_project(nature_project, nature_out, qa_root / "temp_nature", "qa_nature")

    probes = {
        "preview": probe_mp4(ffmpeg, preview_path),
        "classic": probe_mp4(ffmpeg, classic_path),
        "nature": probe_mp4(ffmpeg, nature_path),
    }
    report = {
        "ffmpeg": ffmpeg,
        "real_audio": str(real_audio),
        "nature_audio_copy": str(nature_audio),
        "outputs": {k: {kk: vv for kk, vv in v.items() if kk != "raw"} for k, v in probes.items()},
        "ok": all(
            p["exists"] and p["h264"] and p["aac"] and p["audio_stream_count"] == 1
            for p in probes.values()
        ),
    }
    (qa_root / "PHASE2_PROBE.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items()}, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
