"""Simple Intro · Media · Outro timeline under the Video Maker preview."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

from bmt_voice_studio.ui.theme import COLOR, RADIUS


SEG_INTRO = "intro"
SEG_MEDIA = "media"
SEG_OUTRO = "outro"


class StudioTimeline(QWidget):
    """Clickable 9:16-project strip: branded intro, media body, branded outro."""

    segment_clicked = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("studioTimeline")
        self.setMinimumWidth(0)
        self.setFixedHeight(50)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Intro 10s · media · Outro 10s. Click a section to inspect it.")
        self._intro = True
        self._outro = True
        self._media_s = 20.0
        self._selected = SEG_MEDIA
        self._rects: dict[str, QRectF] = {}

    def set_segments(
        self,
        *,
        intro: bool = True,
        outro: bool = True,
        media_seconds: float = 20.0,
        selected: str = "",
    ) -> None:
        self._intro = bool(intro)
        self._outro = bool(outro)
        self._media_s = max(1.0, float(media_seconds or 20.0))
        if selected in {SEG_INTRO, SEG_MEDIA, SEG_OUTRO}:
            self._selected = selected
        self.update()

    def selected(self) -> str:
        return self._selected

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            pt = event.position()
            for kind, rect in self._rects.items():
                if rect.contains(pt):
                    self._selected = kind
                    self.segment_clicked.emit(kind)
                    self.update()
                    event.accept()
                    return
        super().mousePressEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pad = 8.0
        inner = QRectF(pad, 8.0, max(8.0, self.width() - pad * 2), 42.0)
        painter.setPen(QPen(QColor(COLOR.border), 1))
        painter.setBrush(QColor(COLOR.elevated))
        painter.drawRoundedRect(inner, RADIUS.medium, RADIUS.medium)

        intro_s = 10.0 if self._intro else 0.0
        outro_s = 10.0 if self._outro else 0.0
        media_s = self._media_s
        total = intro_s + media_s + outro_s
        gap = 3.0
        usable = inner.width() - gap * (int(self._intro) + int(self._outro))
        min_px = 52.0
        parts: list[tuple[str, float, str]] = []
        if self._intro:
            parts.append((SEG_INTRO, intro_s, "Intro 10s"))
        parts.append((SEG_MEDIA, media_s, "Media"))
        if self._outro:
            parts.append((SEG_OUTRO, outro_s, "Outro 10s"))

        weights = [max(min_px, usable * (sec / total)) for _, sec, _ in parts]
        scale = usable / max(1.0, sum(weights))
        x = inner.x()
        self._rects = {}
        font = QFont(self.font())
        font.setPointSize(10)
        font.setBold(True)
        painter.setFont(font)
        for (kind, _sec, label), weight in zip(parts, weights):
            w = weight * scale
            rect = QRectF(x, inner.y() + 2, w, inner.height() - 4)
            self._rects[kind] = rect
            selected = kind == self._selected
            if kind == SEG_MEDIA:
                fill = QColor(COLOR.blue_primary)
            else:
                fill = QColor(COLOR.gold)
            fill.setAlpha(210 if selected else 140)
            painter.setBrush(fill)
            painter.setPen(QPen(QColor(COLOR.gold if selected else COLOR.border_strong), 2 if selected else 1))
            painter.drawRoundedRect(rect, 6, 6)
            painter.setPen(QColor(COLOR.text_primary))
            painter.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), label)
            x += w + gap
        painter.end()
