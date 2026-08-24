"""Capture Video Maker Phase 2 UI at common desktop sizes."""

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

    assets = ROOT / "qa_outputs" / "video_maker_phase1" / "assets"
    paths = [
        assets / "portrait_photo.png",
        assets / "landscape_photo.png",
        assets / "portrait_video.mp4",
        assets / "landscape_video.mp4",
    ]
    items = []
    for path in paths:
        if path.is_file():
            try:
                items.append(probe_media(path))
            except Exception:
                pass
    if items:
        page.media.set_items(items)
        page._load_crop_panel()


def main() -> int:
    dest = ROOT / "qa_screenshots" / "video_maker_phase2"
    dest.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("LOCALAPPDATA", str(dest / "localapp"))

    from PySide6.QtCore import QSize
    from PySide6.QtWidgets import QApplication

    from bmt_voice_studio import __version__
    from bmt_voice_studio.config import settings as settings_mod
    from bmt_voice_studio.ui.main_window import MainWindow
    from bmt_voice_studio.ui.theme import apply_theme
    from bmt_voice_studio.video.models import TEMPLATE_BMT_CLASSIC, TEMPLATE_BMT_NATURE

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
    page = win.page_video
    win.show_workspace("video")
    app.processEvents()
    _seed_media(page)
    page.ed_topic.setText("Kingdom Priorities")
    page.lbl_preview_state.setText("Still frame")
    app.processEvents()

    sizes = [(1920, 1080), (1600, 900), (1366, 768)]
    states = [
        ("classic", TEMPLATE_BMT_CLASSIC, False, "Still frame"),
        ("nature", TEMPLATE_BMT_NATURE, False, "Still frame"),
        ("crop", TEMPLATE_BMT_CLASSIC, True, "Still frame"),
        ("preview_ready", TEMPLATE_BMT_CLASSIC, True, "Preview ready — 12 seconds"),
    ]
    for state, template, select_media, preview_label in states:
        page._set_template(template, persist=False)
        if select_media and page.media.items():
            page.media.list.setCurrentRow(1 if len(page.media.items()) > 1 else 0)
            page._load_crop_panel()
            from PySide6.QtWidgets import QScrollArea

            for scroll in page.findChildren(QScrollArea):
                scroll.ensureWidgetVisible(page._crop_card, 20, 20)
        page.lbl_preview_state.setText(preview_label)
        if "Preview ready" in preview_label:
            page.btn_play_preview.setEnabled(True)
        app.processEvents()
        for w, h in sizes:
            win.resize(QSize(w, h))
            win.repaint()
            app.processEvents()
            pix = win.grab()
            out = dest / f"video_maker_{state}_{w}x{h}.png"
            pix.save(str(out))
            print("saved", out, pix.width(), pix.height())
    (dest / "capture_ok.txt").write_text(f"ok\n{__version__}\n", encoding="utf-8")
    win.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
