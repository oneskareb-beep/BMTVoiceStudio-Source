"""Capture Video Maker Phase 4 UI at common desktop sizes."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["BMT_SKIP_RECOVERY"] = "1"
os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"
os.environ["QT_SCALE_FACTOR"] = "1"


def _seed_media(page) -> None:
    from bmt_voice_studio.video.media_probe import probe_media

    assets = ROOT / "qa_outputs" / "video_maker_phase4" / "assets"
    if not assets.is_dir():
        assets = ROOT / "qa_outputs" / "video_maker_phase3" / "assets"
    items = []
    for path in sorted(assets.glob("*")):
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".mp4"}:
            try:
                items.append(probe_media(str(path)))
            except Exception:
                pass
    if items:
        page.media.set_items(items)
        page._load_crop_panel()


def _grab(win, dest: Path, w: int, h: int, name: str) -> None:
    win.resize(w, h)
    win.show()
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app:
        app.processEvents()
    pix = win.grab()
    dest.mkdir(parents=True, exist_ok=True)
    pix.save(str(dest / f"{name}_{w}x{h}.png"))


def main() -> int:
    dest = ROOT / "qa_screenshots" / "video_maker_phase4"
    dest.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("LOCALAPPDATA", str(dest / "localapp"))

    from PySide6.QtWidgets import QApplication

    from bmt_voice_studio.config import settings as settings_mod
    from bmt_voice_studio.ui.main_window import MainWindow
    from bmt_voice_studio.ui.theme import apply_theme
    from bmt_voice_studio.video.models import QUEUE_COMPLETE, QUEUE_RENDERING, QUEUE_WAITING, TEMPLATE_BMT_CLASSIC
    from bmt_voice_studio.video.batch import QueueItem

    app = QApplication.instance() or QApplication(sys.argv)
    apply_theme(app, "dark")
    settings_mod._settings = None
    s = settings_mod.get_settings()
    s.first_run_complete = True
    s.daily_v11_welcome_seen = True
    settings_mod.save_settings(s)

    win = MainWindow()
    win.show()
    app.processEvents()
    sizes = [(1920, 1080), (1600, 900), (1366, 768)]

    def all_sizes(name: str) -> None:
        for w, h in sizes:
            _grab(win, dest, w, h, name)

    win.show_workspace("daily")
    app.processEvents()
    all_sizes("daily_audio")

    page = win.page_video
    win.show_workspace("video")
    app.processEvents()
    _seed_media(page)
    page.ed_topic.setText("Kingdom Priorities")
    all_sizes("video_maker_normal")

    for chk in page._lang_checks.values():
        chk.setEnabled(True)
        chk.setChecked(True)
    page._sync_generate_label()
    app.processEvents()
    all_sizes("four_language")

    page.lbl_preview_state.setText("Preview ready — embedded")
    app.processEvents()
    all_sizes("embedded_preview")

    if page.media.items():
        page.media.list.setCurrentRow(0)
        page._load_crop_panel()
    app.processEvents()
    all_sizes("crop")

    page.chk_captions.setChecked(True)
    page.cmb_caption_content.setCurrentIndex(1)
    app.processEvents()
    all_sizes("captions")

    page._queue = [
        QueueItem(language="en", label="English", status=QUEUE_RENDERING, percent=62),
        QueueItem(language="fr", label="French", status=QUEUE_WAITING),
        QueueItem(language="sw", label="Swahili", status=QUEUE_WAITING),
        QueueItem(language="pt", label="Portuguese", status=QUEUE_WAITING),
    ]
    page._refresh_queue_label()
    app.processEvents()
    all_sizes("render_queue")

    page._queue = [
        QueueItem(language="en", label="English", status=QUEUE_COMPLETE, output=r"C:\out\en.mp4"),
        QueueItem(language="fr", label="French", status=QUEUE_COMPLETE, output=r"C:\out\fr.mp4"),
        QueueItem(language="sw", label="Swahili", status=QUEUE_COMPLETE, output=r"C:\out\sw.mp4"),
        QueueItem(language="pt", label="Portuguese", status=QUEUE_COMPLETE, output=r"C:\out\pt.mp4"),
    ]
    page._show_batch_summary()
    app.processEvents()
    all_sizes("four_video_summary")

    page._set_template(TEMPLATE_BMT_CLASSIC, persist=False)
    win.close()
    print(f"Wrote screenshots to {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
