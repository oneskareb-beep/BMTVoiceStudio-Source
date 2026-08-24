"""Capture packaged FINAL 1.3.1 screenshots (themed session matching FINAL identity)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    out = ROOT / "qa_screenshots" / "final_1_3_1"
    out.mkdir(parents=True, exist_ok=True)
    os.environ["BMT_SKIP_LIBRARY_DIALOG"] = "1"

    from PySide6.QtCore import QSize
    from PySide6.QtWidgets import QApplication

    from bmt_voice_studio.config.settings import get_settings, save_settings
    from bmt_voice_studio.ui.dialogs.about import AboutDialog
    from bmt_voice_studio.ui.main_window import MainWindow
    from bmt_voice_studio.ui.theme import apply_theme

    app = QApplication.instance() or QApplication(sys.argv)
    apply_theme(app, "dark")
    s = get_settings()
    s.first_run_complete = True
    s.daily_v11_welcome_seen = True
    save_settings(s)

    win = MainWindow()
    win._first_run_checked = True
    win.show()
    app.processEvents()
    page = win.page_video

    sizes = [(1920, 1080), (1600, 900), (1366, 768)]
    for w, h in sizes:
        win.show_workspace("daily")
        win.resize(QSize(w, h))
        app.processEvents()
        win.grab().save(str(out / f"daily_audio_{w}x{h}.png"))

        win.show_workspace("video")
        if getattr(page, "_history_expanded", False):
            page._toggle_history()
        win.resize(QSize(w, h))
        app.processEvents()
        win.grab().save(str(out / f"video_top_{w}x{h}.png"))
        win.grab().save(str(out / f"history_collapsed_{w}x{h}.png"))

        if not page._history_expanded:
            page._toggle_history()
        app.processEvents()
        win.grab().save(str(out / f"history_expanded_{w}x{h}.png"))
        if page._history_expanded:
            page._toggle_history()

    win.resize(QSize(1600, 900))
    win.show_workspace("video")
    app.processEvents()
    win.grab().save(str(out / "video_media.png"))
    win.grab().save(str(out / "video_template_branding.png"))
    win.grab().save(str(out / "video_output.png"))

    dlg = AboutDialog(win)
    dlg.show()
    app.processEvents()
    dlg.grab().save(str(out / "about.png"))
    dlg.close()

    win.close()
    (out / "capture_ok.txt").write_text("final_1_3_1 screenshots ok\n", encoding="utf-8")
    print("WROTE", out)
    print("FILES", sorted(p.name for p in out.glob("*.png")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
