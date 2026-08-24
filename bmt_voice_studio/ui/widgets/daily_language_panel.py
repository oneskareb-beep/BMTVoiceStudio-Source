"""Reusable Daily BMT language script panel (English / French today; Swahili later)."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from bmt_voice_studio.core.parser import parse_speaker_script_source
from bmt_voice_studio.daily.language_config import LanguageProductionConfig
from bmt_voice_studio.daily.validate import validate_daily_script
from bmt_voice_studio.ui.widgets.common import card


class DailyLanguagePanel(QWidget):
    """One language production panel: editor, status, counts, Paste/Clear/Validate."""

    text_changed = Signal()
    validate_requested = Signal()

    def __init__(self, config: LanguageProductionConfig, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.edit = QPlainTextEdit()
        self.edit.setPlaceholderText(config.script_placeholder)
        self.edit.setMinimumHeight(300)
        self.edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.status = QLabel("EMPTY")
        self.status.setMinimumHeight(22)
        self.status.setMaximumHeight(24)
        self.status.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        self.counts = QLabel("Segments: 0   Male: 0   Female: 0")
        self.counts.setObjectName("appSubtitle")
        self.counts.setMinimumHeight(18)
        self.counts.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        box, lay = card(config.display_name_local, "")
        box.setMinimumHeight(460)
        box.setMinimumWidth(0)
        box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        lay.addWidget(self.edit)
        lay.addWidget(self.status)
        lay.addWidget(self.counts)
        lay.addWidget(self._toolbar())

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(box)
        self._frame = box

        self.edit.textChanged.connect(self.text_changed.emit)

    def _toolbar(self) -> QWidget:
        w = QWidget()
        row = QHBoxLayout(w)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        paste = QPushButton("Paste")
        paste.setObjectName("secondaryButton")
        clear = QPushButton("Clear")
        clear.setObjectName("tertiaryButton")
        validate = QPushButton("Validate")
        preview = QPushButton("Preview Segments")
        preview.setObjectName("secondaryButton")
        for b in (paste, clear, validate, preview):
            b.setMinimumWidth(0)
            row.addWidget(b)
        row.addStretch(1)
        paste.clicked.connect(self.paste_clipboard)
        clear.clicked.connect(self.clear_text)
        validate.clicked.connect(self.validate_requested.emit)
        preview.clicked.connect(self.preview_segments)
        return w

    def paste_clipboard(self) -> None:
        self.edit.setPlainText(QGuiApplication.clipboard().text())

    def clear_text(self) -> None:
        self.edit.clear()

    def text(self) -> str:
        return self.edit.toPlainText()

    def set_text(self, value: str) -> None:
        self.edit.setPlainText(value or "")

    def refresh_validation(self) -> object:
        result = validate_daily_script(self.text())
        self.counts.setText(
            f"Segments: {result.segment_count}   Male: {result.male_count}   Female: {result.female_count}"
        )
        self.set_status_label(result.label)
        return result

    def set_status_label(self, status: str) -> None:
        from bmt_voice_studio.ui.theme import set_badge_state

        display = "INVALID" if status == "SCRIPT ERROR" else status
        self.status.setText(display)
        key = (display or "WAITING").upper()
        state_map = {
            "READY": "ready",
            "COMPLETE": "complete",
            "SCRIPT ERROR": "error",
            "INVALID": "error",
            "FAILED": "failed",
            "WARNING": "warning",
            "EMPTY": "empty",
            "WAITING": "waiting",
            "GENERATING": "rendering",
            "VALIDATING": "rendering",
            "PROCESSING": "rendering",
        }
        set_badge_state(self.status, state_map.get(key, "waiting"))

    def preview_segments(self) -> None:
        parsed = parse_speaker_script_source(self.text())
        if not parsed.ok:
            QMessageBox.warning(
                self,
                f"{self.config.display_name} script",
                "\n".join(e.message for e in parsed.errors) or "Script is invalid.",
            )
            return
        lines: list[str] = []
        from bmt_voice_studio.core.text_prepare import suppress_spoken_list_markers

        lang = self.config.language_id
        for s in parsed.segments:
            if lang in {"en", "fr"}:
                spoken = suppress_spoken_list_markers(s.text, language=lang)
                src = s.text[:160] + ("…" if len(s.text) > 160 else "")
                tts = spoken[:160] + ("…" if len(spoken) > 160 else "")
                lines.append(f"{s.label}\nSOURCE:\n{src}\nTTS:\n{tts}")
            else:
                lines.append(
                    f"{s.label}\n{s.text[:180]}{'…' if len(s.text) > 180 else ''}"
                )
        QMessageBox.information(self, "Segments", "\n\n".join(lines) or "No segments")
