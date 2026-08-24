"""Reusable UI widgets."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from bmt_voice_studio.audio.player import AudioPlayer
from bmt_voice_studio.ui.theme import HEIGHT, SPACE, set_badge_state


class ScrollPage(QWidget):
    """Inner page for QScrollArea — keep vertical minimum, allow width to match viewport."""

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return False

    def minimumSizeHint(self):
        lay = self.layout()
        if lay is None:
            return super().minimumSizeHint()
        ms = lay.minimumSize()
        return QSize(0, ms.height())


def card(title: str, hint: str = "") -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("card")
    frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(SPACE.card_pad_x, SPACE.card_pad_y, SPACE.card_pad_x, SPACE.card_pad_y)
    layout.setSpacing(SPACE.card_gap)
    t = QLabel(title)
    t.setObjectName("cardTitle")
    t.setWordWrap(True)
    t.setMinimumWidth(0)
    t.setMinimumHeight(22)
    t.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
    t.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
    layout.addWidget(t)
    if hint:
        h = QLabel(hint)
        h.setObjectName("cardHint")
        h.setWordWrap(True)
        h.setMinimumWidth(0)
        h.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        layout.addWidget(h)
    return frame, layout


def field_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("fieldLabel")
    return lbl


def meta_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("metaLabel")
    return lbl


def value_label(text: str = "—") -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("valueLabel")
    lbl.setWordWrap(True)
    return lbl


def status_badge(text: str = "Waiting", state: str = "waiting") -> QLabel:
    lbl = QLabel(text)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    set_badge_state(lbl, state)
    return lbl


def primary_button(text: str) -> QPushButton:
    btn = QPushButton(text)
    btn.setObjectName("primaryButton")
    btn.setMinimumHeight(HEIGHT.primary)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    return btn


def secondary_button(text: str) -> QPushButton:
    btn = QPushButton(text)
    btn.setObjectName("secondaryButton")
    btn.setMinimumHeight(HEIGHT.standard)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    return btn


def tertiary_button(text: str) -> QPushButton:
    btn = QPushButton(text)
    btn.setObjectName("tertiaryButton")
    btn.setMinimumHeight(HEIGHT.small)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    return btn


def toolbar_icon(kind: str, *, color: str = "#E8EEF6", size: int = 18) -> QIcon:
    """Flat 18px glyphs for compact Video Maker chrome (dark-theme safe)."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    c = QColor(color)
    pen = QPen(c, 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    s = float(size)
    m = s * 0.18
    if kind == "play":
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(c)
        p.drawPolygon(
            QPolygonF([QPointF(s * 0.32, m), QPointF(s * 0.32, s - m), QPointF(s - m * 0.7, s * 0.5)])
        )
    elif kind == "pause":
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(c)
        p.drawRoundedRect(QRectF(s * 0.28, m, s * 0.16, s - 2 * m), 1.2, 1.2)
        p.drawRoundedRect(QRectF(s * 0.56, m, s * 0.16, s - 2 * m), 1.2, 1.2)
    elif kind == "restart":
        p.drawArc(QRectF(m, m, s - 2 * m, s - 2 * m), 40 * 16, 280 * 16)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(c)
        p.drawPolygon(
            QPolygonF(
                [
                    QPointF(s * 0.72, m * 0.55),
                    QPointF(s - m * 0.2, s * 0.38),
                    QPointF(s * 0.52, s * 0.40),
                ]
            )
        )
    elif kind == "crop":
        p.drawLine(QPointF(m, m * 1.6), QPointF(s * 0.55, m * 1.6))
        p.drawLine(QPointF(m * 1.6, m), QPointF(m * 1.6, s * 0.55))
        p.drawLine(QPointF(s - m, s - m * 1.6), QPointF(s * 0.45, s - m * 1.6))
        p.drawLine(QPointF(s - m * 1.6, s - m), QPointF(s - m * 1.6, s * 0.45))
        p.drawRect(QRectF(s * 0.28, s * 0.28, s * 0.44, s * 0.44))
    elif kind == "open":
        p.drawRoundedRect(QRectF(m, s * 0.32, s - 2 * m, s * 0.50), 1.5, 1.5)
        p.drawLine(QPointF(m * 1.4, s * 0.32), QPointF(s * 0.42, s * 0.32))
        p.drawLine(QPointF(s * 0.42, s * 0.32), QPointF(s * 0.50, s * 0.18))
        p.drawLine(QPointF(s * 0.50, s * 0.18), QPointF(s - m * 1.1, s * 0.18))
        p.drawLine(QPointF(s - m * 1.1, s * 0.18), QPointF(s - m, s * 0.32))
    elif kind == "fill":
        p.setBrush(c)
        p.drawRoundedRect(QRectF(m, m, s - 2 * m, s - 2 * m), 2.0, 2.0)
    elif kind == "fit":
        p.drawRoundedRect(QRectF(m, m, s - 2 * m, s - 2 * m), 2.0, 2.0)
        p.drawRect(QRectF(s * 0.32, s * 0.28, s * 0.36, s * 0.44))
    elif kind == "smart":
        p.drawEllipse(QRectF(m * 1.2, m * 1.2, s - 2.4 * m, s - 2.4 * m))
        p.drawEllipse(QRectF(s * 0.38, s * 0.38, s * 0.24, s * 0.24))
        p.drawLine(QPointF(s * 0.5, m * 0.6), QPointF(s * 0.5, s * 0.28))
        p.drawLine(QPointF(s * 0.5, s - m * 0.6), QPointF(s * 0.5, s * 0.72))
        p.drawLine(QPointF(m * 0.6, s * 0.5), QPointF(s * 0.28, s * 0.5))
        p.drawLine(QPointF(s - m * 0.6, s * 0.5), QPointF(s * 0.72, s * 0.5))
    elif kind == "up":
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(c)
        p.drawPolygon(
            QPolygonF([QPointF(s * 0.5, m), QPointF(s - m, s - m * 1.1), QPointF(m, s - m * 1.1)])
        )
    elif kind == "down":
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(c)
        p.drawPolygon(QPolygonF([QPointF(s * 0.5, s - m), QPointF(m, m * 1.1), QPointF(s - m, m * 1.1)]))
    elif kind == "left":
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(c)
        p.drawPolygon(
            QPolygonF([QPointF(m, s * 0.5), QPointF(s - m * 1.1, m), QPointF(s - m * 1.1, s - m)])
        )
    elif kind == "right":
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(c)
        p.drawPolygon(QPolygonF([QPointF(s - m, s * 0.5), QPointF(m * 1.1, m), QPointF(m * 1.1, s - m)]))
    elif kind == "reset":
        p.drawArc(QRectF(m * 1.1, m * 1.1, s - 2.2 * m, s - 2.2 * m), 50 * 16, 260 * 16)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(c)
        p.drawPolygon(
            QPolygonF(
                [
                    QPointF(s * 0.70, m * 0.7),
                    QPointF(s - m * 0.15, s * 0.40),
                    QPointF(s * 0.50, s * 0.42),
                ]
            )
        )
    elif kind == "zoom_out":
        p.drawLine(QPointF(m * 1.4, s * 0.5), QPointF(s - m * 1.4, s * 0.5))
    elif kind == "zoom_in":
        p.drawLine(QPointF(m * 1.4, s * 0.5), QPointF(s - m * 1.4, s * 0.5))
        p.drawLine(QPointF(s * 0.5, m * 1.4), QPointF(s * 0.5, s - m * 1.4))
    elif kind == "add":
        p.drawEllipse(QRectF(m * 0.6, m * 0.6, s - 1.2 * m, s - 1.2 * m))
        p.drawLine(QPointF(s * 0.5, m * 1.6), QPointF(s * 0.5, s - m * 1.6))
        p.drawLine(QPointF(m * 1.6, s * 0.5), QPointF(s - m * 1.6, s * 0.5))
    elif kind == "replace":
        p.drawRoundedRect(QRectF(m, m * 1.15, s * 0.52, s * 0.52), 1.4, 1.4)
        p.drawRoundedRect(QRectF(s * 0.36, s * 0.32, s * 0.52, s * 0.52), 1.4, 1.4)
    elif kind == "trash":
        p.drawLine(QPointF(m * 1.15, m * 1.7), QPointF(s - m * 1.15, m * 1.7))
        p.drawLine(QPointF(s * 0.38, m * 0.95), QPointF(s * 0.62, m * 0.95))
        p.drawLine(QPointF(s * 0.32, m * 1.7), QPointF(s * 0.38, s - m * 0.9))
        p.drawLine(QPointF(s * 0.68, m * 1.7), QPointF(s * 0.62, s - m * 0.9))
        p.drawLine(QPointF(s * 0.38, s - m * 0.9), QPointF(s * 0.62, s - m * 0.9))
        p.drawLine(QPointF(s * 0.5, m * 2.05), QPointF(s * 0.5, s - m * 1.25))
    p.end()
    return QIcon(pm)


def icon_button(
    tooltip: str,
    kind: str,
    *,
    checkable: bool = False,
    color: str | None = None,
) -> QToolButton:
    """Icon-only tool button — no card chrome, tooltip keeps the old label."""
    btn = QToolButton()
    btn.setObjectName("iconButton")
    btn.setAutoRaise(True)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
    btn.setIcon(toolbar_icon(kind, color=color or "#E8EEF6"))
    btn.setIconSize(QSize(18, 18))
    btn.setFixedSize(32, 32)
    btn.setToolTip(tooltip)
    btn.setAccessibleName(tooltip)
    btn.setCheckable(checkable)
    btn.setText("")
    return btn


def danger_button(text: str) -> QPushButton:
    btn = QPushButton(text)
    btn.setObjectName("dangerButton")
    btn.setMinimumHeight(HEIGHT.standard)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    return btn


def labeled_field(label: str, widget: QWidget, stretch: int = 1) -> QWidget:
    wrap = QWidget()
    col = QVBoxLayout(wrap)
    col.setContentsMargins(0, 0, 0, 0)
    col.setSpacing(SPACE.xs)
    col.addWidget(field_label(label))
    col.addWidget(widget)
    wrap.setSizePolicy(
        QSizePolicy.Policy.Expanding if stretch else QSizePolicy.Policy.Maximum,
        QSizePolicy.Policy.Fixed,
    )
    return wrap


def wrap_in_scroll(inner: QWidget) -> QScrollArea:
    inner.setMinimumWidth(0)
    inner.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Minimum)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    scroll.setWidget(inner)
    scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    return scroll


