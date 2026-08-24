"""Phase 3 QA: multi-language batch from one visual project + caption previews."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DAY = date(2026, 8, 14)


def _ffmpeg() -> str:
    from bmt_voice_studio.audio.ffmpeg_service import FFmpegService

    return FFmpegService().find()


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
        "codec": "h264" if ("h264" in blob.lower() or "avc" in blob.lower()) else "",
        "raw_tail": blob[-1800:],
    }


def locate_audio(lang: str) -> Path | None:
    from bmt_voice_studio.video.discovery import find_generated_audio

    path = find_generated_audio(DAY, lang)
    if path and path.is_file():
        return path
    path = find_generated_audio(date.today(), lang)
    return path if path and path.is_file() else None


def ensure_assets(ffmpeg: str, folder: Path) -> list[Path]:
    folder.mkdir(parents=True, exist_ok=True)
    phase1 = ROOT / "qa_outputs" / "video_maker_phase1" / "assets"
    names = [
        "portrait_photo.png",
        "landscape_photo.png",
        "extra_photo.png",
        "portrait_video.mp4",
        "landscape_video.mp4",
        "extra_video.mp4",
    ]
    out: list[Path] = []
    if phase1.is_dir():
        mapping = {
            "portrait_photo.png": "portrait_photo.png",
            "landscape_photo.png": "landscape_photo.png",
            "portrait_video.mp4": "portrait_video.mp4",
            "landscape_video.mp4": "landscape_video.mp4",
        }
        for dest_name, src_name in mapping.items():
            src = phase1 / src_name
            dest = folder / dest_name
            if src.is_file() and not dest.exists():
                shutil.copy2(src, dest)
    extra_photo = folder / "extra_photo.png"
    if not extra_photo.exists():
        from PIL import Image

        Image.new("RGB", (1600, 1200), (32, 64, 48)).save(extra_photo)
    extra_video = folder / "extra_video.mp4"
    if not extra_video.exists():
        src_clip = folder / "portrait_video.mp4"
        if src_clip.is_file():
            shutil.copy2(src_clip, extra_video)
        else:
            subprocess.run(
                [
                    ffmpeg,
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    "color=c=0x1a3a2a:s=1080x1920:d=4:r=30",
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    str(extra_video),
                ],
                check=False,
                capture_output=True,
            )
    if not (folder / "portrait_photo.png").exists():
        from PIL import Image

        Image.new("RGB", (1080, 1920), (40, 30, 20)).save(folder / "portrait_photo.png")
        Image.new("RGB", (1920, 1080), (20, 40, 30)).save(folder / "landscape_photo.png")
    if not (folder / "portrait_video.mp4").exists():
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-f",
                "lavfi",
                "-i",
                "color=c=0x243018:s=1080x1920:d=4:r=30",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                str(folder / "portrait_video.mp4"),
            ],
            check=False,
            capture_output=True,
        )
        shutil.copy2(folder / "portrait_video.mp4", folder / "landscape_video.mp4")
    for name in names:
        path = folder / name
        if path.is_file():
            out.append(path)
    return out


def build_project(assets: list[Path], tracks: list, template: str, captions: bool):
    from bmt_voice_studio.resources import logo_path as packaged_logo_path
    from bmt_voice_studio.video.media_probe import probe_media
    from bmt_voice_studio.video.models import TEMPLATE_BMT_NATURE, VideoProject

    items = []
    for path in assets:
        try:
            items.append(probe_media(str(path)))
        except Exception:
            continue
    ready = [t for t in tracks if t.ready]
    first = ready[0] if ready else None
    return VideoProject(
        devotional_date=DAY.isoformat(),
        language=first.language if first else "en",
        audio_path=first.audio_path if first else "",
        audio_duration=first.audio_duration if first else 0.0,
        topic=first.topic if first else "",
        week_focus=first.week_focus if first else "",
        month_theme=first.month_theme if first else "",
        title=first.title if first else "",
        memory_verse=first.memory_verse if first else "",
        logo_path=str(packaged_logo_path() or ""),
        media_items=items,
        template_id=template or TEMPLATE_BMT_NATURE,
        languages=list(tracks),
        selected_languages=[t.language for t in ready],
        show_captions=captions,
    )


def render_one(project, dest: Path | None = None) -> dict:
    from bmt_voice_studio.video.composition import build_composition_plan, validate_project_for_render
    from bmt_voice_studio.video.ffmpeg_renderer import VideoRenderer
    from bmt_voice_studio.video.paths import new_job_id, video_output_path, video_render_temp_dir

    validate_project_for_render(project)
    job = new_job_id()
    temp = video_render_temp_dir(job)
    out = dest or video_output_path(project.devotional_date, project.language)
    plan = build_composition_plan(project, output_path=out, temp_dir=temp, job_id=job)
    renderer = VideoRenderer()
    started = time.time()
    path = renderer.render(project, plan)
    elapsed = time.time() - started
    metrics = dict(renderer.last_metrics or {})
    metrics["wall_elapsed"] = round(elapsed, 2)
    return {"output": str(path), "metrics": metrics, "plan_scenes": len(plan.scenes)}


def render_preview(project, start: float = 0.0) -> dict:
    from bmt_voice_studio.video.composition import build_preview_plan, validate_project_for_render
    from bmt_voice_studio.video.ffmpeg_renderer import VideoRenderer
    from bmt_voice_studio.video.paths import new_job_id, preview_output_path, video_render_temp_dir

    validate_project_for_render(project)
    job = new_job_id()
    temp = video_render_temp_dir(job)
    dest = preview_output_path(project.devotional_date, project.language)
    plan = build_preview_plan(project, output_path=dest, temp_dir=temp, job_id=job, preview_start=start)
    renderer = VideoRenderer()
    path = renderer.render(project, plan)
    return {"output": str(path), "metrics": dict(renderer.last_metrics or {})}


def main() -> int:
    from bmt_voice_studio.video.batch import projects_for_batch
    from bmt_voice_studio.video.discovery import language_tracks_for_day
    from bmt_voice_studio.video.models import TEMPLATE_BMT_MINIMAL, TEMPLATE_BMT_NATURE

    ffmpeg = _ffmpeg()
    qa_dir = ROOT / "qa_outputs" / "video_maker_phase3"
    assets_dir = qa_dir / "assets"
    assets = ensure_assets(ffmpeg, assets_dir)
    tracks = language_tracks_for_day(DAY)
    discovered = {t.language: {"ready": t.ready, "topic": t.topic, "audio": t.audio_path} for t in tracks}
    ready = [t.language for t in tracks if t.ready]
    report: dict = {
        "ffmpeg": ffmpeg,
        "assets": [str(p) for p in assets],
        "discovered": discovered,
        "ready": ready,
        "renders": {},
        "previews": {},
        "probes": {},
    }
    photos = [p for p in assets if p.suffix.lower() in {".png", ".jpg", ".jpeg"}]
    clips = [p for p in assets if p.suffix.lower() == ".mp4"]
    report["photo_count"] = len(photos)
    report["clip_count"] = len(clips)

    shared = build_project(assets, tracks, TEMPLATE_BMT_NATURE, captions=False)
    langs = [x for x in ("en", "fr") if x in ready] or ready[:2]
    batch = projects_for_batch(shared, langs)
    for bound in batch:
        key = bound.language
        print(f"Rendering {key} Nature full-length…", flush=True)
        try:
            result = render_one(bound)
            report["renders"][key] = result
            report["probes"][key] = probe_mp4(ffmpeg, Path(result["output"]))
        except Exception as exc:
            report["renders"][key] = {"error": str(exc)}

    for lang in ready:
        bound_list = projects_for_batch(shared, [lang])
        if not bound_list:
            continue
        cap_proj = bound_list[0]
        cap_proj.show_captions = True
        cap_proj.branding.captions = True
        print(f"Caption preview {lang}…", flush=True)
        try:
            result = render_preview(cap_proj, start=30.0 if cap_proj.audio_duration > 45 else 0.0)
            report["previews"][lang] = result
        except Exception as exc:
            report["previews"][lang] = {"error": str(exc)}

    try:
        mini = build_project(assets[:3], tracks, TEMPLATE_BMT_MINIMAL, captions=False)
        mini_bound = projects_for_batch(mini, langs[:1])
        if mini_bound:
            mini_bound[0].audio_duration = min(20.0, mini_bound[0].audio_duration or 20.0)
            from copy import deepcopy

            sample = deepcopy(mini_bound[0])
            sample.audio_duration = 12.0
            result = render_preview(sample, start=0.0)
            report["minimal_preview"] = result
    except Exception as exc:
        report["minimal_preview"] = {"error": str(exc)}

    dest = qa_dir / "phase3_report.json"
    dest.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("ready", "renders", "previews") if k in report}, indent=2))
    print(f"Wrote {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
