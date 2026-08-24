"""Top-of-window generation progress — long bar + live status text."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QProgressBar, QVBoxLayout, QWidget

from bmt_voice_studio.ui.theme import SPACE


class JobProgressStrip(QWidget):
    """Full-width percent bar shown under the app header during audio/video jobs."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("jobProgressStrip")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACE.page_margin, 8, SPACE.page_margin, 10)
        layout.setSpacing(4)
        self.lbl = QLabel("Ready")
        self.lbl.setObjectName("jobProgressLabel")
        self.lbl.setWordWrap(False)
        self.lbl.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.bar = QProgressBar()
        self.bar.setObjectName("jobProgressBar")
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.bar.setTextVisible(True)
        self.bar.setFormat("%p%")
        self.bar.setMinimumHeight(22)
        layout.addWidget(self.lbl)
        layout.addWidget(self.bar)
        self.set_idle()

    def set_idle(self) -> None:
        self.bar.setValue(0)
        self.bar.setProperty("state", "")
        self.bar.style().unpolish(self.bar)
        self.bar.style().polish(self.bar)
        self.lbl.setText("Ready")
        self.hide()

    def set_progress(self, percent: int, message: str) -> None:
        self.show()
        pct = max(0, min(100, int(percent)))
        self.bar.setValue(pct)
        text = (message or "").strip() or "Working…"
        self.lbl.setText(f"{text}  ·  {pct}%")
        # Keep the percent visible on the bar itself, with a short stage hint.
        hint = text if len(text) <= 36 else text[:33] + "…"
        self.bar.setFormat(f"{pct}%  {hint}")
        self.bar.setProperty("state", "success" if pct >= 100 else "")
        self.bar.style().unpolish(self.bar)
        self.bar.style().polish(self.bar)

    def set_error(self, message: str) -> None:
        self.show()
        self.bar.setProperty("state", "error")
        self.bar.style().unpolish(self.bar)
        self.bar.style().polish(self.bar)
        self.lbl.setText((message or "Generation failed").strip())
