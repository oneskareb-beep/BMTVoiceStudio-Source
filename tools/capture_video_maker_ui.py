"""Capture Video Maker UI at common desktop sizes (development, not packaged EXE)."""

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


def main() -> int:
    dest = ROOT / "qa_screenshots" / "video_maker_phase1"
    dest.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("LOCALAPPDATA", str(dest / "localapp"))

    from PySide6.QtCore import QSize
    from PySide6.QtWidgets import QApplication

    from bmt_voice_studio import __version__
    from bmt_voice_studio.config import settings as settings_mod
    from bmt_voice_studio.ui.main_window import MainWindow
    from bmt_voice_studio.ui.theme import apply_theme

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
    for mode, fn in (("daily", win.show_workspace),):
        pass
    for workspace, prefix in (("daily", "daily_audio"), ("video", "video_maker")):
        win.show_workspace("video" if workspace == "video" else "daily")
        app.processEvents()
        for w, h in sizes:
            win.resize(QSize(w, h))
            win.repaint()
            app.processEvents()
            pix = win.grab()
            out = dest / f"{prefix}_{w}x{h}.png"
            pix.save(str(out))
            print("saved", out, pix.width(), pix.height())
    (dest / "capture_ok.txt").write_text(f"ok\n{__version__}\n", encoding="utf-8")
    win.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
