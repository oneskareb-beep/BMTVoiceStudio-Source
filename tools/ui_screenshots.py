"""Offscreen UI screenshots for Daily BMT visual QA (no production logic)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QSize  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QPlainTextEdit, QScrollArea  # noqa: E402

from bmt_voice_studio.config.paths import daily_v11_welcome_marker, first_run_marker  # noqa: E402
from bmt_voice_studio.config.settings import get_settings, save_settings  # noqa: E402
from bmt_voice_studio.ui.main_window import MainWindow  # noqa: E402
from bmt_voice_studio.ui.theme import apply_theme  # noqa: E402

SIZES = [(1920, 1080), (1600, 900), (1366, 768)]


def main() -> int:
    first_run_marker().write_text("ok", encoding="utf-8")
    daily_v11_welcome_marker().write_text("ok", encoding="utf-8")
    s = get_settings()
    s.first_run_complete = True
    s.daily_v11_welcome_seen = True
    save_settings(s)

    out = ROOT / "qa_screenshots"
    out.mkdir(exist_ok=True)

    app = QApplication(sys.argv)
    apply_theme(app, "dark")
    win = MainWindow()
    win._first_run_checked = True
    win.show()

    page = win.page_daily
    # Seed sample text so editors look production-ready in screenshots
    page.en_edit.setPlainText("Male intro. {Female response.} Male close.")
    page.fr_edit.setPlainText("Intro homme. {Réponse femme.} Conclusion homme.")
    page._refresh_validation()

    for w, h in SIZES:
        win.resize(QSize(w, h))
        win.repaint()
        app.processEvents()
        pix = win.grab()
        dest = out / f"daily_bmt_{w}x{h}.png"
        pix.save(str(dest))
        print("WROTE", dest, pix.size().width(), pix.size().height())

        edits = page.findChildren(QPlainTextEdit)
        titles = [t for t in page.findChildren(QLabel) if t.objectName() == "cardTitle"]
        areas = page.findChildren(QScrollArea)
        eh = [e.height() for e in edits]
        th = [(t.text(), t.height()) for t in titles[:8]]
        vmax = areas[0].verticalScrollBar().maximum() if areas else -1
        hmax = areas[0].horizontalScrollBar().maximum() if areas else -1
        gen = page.btn_generate
        print(
            "  MEASURE",
            f"{w}x{h}",
            "editors",
            eh,
            "titles",
            th,
            "generate_h",
            gen.height() if gen else None,
            "vscroll",
            vmax,
            "hscroll",
            hmax,
            "has_sidebar",
            hasattr(win, "nav_buttons"),
        )
        if areas:
            bar = areas[0].verticalScrollBar()
            bar.setValue(bar.maximum())
            app.processEvents()
            pix2 = win.grab()
            dest2 = out / f"daily_bmt_{w}x{h}_scrolled.png"
            pix2.save(str(dest2))
            print("WROTE", dest2)
            bar.setValue(0)
            app.processEvents()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
