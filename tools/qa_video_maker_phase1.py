"""Generate synthetic Video Maker Phase 1 QA assets and a real portrait MP4."""

from __future__ import annotations

import json
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
        raise RuntimeError((result.stderr or result.stdout or "")[-1500:])


def make_assets(folder: Path, ffmpeg: str) -> dict[str, Path]:
    from PIL import Image, ImageDraw, ImageFont

    folder.mkdir(parents=True, exist_ok=True)
    portrait = folder / "portrait_photo.png"
    landscape = folder / "landscape_photo.png"
    img = Image.new("RGB", (1080, 1920), (18, 42, 74))
    draw = ImageDraw.Draw(img)
    draw.rectangle([80, 700, 1000, 1220], fill=(212, 160, 23))
    draw.text((140, 860), "PORTRAIT", fill=(15, 20, 28))
    img.save(portrait)
    img2 = Image.new("RGB", (1920, 1080), (28, 90, 64))
    draw2 = ImageDraw.Draw(img2)
    draw2.rectangle([200, 300, 1720, 780], fill=(244, 247, 251))
    draw2.text((260, 480), "LANDSCAPE", fill=(15, 20, 28))
    img2.save(landscape)

    portrait_vid = folder / "portrait_video.mp4"
    landscape_vid = folder / "landscape_video.mp4"
    audio = folder / "master_audio.wav"
    _run(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x1E3A5F:s=1080x1920:d=4",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=220:duration=4",
            "-shortest",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(portrait_vid),
        ]
    )
    _run(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x2F6FED:s=1920x1080:d=4",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=330:duration=4",
            "-shortest",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(landscape_vid),
        ]
    )
    _run(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=42",
            "-ar",
            "48000",
            "-ac",
            "2",
            str(audio),
        ]
    )
    return {
        "portrait_photo": portrait,
        "landscape_photo": landscape,
        "portrait_video": portrait_vid,
        "landscape_video": landscape_vid,
        "audio": audio,
    }


def probe_mp4(ffmpeg: str, path: Path) -> dict:
    result = subprocess.run([ffmpeg, "-hide_banner", "-i", str(path)], capture_output=True, text=True)
    blob = (result.stderr or "") + (result.stdout or "")
    from bmt_voice_studio.video.media_probe import parse_ffmpeg_duration, parse_ffmpeg_video_size

    w, h = parse_ffmpeg_video_size(blob)
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
        "raw": blob[-2000:],
    }


def main() -> int:
    from bmt_voice_studio.resources import logo_path
    from bmt_voice_studio.video.composition import build_composition_plan
    from bmt_voice_studio.video.ffmpeg_renderer import VideoRenderer
    from bmt_voice_studio.video.media_probe import probe_audio_duration, probe_media
    from bmt_voice_studio.video.models import MediaItem, VideoProject

    ffmpeg = _ffmpeg()
    qa_root = ROOT / "qa_outputs" / "video_maker_phase1"
    assets_dir = qa_root / "assets"
    assets = make_assets(assets_dir, ffmpeg)
    out = qa_root / "BMT_VIDEO_MAKER_PHASE1_TEST.mp4"
    if out.exists():
        out.unlink()

    items: list[MediaItem] = []
    for key in ("portrait_photo", "landscape_photo", "portrait_video", "landscape_video"):
        items.append(probe_media(assets[key]))
    audio_dur = probe_audio_duration(assets["audio"])
    logo = logo_path()
    project = VideoProject(
        devotional_date=date.today().isoformat(),
        language="en",
        audio_path=str(assets["audio"]),
        audio_duration=audio_dur,
        topic="The God Who Provides",
        week_focus="Trust in every season",
        month_theme="Abundance",
        logo_path=str(logo) if logo else "",
        media_items=items,
    )
    temp = qa_root / "temp_render"
    temp.mkdir(parents=True, exist_ok=True)
    plan = build_composition_plan(project, output_path=out, temp_dir=temp, job_id="qa_phase1")
    renderer = VideoRenderer()
    produced = renderer.render(project, plan, keep_temp_on_success=True)
    info = probe_mp4(ffmpeg, produced)
    report = {
        "ffmpeg": ffmpeg,
        "output": str(produced),
        "probe": {k: v for k, v in info.items() if k != "raw"},
        "audio_duration": audio_dur,
        "ok": bool(
            info["exists"]
            and info["width"] == 1080
            and info["height"] == 1920
            and info["h264"]
            and info["aac"]
            and info["duration"] > 10
        ),
    }
    (qa_root / "PHASE1_PROBE.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
