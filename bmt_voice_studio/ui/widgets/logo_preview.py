"""Logo picker with a live preview on a cream card."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from bmt_voice_studio.resources import logo_path as packaged_logo_path
from bmt_voice_studio.ui.theme import SPACE


class LogoPreviewPicker(QWidget):
    """Choose a PNG logo and see it immediately on the intro-card cream background."""

    changed = Signal()
    choose_requested = Signal()
    packaged_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._path = ""
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(SPACE.sm)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

        self.preview = QLabel()
        self.preview.setObjectName("logoPreviewCard")
        self.preview.setFixedSize(140, 80)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setScaledContents(False)
        root.addWidget(self.preview, 0, Qt.AlignmentFlag.AlignLeft)

        self.lbl_name = QLabel("Packaged BMT logo")
        self.lbl_name.setObjectName("valueLabel")
        self.lbl_name.setWordWrap(True)
        self.lbl_name.setMinimumWidth(0)
        self.lbl_hint = QLabel("Transparent PNG looks best on the intro card.")
        self.lbl_hint.setObjectName("taskLabel")
        self.lbl_hint.setWordWrap(True)
        self.lbl_hint.setMinimumWidth(0)
        root.addWidget(self.lbl_name)
        root.addWidget(self.lbl_hint)

        self.btn_choose = QPushButton("Choose Logo…")
        self.btn_choose.setObjectName("tertiaryButton")
        self.btn_packaged = QPushButton("Use packaged")
        self.btn_packaged.setObjectName("tertiaryButton")
        for btn in (self.btn_choose, self.btn_packaged):
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            root.addWidget(btn)

        self.btn_choose.clicked.connect(self.choose_requested.emit)
        self.btn_packaged.clicked.connect(self.packaged_requested.emit)

    def set_logo_path(self, path: str) -> None:
        self._path = str(path or "")
        self._refresh()

    def logo_path(self) -> str:
        return self._path

    def _refresh(self) -> None:
        custom = Path(self._path) if self._path else None
        if custom and custom.is_file():
            source = custom
            self.lbl_name.setText(custom.name)
            self.lbl_hint.setText("Custom logo — used on intro, outro, and overlays.")
        else:
            packaged = packaged_logo_path()
            source = packaged if packaged and packaged.is_file() else None
            self.lbl_name.setText("Packaged BMT logo")
            self.lbl_hint.setText("Choose a PNG to replace the packaged logo.")
        self.preview.setPixmap(self._preview_pixmap(source))

    def _preview_pixmap(self, path: Path | None) -> QPixmap:
        card = QPixmap(self.preview.size() * max(1, int(self.devicePixelRatioF())))
        card.setDevicePixelRatio(self.devicePixelRatioF())
        card.fill(QColor("#F3E6C4"))
        painter = QPainter(card)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        if path and path.is_file():
            pix = QPixmap(str(path))
            if not pix.isNull():
                inner = self.preview.size()
                scaled = pix.scaled(
                    int((inner.width() - 16) * card.devicePixelRatio()),
                    int((inner.height() - 16) * card.devicePixelRatio()),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                scaled.setDevicePixelRatio(card.devicePixelRatio())
                x = int((card.width() - scaled.width()) / 2)
                y = int((card.height() - scaled.height()) / 2)
                painter.drawPixmap(x, y, scaled)
        else:
            painter.setPen(QColor("#5C4A2A"))
            painter.drawText(card.rect(), Qt.AlignmentFlag.AlignCenter, "No logo")
        painter.end()
        return card
