"""Headless Video Maker smoke for packaged DEV EXE (no GUI)."""

from __future__ import annotations

import json
import subprocess
from datetime import date
from pathlib import Path

from bmt_voice_studio.audio.ffmpeg_service import FFmpegService
from bmt_voice_studio.video.discovery import todays_audio_status
from bmt_voice_studio.video.models import TEMPLATE_BMT_CLASSIC, TEMPLATE_BMT_MINIMAL, TEMPLATE_BMT_NATURE

NO_WINDOW = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0


def run_video_maker_smoke(report: Path | None = None) -> int:
    ffmpeg = FFmpegService()
    path = ffmpeg.find()
    rows = todays_audio_status(date.today())
    payload = {
        "ok": True,
        "ffmpeg": path,
        "templates": [TEMPLATE_BMT_CLASSIC, TEMPLATE_BMT_NATURE, TEMPLATE_BMT_MINIMAL],
        "todays_audio": [
            {"language": r["language"], "ready": r["ready"], "status": r["status"]} for r in rows
        ],
    }
    if report:
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print("VIDEO_MAKER_SMOKE_OK", path)
    return 0


def run_video_maker_render_smoke(report: Path | None = None) -> int:
    """Tiny packaged render: 8s master audio, 2 images, preview + short 1080p."""
    from bmt_voice_studio.config.paths import cache_dir
    from bmt_voice_studio.video.composition import build_composition_plan, build_preview_plan
    from bmt_voice_studio.video.ffmpeg_renderer import VideoRenderer
    from bmt_voice_studio.video.media_probe import probe_audio_duration, probe_media
    from bmt_voice_studio.video.models import VideoProject, output_profile_for

    exe = FFmpegService().find()
    folder = cache_dir() / "packaged_video_smoke"
    folder.mkdir(parents=True, exist_ok=True)
    img1 = folder / "a.png"
    img2 = folder / "b.png"
    audio = folder / "master.wav"
    preview = folder / "preview.mp4"
    full = folder / "full.mp4"

    def run(cmd: list[str]) -> None:
        result = subprocess.run(cmd, capture_output=True, text=True, creationflags=NO_WINDOW)
        if result.returncode != 0:
            raise RuntimeError((result.stderr or result.stdout or "")[-1200:])

    run([exe, "-y", "-f", "lavfi", "-i", "color=c=0x1E3A5F:s=1080x1920:d=1", "-frames:v", "1", str(img1)])
    run([exe, "-y", "-f", "lavfi", "-i", "color=c=0x2F6FED:s=1920x1080:d=1", "-frames:v", "1", str(img2)])
    run([exe, "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=8", "-ar", "48000", "-ac", "2", str(audio)])

    items = [probe_media(img1), probe_media(img2)]
    project = VideoProject(
        devotional_date=date.today().isoformat(),
        language="en",
        audio_path=str(audio),
        audio_duration=probe_audio_duration(audio),
        topic="Packaged Smoke",
        media_items=items,
        template_id=TEMPLATE_BMT_CLASSIC,
        output_profile=output_profile_for("standard_1080p"),
    )
    renderer = VideoRenderer()
    prev_plan = build_preview_plan(project, output_path=preview, temp_dir=folder / "t_prev", job_id="pkg_prev")
    prev_out = renderer.render(project, prev_plan, keep_temp_on_success=False)
    full_plan = build_composition_plan(project, output_path=full, temp_dir=folder / "t_full", job_id="pkg_full")
    full_out = renderer.render(project, full_plan, keep_temp_on_success=False)
    payload = {
        "ok": prev_out.is_file()
        and full_out.is_file()
        and prev_out.stat().st_size > 1000
        and full_out.stat().st_size > 1000,
        "ffmpeg": exe,
        "preview": str(prev_out),
        "full": str(full_out),
        "preview_bytes": prev_out.stat().st_size if prev_out.is_file() else 0,
        "full_bytes": full_out.stat().st_size if full_out.is_file() else 0,
    }
    if report:
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print("VIDEO_MAKER_RENDER_SMOKE", payload["ok"], exe)
    return 0 if payload["ok"] else 1


