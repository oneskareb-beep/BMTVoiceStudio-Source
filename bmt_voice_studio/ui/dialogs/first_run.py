"""First-run dependency self-check dialog."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from bmt_voice_studio.config.paths import first_run_marker
from bmt_voice_studio.config.settings import get_settings, save_settings
from bmt_voice_studio.resources import load_app_icon, logo_label
from bmt_voice_studio.workers.generation import HealthController


class FirstRunDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Welcome — BMT Voice Studio")
        self.setMinimumSize(560, 480)
        icon = load_app_icon()
        if not icon.isNull():
            self.setWindowIcon(icon)
        layout = QVBoxLayout(self)
        layout.addWidget(logo_label(max_width=240, max_height=150, parent=self))
        title = QLabel("Welcome to BMT Voice Studio")
        title.setObjectName("appTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        brand = QLabel("BBNet — Believers Businessmen Network")
        brand.setObjectName("appSubtitle")
        brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(brand)
        hint = QLabel(
            "Running a quick dependency self-check.\n"
            "Daily BMT uses Edge TTS for approved English and French voices."
        )
        hint.setWordWrap(True)
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(hint)
        self.status = QTextEdit()
        self.status.setReadOnly(True)
        layout.addWidget(self.status)
        row = QHBoxLayout()
        self.btn_continue = QPushButton("Continue")
        self.btn_continue.setObjectName("primaryButton")
        self.btn_continue.setEnabled(False)
        row.addStretch(1)
        row.addWidget(self.btn_continue)
        layout.addLayout(row)
        self.btn_continue.clicked.connect(self._finish)
        self._open_voices = False
        self._health = HealthController()
        self._health.signals.finished.connect(self._on_health)
        self._health.signals.error.connect(lambda h, t: self.status.append(h))
        self.status.append("Checking services…")
        self._health.start()

    def _on_health(self, status: dict) -> None:
        self.status.clear()
        self.status.append(f"Internet: {status.get('internet', '?')}")
        self.status.append(f"Edge TTS: {status.get('edge', '?')}")
        self.status.append(f"Piper Offline: {status.get('piper', '?')}")
        self.status.append(f"FFmpeg: {status.get('ffmpeg', '?')}")
        self.status.append("")
        if "AVAILABLE" in str(status.get("edge", "")):
            self.status.append("Edge TTS is ready for Daily BMT production.")
        else:
            self.status.append("Edge TTS is currently unavailable — check your network connection.")
        self.btn_continue.setEnabled(True)

    def _finish(self) -> None:
        first_run_marker().write_text("ok", encoding="utf-8")
        settings = get_settings()
        settings.first_run_complete = True
        save_settings(settings)
        self.accept()

    @property
    def open_voice_manager(self) -> bool:
        return False
