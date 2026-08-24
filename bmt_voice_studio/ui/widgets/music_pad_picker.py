"""Music picker with a 10-second intro/outro crop on the audio track."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from bmt_voice_studio.audio.player import AudioPlayer
from bmt_voice_studio.ui.theme import COLOR, SPACE
from bmt_voice_studio.video.branding_audio import (
    AUTO_OUTRO_START,
    BRANDED_PAD_SECONDS,
    clamp_music_window,
    default_outro_start,
    music_display_name,
    music_source_duration,
    resolve_music_window_starts,
)


def _fmt(seconds: float) -> str:
    sec = max(0, int(round(seconds)))
    return f"{sec // 60}:{sec % 60:02d}"


class MusicTrackCrop(QWidget):
    """Visual audio track with two draggable 10-second windows (intro + outro)."""

    intro_moved = Signal(float)
    outro_moved = Signal(float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("musicTrackCrop")
        self.setMinimumHeight(52)
        self.setMaximumHeight(56)
        self.duration = 0.0
        self.pad = BRANDED_PAD_SECONDS
        self.intro_start = 0.0
        self.outro_start = 0.0
        self.intro_enabled = True
        self.outro_enabled = True
        self._drag: str | None = None
        self._drag_origin_x = 0
        self._drag_origin_start = 0.0
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Drag the Intro or Outro 10-second window along the music.")

    def set_windows(
        self,
        *,
        duration: float,
        intro_start: float,
        outro_start: float,
        intro_enabled: bool = True,
        outro_enabled: bool = True,
        pad: float = BRANDED_PAD_SECONDS,
    ) -> None:
        self.duration = max(0.0, float(duration or 0.0))
        self.pad = max(0.5, float(pad or BRANDED_PAD_SECONDS))
        self.intro_enabled = bool(intro_enabled)
        self.outro_enabled = bool(outro_enabled)
        self.intro_start = clamp_music_window(intro_start, self.pad, self.duration)
        self.outro_start = clamp_music_window(outro_start, self.pad, self.duration)
        self.update()

    def _window_rect(self, start: float) -> QRect:
        w = max(8, self.width())
        h = self.height()
        if self.duration <= 0:
            return QRect(0, 6, min(w, 48), h - 12)
        span = min(self.pad, self.duration) / self.duration
        px = int(round(start / self.duration * w))
        pw = max(18, int(round(span * w)))
        return QRect(px, 6, min(pw, w - px), h - 12)

    def _hit(self, x: int) -> str | None:
        intro_r = self._window_rect(self.intro_start) if self.intro_enabled else QRect()
        outro_r = self._window_rect(self.outro_start) if self.outro_enabled else QRect()
        in_intro = intro_r.contains(x, intro_r.center().y())
        in_outro = outro_r.contains(x, outro_r.center().y())
        if in_intro and in_outro:
            di = abs(x - intro_r.center().x())
            do = abs(x - outro_r.center().x())
            return "intro" if di <= do else "outro"
        if in_intro:
            return "intro"
        if in_outro:
            return "outro"
        return None

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton or self.duration <= 0:
            return
        hit = self._hit(int(event.position().x()))
        if not hit:
            return
        self._drag = hit
        self._drag_origin_x = int(event.position().x())
        self._drag_origin_start = self.intro_start if hit == "intro" else self.outro_start
        self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not self._drag or self.duration <= 0 or self.width() <= 0:
            return
        dx = int(event.position().x()) - self._drag_origin_x
        dt = dx / float(self.width()) * self.duration
        start = clamp_music_window(self._drag_origin_start + dt, self.pad, self.duration)
        if self._drag == "intro":
            self.intro_start = start
            self.intro_moved.emit(start)
        else:
            self.outro_start = start
            self.outro_moved.emit(start)
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag = None
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        super().mouseReleaseEvent(event)

    def paintEvent(self, event) -> None:  # noqa: ARG002
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        track = self.rect().adjusted(0, 10, 0, -10)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(COLOR.track))
        painter.drawRoundedRect(track, 6, 6)
        if self.duration <= 0:
            painter.setPen(QColor(COLOR.text_muted))
            painter.drawText(self.rect().adjusted(8, 0, -8, 0), Qt.AlignmentFlag.AlignCenter, "Choose music")
            painter.end()
            return
        font = QFont(painter.font())
        font.setPointSize(9)
        font.setBold(True)
        painter.setFont(font)
        if self.intro_enabled:
            r = self._window_rect(self.intro_start)
            painter.setBrush(QColor("#D4A017"))
            painter.setPen(QPen(QColor("#F0C040"), 1))
            painter.drawRoundedRect(r, 5, 5)
            painter.setPen(QColor("#1A1408"))
            painter.drawText(r, Qt.AlignmentFlag.AlignCenter, "INTRO 10s")
        if self.outro_enabled:
            r = self._window_rect(self.outro_start)
            painter.setBrush(QColor("#1E5BB8"))
            painter.setPen(QPen(QColor("#7EC8FF"), 1))
            painter.drawRoundedRect(r, 5, 5)
            painter.setPen(QColor("#F2F6FC"))
            painter.drawText(r, Qt.AlignmentFlag.AlignCenter, "OUTRO 10s")
        painter.end()


class MusicPadPicker(QWidget):
    """Choose music, preview the file, and crop which 10 seconds feed intro/outro."""

    changed = Signal()
    choose_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._path = ""
        self._duration = 0.0
        self._intro_start = 0.0
        self._outro_start = AUTO_OUTRO_START
        self._outro_auto = True
        self._play_until_ms = 0
        self._pending_seek = -1
        self.player = AudioPlayer(self)
        self.player.position_changed.connect(self._on_play_pos)
        self.player.duration_changed.connect(self._on_player_duration)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(SPACE.sm)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

        self.lbl_name = QLabel("No music selected")
        self.lbl_name.setObjectName("valueLabel")
        self.lbl_name.setWordWrap(True)
        self.lbl_name.setMinimumWidth(0)
        self.lbl_hint = QLabel(
            "Soft bed under the whole video — loud on 10s intro/outro, quiet under the voice."
        )
        self.lbl_hint.setObjectName("taskLabel")
        self.lbl_hint.setWordWrap(True)
        self.btn_choose = QPushButton("Choose Music…")
        self.btn_choose.setObjectName("tertiaryButton")
        self.btn_choose.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        root.addWidget(self.lbl_name)
        root.addWidget(self.lbl_hint)
        root.addWidget(self.btn_choose)

        self.track = MusicTrackCrop()
        root.addWidget(self.track)

        intro_row = QHBoxLayout()
        intro_row.setSpacing(SPACE.sm)
        self.lbl_intro = QLabel("Intro 10s: —")
        self.lbl_intro.setObjectName("taskLabel")
        self.lbl_intro.setWordWrap(True)
        self.lbl_intro.setMinimumWidth(0)
        self.btn_play_intro = QPushButton("Play intro")
        self.btn_play_intro.setObjectName("tertiaryButton")
        intro_row.addWidget(self.lbl_intro, 1)
        intro_row.addWidget(self.btn_play_intro)
        root.addLayout(intro_row)

        outro_row = QHBoxLayout()
        outro_row.setSpacing(SPACE.sm)
        self.lbl_outro = QLabel("Outro 10s: —")
        self.lbl_outro.setObjectName("taskLabel")
        self.lbl_outro.setWordWrap(True)
        self.lbl_outro.setMinimumWidth(0)
        self.btn_play_outro = QPushButton("Play outro")
        self.btn_play_outro.setObjectName("tertiaryButton")
        outro_row.addWidget(self.lbl_outro, 1)
        outro_row.addWidget(self.btn_play_outro)
        root.addLayout(outro_row)

        self.btn_choose.clicked.connect(self.choose_requested.emit)
        self.track.intro_moved.connect(self._on_intro_moved)
        self.track.outro_moved.connect(self._on_outro_moved)
        self.btn_play_intro.clicked.connect(lambda: self._play_pad("intro"))
        self.btn_play_outro.clicked.connect(lambda: self._play_pad("outro"))
        self._sync_buttons()

    def music_path(self) -> str:
        return self._path

    def intro_start(self) -> float:
        return float(self._intro_start)

    def outro_start(self) -> float:
        if self._outro_auto:
            return AUTO_OUTRO_START
        return float(self._outro_start)

    def set_music(
        self,
        path: str,
        *,
        intro_start: float = 0.0,
        outro_start: float = AUTO_OUTRO_START,
        intro_enabled: bool = True,
        outro_enabled: bool = True,
        reset_windows: bool = False,
    ) -> None:
        self._path = str(path or "")
        file_ok = bool(self._path and Path(self._path).is_file())
        self._duration = music_source_duration(self._path) if file_ok else 0.0
        if reset_windows or not file_ok:
            self._intro_start = 0.0
            self._outro_auto = True
            self._outro_start = default_outro_start(self._duration, BRANDED_PAD_SECONDS)
        else:
            self._intro_start = float(intro_start or 0.0)
            self._outro_auto = float(outro_start) < 0
            if self._outro_auto:
                self._outro_start = default_outro_start(self._duration, BRANDED_PAD_SECONDS)
            else:
                self._outro_start = float(outro_start)
        intro_at, outro_at = resolve_music_window_starts(
            source_duration=self._duration,
            intro_sec=BRANDED_PAD_SECONDS if intro_enabled else 0.0,
            outro_sec=BRANDED_PAD_SECONDS if outro_enabled else 0.0,
            intro_start=self._intro_start,
            outro_start=None if self._outro_auto else self._outro_start,
        )
        self._intro_start = intro_at
        self._outro_start = outro_at
        self.track.set_windows(
            duration=self._duration,
            intro_start=self._intro_start,
            outro_start=self._outro_start,
            intro_enabled=intro_enabled,
            outro_enabled=outro_enabled,
        )
        if not self._path:
            self.lbl_name.setText("No music selected")
        elif not file_ok:
            self.lbl_name.setText("Music missing — choose a replacement")
        else:
            length = _fmt(self._duration) if self._duration else "—"
            self.lbl_name.setText(f"{music_display_name(self._path)}  ·  {length}")
        self._refresh_labels(intro_enabled, outro_enabled)
        self._sync_buttons()

    def set_pads_enabled(self, intro: bool, outro: bool) -> None:
        self.track.set_windows(
            duration=self._duration,
            intro_start=self._intro_start,
            outro_start=self._outro_start,
            intro_enabled=intro,
            outro_enabled=outro,
        )
        self._refresh_labels(intro, outro)
        self._sync_buttons()

    def _on_intro_moved(self, start: float) -> None:
        self._intro_start = start
        self._refresh_labels(self.track.intro_enabled, self.track.outro_enabled)
        self.changed.emit()

    def _on_outro_moved(self, start: float) -> None:
        self._outro_start = start
        self._outro_auto = False
        self._refresh_labels(self.track.intro_enabled, self.track.outro_enabled)
        self.changed.emit()

    def _refresh_labels(self, intro: bool, outro: bool) -> None:
        if intro and self._duration > 0:
            end = min(self._duration, self._intro_start + BRANDED_PAD_SECONDS)
            self.lbl_intro.setText(f"Intro 10s:  {_fmt(self._intro_start)} – {_fmt(end)}")
        else:
            self.lbl_intro.setText("Intro 10s: off")
        if outro and self._duration > 0:
            end = min(self._duration, self._outro_start + BRANDED_PAD_SECONDS)
            auto = "  (auto end)" if self._outro_auto else ""
            self.lbl_outro.setText(f"Outro 10s:  {_fmt(self._outro_start)} – {_fmt(end)}{auto}")
        else:
            self.lbl_outro.setText("Outro 10s: off")

    def _sync_buttons(self) -> None:
        ready = bool(self._path and Path(self._path).is_file() and self._duration > 0)
        self.btn_play_intro.setEnabled(ready and self.track.intro_enabled)
        self.btn_play_outro.setEnabled(ready and self.track.outro_enabled)

    def _play_pad(self, which: str) -> None:
        if not self._path or not Path(self._path).is_file():
            return
        start = self._intro_start if which == "intro" else self._outro_start
        self._play_until_ms = int((start + BRANDED_PAD_SECONDS) * 1000)
        self._pending_seek = int(start * 1000)
        self.player.stop()
        self.player.load(self._path)
        if self.player.duration > 0:
            self.player.seek(self._pending_seek)
            self.player.play()
            self._pending_seek = -1

    def _on_player_duration(self, dur: int) -> None:
        if self._pending_seek >= 0 and dur > 0:
            self.player.seek(self._pending_seek)
            self.player.play()
            self._pending_seek = -1

    def _on_play_pos(self, pos: int) -> None:
        if self._play_until_ms and pos >= self._play_until_ms:
            self.player.stop()
            self._play_until_ms = 0

    def stop_preview(self) -> None:
        self.player.stop()
        self._play_until_ms = 0
        self._pending_seek = -1