def ellipsize_path(path: str, keep: int = 42) -> str:
    text = (path or "").strip()
    if len(text) <= keep:
        return text
    return "…" + text[-(keep - 1) :]


class Toast(QLabel):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("toast")
        self.setStyleSheet(
            "QLabel#toast { background:#1E3A5F; color:white; padding:10px 14px; "
            "border-radius:8px; border:1px solid #3D6FB8; }"
        )
        self.hide()

    def show_message(self, text: str, ms: int = 3200) -> None:
        self.setText(text)
        self.adjustSize()
        if self.parent():
            p = self.parent().rect()
            self.move(p.width() - self.width() - 24, 24)
        self.show()
        self.raise_()
        from PySide6.QtCore import QTimer

        QTimer.singleShot(ms, self.hide)


class AudioPlayerBar(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.player = AudioPlayer(self)
        self._path = ""
        self.setMinimumHeight(64)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        frame = QFrame(self)
        frame.setObjectName("playerFrame")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(frame)

        root = QHBoxLayout(frame)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(10)

        self.cover = QLabel()
        self.cover.setFixedSize(36, 64)
        self.cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover.setToolTip("Locked 9:16 artwork")
        self.cover.hide()
        root.addWidget(self.cover)

        self.btn_play = secondary_button("Play")
        self.btn_pause = tertiary_button("Pause")
        self.btn_stop = tertiary_button("Stop")
        for b in (self.btn_play, self.btn_pause, self.btn_stop):
            b.setMinimumHeight(HEIGHT.standard)
            b.setMinimumWidth(72)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.slider.setMinimumHeight(22)

        self.lbl_time = QLabel("0:00 / 0:00")
        self.lbl_time.setObjectName("metaLabel")
        self.lbl_time.setMinimumWidth(92)
        self.lbl_time.setAlignment(Qt.AlignmentFlag.AlignCenter)

        vol_lbl = QLabel("Vol")
        vol_lbl.setObjectName("fieldLabel")
        self.vol = QSlider(Qt.Orientation.Horizontal)
        self.vol.setRange(0, 100)
        self.vol.setValue(90)
        self.vol.setMinimumWidth(90)
        self.vol.setMaximumWidth(120)

        root.addWidget(self.btn_play)
        root.addWidget(self.btn_pause)
        root.addWidget(self.btn_stop)
        root.addWidget(self.slider, 1)
        root.addWidget(self.lbl_time)
        root.addWidget(vol_lbl)
        root.addWidget(self.vol)

        self.btn_play.clicked.connect(self.player.play)
        self.btn_pause.clicked.connect(self.player.pause)
        self.btn_stop.clicked.connect(self.player.stop)
        self.slider.sliderMoved.connect(self.player.seek)
        self.vol.valueChanged.connect(lambda v: self.player.set_volume(v / 100.0))
        self.player.position_changed.connect(self._on_pos)
        self.player.duration_changed.connect(self._on_dur)
        self.player.error_occurred.connect(lambda e: None)

    def load(self, path: str | Path) -> None:
        self._path = str(path)
        self.player.load(path)
        self._load_cover(Path(path))

    def _load_cover(self, path: Path) -> None:
        pix = QPixmap()
        if path.suffix.lower() == ".mp3" and path.is_file():
            try:
                from mutagen.id3 import ID3

                tags = ID3(str(path))
                for apic in tags.getall("APIC"):
                    pix.loadFromData(apic.data)
                    break
            except Exception:
                pix = QPixmap()
        if pix.isNull():
            self.cover.hide()
            return
        self.cover.setPixmap(
            pix.scaled(self.cover.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        )
        self.cover.show()

    def play_file(self, path: str | Path) -> None:
        self.load(path)
        self.player.play()

    @staticmethod
    def _fmt(ms: int) -> str:
        s = max(0, ms) // 1000
        return f"{s // 60}:{s % 60:02d}"

    def _on_pos(self, pos: int) -> None:
        self.slider.blockSignals(True)
        self.slider.setValue(pos)
        self.slider.blockSignals(False)
        self.lbl_time.setText(f"{self._fmt(pos)} / {self._fmt(self.player.duration)}")

    def _on_dur(self, dur: int) -> None:
        self.slider.setRange(0, max(0, dur))


def show_error(parent: QWidget, title: str, human: str, technical: str = "") -> None:
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle(title)
    box.setText(human)
    if technical:
        box.setDetailedText(technical)
    box.exec()


class SegmentFailDialog(QMessageBox):
    def __init__(self, parent: QWidget, index: int, error: str) -> None:
        super().__init__(parent)
        self.setIcon(QMessageBox.Icon.Critical)
        self.setWindowTitle("Segment failed")
        self.setText(
            f"Segment {index:02d} failed.\n\n{error}\n\n"
            "ONLINE TTS UNAVAILABLE\nUse Offline Piper instead?"
        )
        self.retry = self.addButton("Retry", QMessageBox.ButtonRole.AcceptRole)
        self.use_piper = self.addButton("Use Piper", QMessageBox.ButtonRole.ActionRole)
        self.skip = self.addButton("Skip", QMessageBox.ButtonRole.DestructiveRole)
        self.cancel = self.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
