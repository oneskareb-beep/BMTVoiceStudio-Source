"""Phase 4 QA: four-language batch, captions, Standard vs Faster, full Nature, probes."""

from __future__ import annotations

import json
import re
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
SHORT_SEC = 80.0


def _ffmpeg() -> str:
    from bmt_voice_studio.audio.ffmpeg_service import FFmpegService

    return FFmpegService().find()


def probe_mp4(ffmpeg: str, path: Path) -> dict:
    result = subprocess.run([ffmpeg, "-hide_banner", "-i", str(path)], capture_output=True, text=True)
    blob = (result.stderr or "") + (result.stdout or "")
    from bmt_voice_studio.video.media_probe import parse_ffmpeg_duration, parse_ffmpeg_video_size

    w, h = parse_ffmpeg_video_size(blob)
    audio_streams = len(re.findall(r"Audio:", blob, flags=re.IGNORECASE))
    fps = 0.0
    m = re.search(r"(\d+(?:\.\d+)?)\s*fps", blob)
    if m:
        fps = float(m.group(1))
    pix = ""
    pm = re.search(r"yuv\w+", blob)
    if pm:
        pix = pm.group(0)
    vbit = ""
    bm = re.search(r"bitrate:\s*(\d+)\s*kb/s", blob)
    if bm:
        vbit = f"{bm.group(1)} kb/s"
    return {
        "path": str(path),
        "exists": path.is_file(),
        "size_bytes": path.stat().st_size if path.is_file() else 0,
        "width": w,
        "height": h,
        "fps": fps,
        "duration": parse_ffmpeg_duration(blob),
        "video_codec": "h264" if ("h264" in blob.lower() or "avc" in blob.lower()) else "",
        "pixel_format": pix,
        "audio_codec": "aac" if "aac" in blob.lower() else "",
        "sample_rate": 48000 if "48000" in blob else (44100 if "44100" in blob else 0),
        "channels": 2 if "stereo" in blob.lower() else (1 if "mono" in blob.lower() else 0),
        "audio_stream_count": audio_streams,
        "bitrate": vbit,
        "h264": "h264" in blob.lower() or "avc" in blob.lower(),
        "aac": "aac" in blob.lower(),
        "fps30": fps >= 29.0,
    }


def clip_audio(ffmpeg: str, src: Path, dest: Path, seconds: float) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-i",
            str(src),
            "-t",
            f"{seconds:.2f}",
            "-acodec",
            "libmp3lame",
            "-b:a",
            "192k",
            str(dest),
        ],
        check=True,
        capture_output=True,
    )
    return dest


def ensure_assets(ffmpeg: str, folder: Path) -> list[Path]:
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "qa_video_maker_phase3", ROOT / "tools" / "qa_video_maker_phase3.py"
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod.ensure_assets(ffmpeg, folder)


