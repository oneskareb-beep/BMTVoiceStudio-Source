"""One-time Daily BMT welcome."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from bmt_voice_studio.config.paths import daily_v11_welcome_marker
from bmt_voice_studio.config.settings import get_settings, save_settings
from bmt_voice_studio.resources import load_app_icon, logo_label


class DailyWelcomeDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Welcome — Daily BMT")
        self.setMinimumWidth(480)
        icon = load_app_icon()
        if not icon.isNull():
            self.setWindowIcon(icon)
        self.choice = "daily"
        layout = QVBoxLayout(self)
        layout.addWidget(logo_label(max_width=200, max_height=120, parent=self))
        title = QLabel("DAILY BMT PRODUCTION")
        title.setObjectName("appTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        body = QLabel(
            "Produce English and French devotionals from one screen.\n"
            "Select the date, paste both scripts, and click GENERATE TODAY'S DEVOTIONAL."
        )
        body.setWordWrap(True)
        body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(body)
        row = QHBoxLayout()
        btn_daily = QPushButton("CONTINUE")
        btn_daily.setObjectName("primaryButton")
        row.addStretch(1)
        row.addWidget(btn_daily)
        layout.addLayout(row)
        btn_daily.clicked.connect(self._daily)

    def _mark(self) -> None:
        daily_v11_welcome_marker().write_text("ok", encoding="utf-8")
        s = get_settings()
        s.daily_v11_welcome_seen = True
        save_settings(s)

    def _daily(self) -> None:
        self.choice = "daily"
        self._mark()
        self.accept()
