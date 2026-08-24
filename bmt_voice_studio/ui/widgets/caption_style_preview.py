"""Live caption type preview — size, fill, and stroke before generate."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QImage, QPixmap
from PySide6.QtWidgets import (
    QColorDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from bmt_voice_studio.ui.theme import SPACE
from bmt_voice_studio.ui.widgets.common import labeled_field
from bmt_voice_studio.video.captions import render_caption_preview
from bmt_voice_studio.video.models import (
    FONT_SIZE_DEFAULT,
    FONT_SIZE_MAX,
    FONT_SIZE_MIN,
    STROKE_WIDTH_DEFAULT,
    STROKE_WIDTH_MAX,
    STROKE_WIDTH_MIN,
    TEXT_COLOR_DEFAULT,
    STROKE_COLOR_DEFAULT,
    TextStyle,
)

TEXT_PRESETS = (
    ("#E89430", "Soft orange (Recommended)"),
    ("#FFFFFF", "White"),
    ("#F6E7C1", "Cream"),
    ("#D4A017", "Gold"),
)
STROKE_PRESETS = (
    ("#0A204A", "Dark blue (Recommended)"),
    ("#0A3A8C", "Navy"),
    ("#000000", "Black"),
    ("#FFFFFF", "White"),
)


def _swatch(color: str, tooltip: str) -> QPushButton:
    btn = QPushButton()
    btn.setObjectName("colorSwatch")
    btn.setFixedSize(26, 26)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setToolTip(tooltip)
    btn.setStyleSheet(
        f"QPushButton#colorSwatch {{ background-color: {color}; border: 1px solid #3D5573; "
        f"border-radius: 6px; min-height: 26px; max-height: 26px; padding: 0; }}"
        f"QPushButton#colorSwatch:hover {{ border-color: #D4A017; }}"
    )
    return btn


class CaptionStylePreview(QWidget):
    """Compact inspector: 9:16 sample plus color, stroke, and size controls."""

    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._text = TEXT_COLOR_DEFAULT
        self._stroke = STROKE_COLOR_DEFAULT
        self._sample = "Seek first the kingdom of God. All these things will be added to you."
        self._busy = False
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(SPACE.sm)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

        self.preview = QLabel()
        self.preview.setObjectName("captionPreviewStage")
        self.preview.setFixedSize(108, 192)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.preview, 0, Qt.AlignmentFlag.AlignHCenter)

        self.sp_size = QSpinBox()
        self.sp_size.setRange(FONT_SIZE_MIN, FONT_SIZE_MAX)
        self.sp_size.setValue(FONT_SIZE_DEFAULT)
        self.sp_size.setSuffix(" px")
        self.sp_size.setToolTip("Caption and overlay text size on the 1080×1920 video")
        root.addWidget(labeled_field("Font size", self.sp_size))

        self.sp_stroke = QSpinBox()
        self.sp_stroke.setRange(STROKE_WIDTH_MIN, STROKE_WIDTH_MAX)
        self.sp_stroke.setValue(STROKE_WIDTH_DEFAULT)
        self.sp_stroke.setSuffix(" px")
        self.sp_stroke.setToolTip("Outline thickness around the letters")
        root.addWidget(labeled_field("Stroke size", self.sp_stroke))

        root.addWidget(self._color_row("Text colour", TEXT_PRESETS, self._set_text_color, True))
        root.addWidget(self._color_row("Stroke colour", STROKE_PRESETS, self._set_stroke_color, False))

        self.sp_size.valueChanged.connect(self._emit)
        self.sp_stroke.valueChanged.connect(self._emit)
        self._refresh()

    def _color_row(self, label: str, presets: tuple, setter, text_side: bool) -> QWidget:
        wrap = QWidget()
        col = QVBoxLayout(wrap)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(4)
        title = QLabel(label)
        title.setObjectName("fieldLabel")
        col.addWidget(title)
        row = QHBoxLayout()
        row.setSpacing(4)
        for hex_color, name in presets:
            btn = _swatch(hex_color, f"{name} {label.lower()}")
            btn.clicked.connect(lambda _=False, c=hex_color, fn=setter: fn(c))
            row.addWidget(btn)
        more = QPushButton("…")
        more.setObjectName("tertiaryButton")
        more.setFixedWidth(32)
        more.setToolTip(f"Choose a custom {label.lower()}")
        more.clicked.connect(lambda: self._pick(text_side))
        row.addWidget(more)
        row.addStretch(1)
        col.addLayout(row)
        return wrap

    def _pick(self, text_side: bool) -> None:
        start = QColor(self._text if text_side else self._stroke)
        chosen = QColorDialog.getColor(start, self, "Choose colour")
        if chosen.isValid():
            hex_color = chosen.name().upper()
            if text_side:
                self._set_text_color(hex_color)
            else:
                self._set_stroke_color(hex_color)

    def _set_text_color(self, color: str) -> None:
        self._text = color
        self._emit()

    def _set_stroke_color(self, color: str) -> None:
        self._stroke = color
        self._emit()

    def _emit(self) -> None:
        if self._busy:
            return
        self._refresh()
        self.changed.emit()

    def set_sample(self, text: str) -> None:
        sample = (text or "").strip()
        if sample:
            self._sample = sample
            self._refresh()

    def style(self) -> TextStyle:
        return TextStyle(
            font_size=int(self.sp_size.value()),
            text_color=self._text,
            stroke_color=self._stroke,
            stroke_width=int(self.sp_stroke.value()),
        ).normalized()

    def set_style(self, style: TextStyle | None) -> None:
        ready = (style or TextStyle()).normalized()
        self._busy = True
        try:
            self.sp_size.setValue(ready.font_size)
            self.sp_stroke.setValue(ready.stroke_width)
            self._text = ready.text_color
            self._stroke = ready.stroke_color
        finally:
            self._busy = False
        self._refresh()

    def _refresh(self) -> None:
        try:
            frame = render_caption_preview(self.style(), self._sample, width=108, height=192)
            data = frame.convert("RGBA").tobytes("raw", "RGBA")
            qimg = QImage(data, frame.width, frame.height, QImage.Format.Format_RGBA8888)
            self.preview.setPixmap(QPixmap.fromImage(qimg.copy()))
        except Exception:
            self.preview.setText("Preview")
