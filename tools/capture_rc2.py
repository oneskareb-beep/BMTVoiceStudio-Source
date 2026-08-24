"""Capture RC2 packaged/dev GUI screenshots including Data Folder and library dialog."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("BMT_SKIP_LIBRARY_DIALOG", "1")


def _grab(widget, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    pix = widget.grab()
    pix.save(str(dest))


def main() -> int:
    dest = ROOT / "qa_outputs" / "rc2" / "screenshots"
    dest.mkdir(parents=True, exist_ok=True)
    from PySide6.QtWidgets import QApplication

    from bmt_voice_studio.config.data_root import LibraryCandidate
    from bmt_voice_studio.config.settings import get_settings, save_settings
    from bmt_voice_studio.ui.dialogs.data_library import DataLibraryDialog
    from bmt_voice_studio.ui.dialogs.preferences import PreferencesDialog
    from bmt_voice_studio.ui.dialogs.troubleshooting import TroubleshootingDialog
    from bmt_voice_studio.ui.main_window import MainWindow
    from bmt_voice_studio.video.batch import QueueItem
    from bmt_voice_studio.video.models import QUEUE_COMPLETE, QUEUE_RENDERING, QUEUE_WAITING

    app = QApplication.instance() or QApplication([])
    s = get_settings()
    s.first_run_complete = True
    s.daily_v11_welcome_seen = True
    save_settings(s)

    win = MainWindow()
    win.show()
    sizes = [(1920, 1080), (1600, 900), (1366, 768)]
    for w, h in sizes:
        win.resize(w, h)
        win.show_workspace("daily")
        app.processEvents()
        _grab(win, dest / f"daily_{w}x{h}.png")
        win.show_workspace("video")
        app.processEvents()
        _grab(win, dest / f"video_maker_{w}x{h}.png")

    win.resize(1366, 768)
    win.show_workspace("video")
    page = win.page_video
    # scroll the inner area if present
    from PySide6.QtWidgets import QScrollArea, QAbstractSlider

    for sc in page.findChildren(QScrollArea):
        bar = sc.verticalScrollBar()
        bar.setValue(bar.maximum())
    app.processEvents()
    _grab(win, dest / "video_maker_1366x768_scrolled.png")

    page._queue = [
        QueueItem(language="en", label="English", status=QUEUE_RENDERING, percent=40),
        QueueItem(language="fr", label="French", status=QUEUE_WAITING),
        QueueItem(language="sw", label="Swahili", status=QUEUE_WAITING),
        QueueItem(language="pt", label="Portuguese", status=QUEUE_WAITING),
    ]
    page._refresh_queue_label()
    app.processEvents()
    _grab(win, dest / "four_language_queue.png")

    page._queue = [
        QueueItem(language="en", label="English", status=QUEUE_COMPLETE, output="en.mp4"),
        QueueItem(language="fr", label="French", status=QUEUE_COMPLETE, output="fr.mp4"),
        QueueItem(language="sw", label="Swahili", status=QUEUE_COMPLETE, output="sw.mp4"),
        QueueItem(language="pt", label="Portuguese", status=QUEUE_COMPLETE, output="pt.mp4"),
    ]
    page._show_batch_summary()
    app.processEvents()
    _grab(win, dest / "completed_render_summary.png")
    _grab(page.preview_player, dest / "embedded_preview.png")

    prefs = PreferencesDialog(win)
    prefs.show()
    app.processEvents()
    _grab(prefs, dest / "preferences_data_folder.png")
    prefs.close()

    trouble = TroubleshootingDialog(win)
    trouble.show()
    app.processEvents()
    _grab(trouble, dest / "troubleshooting_data_root.png")
    trouble.close()

    cands = [
        LibraryCandidate(path=Path(r"C:\Users\<user>\Documents\BMT Voice Studio"), kind="legacy", populated=True, file_count=12, label="Documents folder"),
        LibraryCandidate(path=Path(r"C:\Users\<user>\OneDrive\Documents\BMT Voice Studio"), kind="canonical", populated=True, file_count=4, label="Default Documents location"),
    ]
    dlg = DataLibraryDialog(cands, win)
    dlg.show()
    app.processEvents()
    _grab(dlg, dest / "multiple_library_dialog.png")
    dlg.close()
    win.close()
    print("WROTE", dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