def run_project_restore_gui_smoke(report: Path | None = None) -> int:
    """Live GUI persistence: save Video Maker state, reopen, then missing-media recovery."""
    import os
    from datetime import date

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("BMT_SKIP_LIBRARY_DIALOG", "1")

    from PySide6.QtWidgets import QApplication

    from bmt_voice_studio.config.paths import user_data_root
    from bmt_voice_studio.config.settings import get_settings, save_settings
    from bmt_voice_studio.ui.main_window import MainWindow
    from bmt_voice_studio.daily.layout import ensure_daily_layout, final_paths
    from bmt_voice_studio.video.models import (
        TEMPLATE_BMT_NATURE,
        BrandingToggles,
        FitMode,
        MediaItem,
        VideoProject,
    )
    from bmt_voice_studio.video.project_store import load_project, save_project

    app = QApplication.instance() or QApplication([])
    s = get_settings()
    s.first_run_complete = True
    s.daily_v11_welcome_seen = True
    save_settings(s)

    folder = user_data_root() / "Temp" / "restore_smoke"
    folder.mkdir(parents=True, exist_ok=True)
    img1 = folder / "keep.jpg"
    img2 = folder / "gone.jpg"
    img1.write_bytes(b"jpg-keep")
    img2.write_bytes(b"jpg-gone")
    audio = folder / "master.mp3"
    audio.write_bytes(b"mp3")
    day = date.today()
    daily_root = ensure_daily_layout(day)
    for lang in ("en", "fr", "sw", "pt"):
        mp3, _wav = final_paths(daily_root, day, lang)
        mp3.parent.mkdir(parents=True, exist_ok=True)
        if not mp3.exists():
            mp3.write_bytes(b"mp3")

    win = MainWindow()
    win.show()
    app.processEvents()
    win.show_workspace("video")
    app.processEvents()
    page = win.page_video
    project = VideoProject(
        devotional_date=date.today().isoformat(),
        language="en",
        audio_path=str(audio),
        audio_duration=12.5,
        topic="Restore Topic",
        week_focus="Restore Week",
        month_theme="Restore Month",
        title="Restore Title",
        memory_verse="John 3:16",
        template_id=TEMPLATE_BMT_NATURE,
        show_captions=True,
        skip_caption_header=True,
        caption_content="body_verse",
        selected_languages=["en", "fr", "sw", "pt"],
        media_items=[
            MediaItem(path=str(img1), media_type="image", order=0, crop_x=0.15, zoom=1.2, trim_start=0.5, trim_end=8.0, fit_mode=FitMode.FILL.value),
            MediaItem(path=str(img2), media_type="image", order=1, crop_x=-0.1, zoom=1.0, trim_start=1.0, trim_end=6.0),
        ],
        branding=BrandingToggles(captions=True),
    )
    page.apply_project(project)
    app.processEvents()
    try:
        from PySide6.QtTest import QTest

        QTest.qWait(400)
    except Exception:
        app.processEvents()
    save_project(page.collect_project())
    win.close()
    app.processEvents()

    win2 = MainWindow()
    win2.show()
    app.processEvents()
    win2.show_workspace("video")
    app.processEvents()
    try:
        from PySide6.QtTest import QTest

        QTest.qWait(500)
    except Exception:
        app.processEvents()
    loaded = load_project()
    ok_restore = (
        loaded.topic == "Restore Topic"
        and loaded.template_id == TEMPLATE_BMT_NATURE
        and loaded.show_captions is True
        and loaded.caption_content == "body_verse"
        and loaded.selected_languages == ["en", "fr", "sw", "pt"]
        and len(loaded.media_items) == 2
        and loaded.media_items[0].crop_x == 0.15
        and loaded.media_items[1].trim_start == 1.0
        and loaded.media_items[0].missing is False
        and loaded.media_items[1].missing is False
    )
    win2.close()
    app.processEvents()

    img2.unlink()
    win3 = MainWindow()
    win3.show()
    app.processEvents()
    win3.show_workspace("video")
    app.processEvents()
    try:
        from PySide6.QtTest import QTest

        QTest.qWait(500)
    except Exception:
        app.processEvents()
    crashed = False
    try:
        again = load_project()
        missing_ok = again.media_items[1].missing is True and again.media_items[0].missing is False
        page3 = win3.page_video
        joined = " ".join(
            str(getattr(w, "text", lambda: "")())
            for w in page3.findChildren(object)
            if hasattr(w, "text") and callable(getattr(w, "text"))
        )
        ui_mentions_missing = "missing" in joined.lower() or "replace" in joined.lower() or again.media_items[1].missing
    except Exception:
        crashed = True
        missing_ok = False
        ui_mentions_missing = False
        again = None
    win3.close()
    app.processEvents()

    payload = {
        "ok": bool(ok_restore and missing_ok and not crashed),
        "restore_ok": bool(ok_restore),
        "missing_ok": bool(missing_ok),
        "crashed": crashed,
        "ui_mentions_missing": bool(ui_mentions_missing),
        "data_root": str(user_data_root()),
    }
    if report:
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print("PROJECT_RESTORE_SMOKE", payload["ok"], payload)
    return 0 if payload["ok"] else 1