def build_shared(assets: list[Path], tracks, *, captions: bool, speed: str, template: str):
    from bmt_voice_studio.resources import logo_path as packaged_logo_path
    from bmt_voice_studio.video.media_probe import probe_audio_duration, probe_media
    from bmt_voice_studio.video.models import VideoProject

    items = []
    for path in assets:
        try:
            item = probe_media(str(path))
            item.crop_x = 0.08
            item.zoom = 1.08
            if item.media_type == "video":
                item.trim_end = min(item.duration or 8.0, 8.0)
            items.append(item)
        except Exception:
            continue
    ready = [t for t in tracks if t.ready]
    first = ready[0] if ready else None
    audio_path = first.audio_path if first else ""
    audio_duration = first.audio_duration if first else 0.0
    if audio_path:
        try:
            probed = probe_audio_duration(audio_path)
            if probed > 0.4:
                audio_duration = probed
        except Exception:
            pass
    return VideoProject(
        devotional_date=DAY.isoformat(),
        language=first.language if first else "en",
        audio_path=audio_path,
        audio_duration=audio_duration,
        topic=first.topic if first else "",
        week_focus=first.week_focus if first else "",
        month_theme=first.month_theme if first else "",
        title=first.title if first else "",
        memory_verse=first.memory_verse if first else "",
        logo_path=str(packaged_logo_path() or ""),
        media_items=items,
        template_id=template,
        languages=list(tracks),
        selected_languages=[t.language for t in ready],
        show_captions=captions,
        skip_caption_header=True,
        render_speed=speed,
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


def render_preview(project, start: float = 12.0) -> dict:
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


def caption_sample(language: str, audio_duration: float) -> dict:
    from bmt_voice_studio.video.captions import captions_for_language

    cues = captions_for_language(DAY, language, audio_duration=audio_duration, skip_header=True)
    text = " ".join(c.text for c in cues[:8])
    return {
        "language": language,
        "cue_count": len(cues),
        "first_start": cues[0].start if cues else None,
        "sample": text[:240],
        "has_english_seek": "Seek first" in text,
        "encoding_ok": "Ã" not in text and "�" not in text,
    }


def main() -> int:
    from bmt_voice_studio.video.batch import projects_for_batch
    from bmt_voice_studio.video.discovery import language_tracks_for_day
    from bmt_voice_studio.video.history import upsert_video_entry
    from bmt_voice_studio.video.media_probe import probe_audio_duration
    from bmt_voice_studio.video.models import TEMPLATE_BMT_NATURE

    ffmpeg = _ffmpeg()
    qa_dir = ROOT / "qa_outputs" / "video_maker_phase4"
    assets_dir = qa_dir / "assets"
    phase3_assets = ROOT / "qa_outputs" / "video_maker_phase3" / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    if phase3_assets.is_dir():
        for src in phase3_assets.iterdir():
            dest = assets_dir / src.name
            if src.is_file() and not dest.exists():
                shutil.copy2(src, dest)
    assets = ensure_assets(ffmpeg, assets_dir)
    tracks = language_tracks_for_day(DAY)
    ready = [t.language for t in tracks if t.ready]
    report: dict = {
        "ffmpeg": ffmpeg,
        "assets": [str(p) for p in assets],
        "ready": ready,
        "discovered": {t.language: {"ready": t.ready, "topic": t.topic, "audio": t.audio_path} for t in tracks},
        "captions": {},
        "short_batch": {},
        "benchmark": {},
        "full_nature": {},
        "probes": {},
        "history_rows": 0,
    }
    if set(ready) < {"en", "fr", "sw", "pt"}:
        report["error"] = f"Need four ready languages, have {ready}"
        (qa_dir / "phase4_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 2

    clips_dir = qa_dir / "clips"
    short_tracks = []
    for t in tracks:
        if not t.ready:
            continue
        clip = clip_audio(ffmpeg, Path(t.audio_path), clips_dir / f"{t.language}_80s.mp3", SHORT_SEC)
        clone = type(t)(**{**t.__dict__, "audio_path": str(clip), "audio_duration": probe_audio_duration(clip)})
        short_tracks.append(clone)

    shared = build_shared(assets, short_tracks, captions=True, speed="faster", template=TEMPLATE_BMT_NATURE)
    bound = projects_for_batch(shared, ["en", "fr", "sw", "pt"])
    report["shared_media"] = [m.path for m in shared.media_items]
    report["bound_topics"] = {p.language: p.topic for p in bound}
    assert len(set(report["bound_topics"].values())) == 4

    for p in bound:
        dest = qa_dir / f"short_{p.language}_nature_captions.mp4"
        result = render_one(p, dest)
        report["short_batch"][p.language] = result
        report["probes"][dest.name] = probe_mp4(ffmpeg, dest)
        report["captions"][p.language] = caption_sample(p.language, SHORT_SEC)
        prev = render_preview(p, start=14.0)
        report["captions"][p.language]["preview"] = prev
        report["probes"][Path(prev["output"]).name] = probe_mp4(ffmpeg, Path(prev["output"]))
        upsert_video_entry(
            {
                "date": DAY.isoformat(),
                "language": p.language,
                "template": "BMT NATURE",
                "quality": "Standard 1080p",
                "duration": "01:20",
                "size": f"{Path(result['output']).stat().st_size / (1024 * 1024):.1f} MB",
                "status": "Complete",
                "output": result["output"],
            }
        )

    bench_src = next(p for p in bound if p.language == "en")
    for speed in ("standard", "faster"):
        proj = bench_src.bind_language("en")
        proj.render_speed = speed
        dest = qa_dir / f"bench_en_{speed}.mp4"
        result = render_one(proj, dest)
        probe = probe_mp4(ffmpeg, dest)
        elapsed = float(result["metrics"].get("wall_elapsed") or 0)
        dur = float(probe.get("duration") or SHORT_SEC)
        report["benchmark"][speed] = {
            "render_time": elapsed,
            "speed_factor": round(dur / elapsed, 2) if elapsed else 0,
            "output_size": probe["size_bytes"],
            "video_bitrate": probe["bitrate"],
            "quality_profile": "Standard (x264 medium, current CRF)" if speed == "standard" else "Faster (x264 veryfast, CRF +2)",
            "x264_preset": result["metrics"].get("x264_preset"),
            "probe": probe,
        }

    full_tracks = [t for t in tracks if t.language == "en" and t.ready]
    if full_tracks:
        full = build_shared(assets, tracks, captions=False, speed="faster", template=TEMPLATE_BMT_NATURE)
        full = full.bind_language("en")
        full.show_captions = False
        dest = qa_dir / "full_en_nature.mp4"
        result = render_one(full, dest)
        report["full_nature"] = result
        report["probes"][dest.name] = probe_mp4(ffmpeg, dest)

    from bmt_voice_studio.video.history import load_video_history

    rows = [r for r in load_video_history() if str(r.get("date")) == DAY.isoformat()]
    report["history_rows"] = len(rows)
    dest = qa_dir / "phase4_report.json"
    dest.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("ready", "bound_topics", "benchmark", "error") if k in report}, indent=2))
    print("WROTE", dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
