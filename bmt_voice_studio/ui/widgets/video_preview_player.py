"""Embedded 9:16 preview player with drag-to-reframe and wheel zoom."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, QUrl, Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QMouseEvent, QPixmap, QWheelEvent
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSlider, QVBoxLayout, QWidget

from bmt_voice_studio.ui.widgets.common import icon_button

PREVIEW_W = 180
PREVIEW_H = 320


class _CropStill(QLabel):
    crop_dragged = Signal(float, float)
    crop_clicked = Signal(float, float)
    zoom_wheeled = Signal(int, float, float)
    media_index_dropped = Signal(int)
    files_dropped = Signal(list)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._last: QPointF | None = None
        self._press: QPointF | None = None
        self._moved = False
        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setToolTip("Drag a thumbnail here to position it · drag to reframe · scroll to zoom")

    def _drop_index(self, event) -> int | None:
        mime = event.mimeData()
        if mime.hasFormat("application/x-bmt-media-index"):
            try:
                return int(bytes(mime.data("application/x-bmt-media-index")).decode("utf-8"))
            except (TypeError, ValueError):
                return None
        return None

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls() or event.mimeData().hasFormat("application/x-bmt-media-index"):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        idx = self._drop_index(event)
        if idx is not None:
            self.media_index_dropped.emit(idx)
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
            return
        if event.mimeData().hasUrls():
            paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
            if paths:
                self.files_dropped.emit(paths)
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
            return
        super().dropEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._last = event.position()
            self._press = event.position()
            self._moved = False
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._last is not None and event.buttons() & Qt.MouseButton.LeftButton:
            pos = event.position()
            dx = float(pos.x() - self._last.x())
            dy = float(pos.y() - self._last.y())
            if abs(dx) + abs(dy) > 2:
                self._moved = True
            self._last = pos
            if self._moved:
                self.crop_dragged.emit(dx, dy)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            if not self._moved and self._press is not None:
                self.crop_clicked.emit(float(self._press.x()), float(self._press.y()))
            self._last = None
            self._press = None
            self._moved = False
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        delta = int(event.angleDelta().y())
        if delta == 0:
            delta = int(event.pixelDelta().y())
        if delta:
            pos = event.position()
            self.zoom_wheeled.emit(delta, float(pos.x()), float(pos.y()))
            event.accept()
            return
        super().wheelEvent(event)


class VideoPreviewPlayer(QWidget):
    fallback_requested = Signal(str)
    crop_dragged = Signal(float, float)
    crop_clicked = Signal(float, float)
    zoom_wheeled = Signal(int, float, float)
    media_index_dropped = Signal(int)
    files_dropped = Signal(list)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._path = ""
        self._embedded_ok = False
        self._player = None
        self._audio = None
        self._video = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)

        self.still = _CropStill()
        self.still.setObjectName("previewStage")
        self.still.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.still.setFixedSize(PREVIEW_W, PREVIEW_H)
        self.still.setText("Add media, then drag here to reframe")
        self.still.crop_dragged.connect(self.crop_dragged.emit)
        self.still.crop_clicked.connect(self.crop_clicked.emit)
        self.still.zoom_wheeled.connect(self.zoom_wheeled.emit)
        self.still.media_index_dropped.connect(self.media_index_dropped.emit)
        self.still.files_dropped.connect(self.files_dropped.emit)
        outer.addWidget(self.still, 0, Qt.AlignmentFlag.AlignHCenter)

        self.host = QWidget()
        self.host.setObjectName("previewStage")
        self.host.setFixedSize(PREVIEW_W, PREVIEW_H)
        host_l = QVBoxLayout(self.host)
        host_l.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.host, 0, Qt.AlignmentFlag.AlignHCenter)
        self.host.hide()

        self.lbl_state = QLabel("Drag to reframe · scroll to zoom")
        self.lbl_state.setObjectName("emptyStateBody")
        self.lbl_state.setWordWrap(True)
        self.lbl_state.setMinimumWidth(0)
        self.lbl_state.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        outer.addWidget(self.lbl_state)

        seek_row = QHBoxLayout()
        self.sld_seek = QSlider(Qt.Orientation.Horizontal)
        self.sld_seek.setRange(0, 1000)
        self.sld_seek.setEnabled(False)
        seek_row.addWidget(self.sld_seek)
        outer.addLayout(seek_row)

        chrome = QHBoxLayout()
        chrome.setContentsMargins(0, 0, 0, 0)
        chrome.setSpacing(2)
        self.btn_play = icon_button("Play", "play")
        self.btn_pause = icon_button("Pause", "pause")
        self.btn_restart = icon_button("Restart", "restart")
        self.btn_crop = icon_button("Crop", "crop")
        self.btn_system = icon_button("Play file", "open")
        for b in (self.btn_play, self.btn_pause, self.btn_restart, self.btn_crop, self.btn_system):
            b.setEnabled(False)
            chrome.addWidget(b)
        chrome.addSpacing(8)
        vol_lbl = QLabel("Vol")
        vol_lbl.setObjectName("metaLabel")
        chrome.addWidget(vol_lbl)
        self.sld_volume = QSlider(Qt.Orientation.Horizontal)
        self.sld_volume.setRange(0, 100)
        self.sld_volume.setValue(80)
        chrome.addWidget(self.sld_volume, 1)
        outer.addLayout(chrome)

        self.btn_play.clicked.connect(self.play)
        self.btn_pause.clicked.connect(self.pause)
        self.btn_restart.clicked.connect(self.restart)
        self.btn_crop.clicked.connect(self.show_still)
        self.btn_system.clicked.connect(self._fallback)
        self.sld_volume.valueChanged.connect(self._set_volume)
        self.sld_seek.sliderReleased.connect(self._seek)
        self._init_multimedia()

    def _init_multimedia(self) -> None:
        try:
            from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
            from PySide6.QtMultimediaWidgets import QVideoWidget

            self._audio = QAudioOutput(self)
            self._player = QMediaPlayer(self)
            self._video = QVideoWidget(self.host)
            self.host.layout().addWidget(self._video)
            self._player.setAudioOutput(self._audio)
            self._player.setVideoOutput(self._video)
            self._audio.setVolume(0.8)
            self._player.positionChanged.connect(self._on_pos)
            self._player.durationChanged.connect(self._on_dur)
            self._embedded_ok = True
        except Exception:
            self._embedded_ok = False
            self.lbl_state.setText("Embedded preview unavailable — use system player")

    def set_still(self, pixmap) -> None:
        if pixmap is not None and not pixmap.isNull():
            self.still.setPixmap(
                pixmap.scaled(
                    self.still.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
            self.show_still()

    def show_still(self) -> None:
        if self._player is not None:
            try:
                self._player.pause()
            except Exception:
                pass
        self.host.hide()
        self.still.show()
        self.lbl_state.setText("Drag to reframe · scroll to zoom · click to center")

    def load(self, path: str) -> bool:
        self._path = path
        ok = bool(path and Path(path).is_file())
        self.btn_system.setEnabled(ok)
        self.btn_play.setEnabled(ok)
        self.btn_pause.setEnabled(ok)
        self.btn_restart.setEnabled(ok)
        self.btn_crop.setEnabled(True)
        self.sld_seek.setEnabled(ok)
        if ok and self._embedded_ok and self._player is not None:
            try:
                self._player.setSource(QUrl.fromLocalFile(str(Path(path).resolve())))
                self.still.hide()
                self.host.show()
                self.lbl_state.setText("Preview ready — press Crop to reframe")
                return True
            except Exception:
                self._embedded_ok = False
        if ok:
            self.host.hide()
            self.still.show()
            self.lbl_state.setText("Preview ready — 12 seconds")
        return False

    def play(self) -> None:
        if self._embedded_ok and self._player is not None and self._path:
            self.still.hide()
            self.host.show()
            self._player.play()
            return
        self._fallback()

    def pause(self) -> None:
        if self._player is not None:
            self._player.pause()

    def restart(self) -> None:
        if self._player is not None:
            self._player.setPosition(0)
            self.still.hide()
            self.host.show()
            self._player.play()

    def _set_volume(self, value: int) -> None:
        if self._audio is not None:
            self._audio.setVolume(max(0.0, min(1.0, value / 100.0)))

    def _on_pos(self, pos: int) -> None:
        if self._player is None or self.sld_seek.isSliderDown():
            return
        dur = max(1, int(self._player.duration() or 1))
        self.sld_seek.setValue(int(1000 * pos / dur))

    def _on_dur(self, _dur: int) -> None:
        pass

    def _seek(self) -> None:
        if self._player is None:
            return
        dur = int(self._player.duration() or 0)
        if dur <= 0:
            return
        self._player.setPosition(int(dur * self.sld_seek.value() / 1000))

    def _fallback(self) -> None:
        if self._path:
            self.fallback_requested.emit(self._path)

    def uses_embedded(self) -> bool:
        return bool(self._embedded_ok)
