"""Qt multimedia player wrapper."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QUrl, Signal, Slot
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer


class AudioPlayer(QObject):
    position_changed = Signal(int)
    duration_changed = Signal(int)
    state_changed = Signal(str)
    error_occurred = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._player = QMediaPlayer(self)
        self._audio = QAudioOutput(self)
        self._player.setAudioOutput(self._audio)
        self._audio.setVolume(0.9)
        self._player.positionChanged.connect(self._on_pos)
        self._player.durationChanged.connect(self._on_dur)
        self._player.playbackStateChanged.connect(self._on_state)
        self._player.errorOccurred.connect(self._on_error)

    def _on_pos(self, pos: int) -> None:
        self.position_changed.emit(pos)

    def _on_dur(self, dur: int) -> None:
        self.duration_changed.emit(dur)

    def _on_state(self, state: QMediaPlayer.PlaybackState) -> None:
        mapping = {
            QMediaPlayer.PlaybackState.PlayingState: "playing",
            QMediaPlayer.PlaybackState.PausedState: "paused",
            QMediaPlayer.PlaybackState.StoppedState: "stopped",
        }
        self.state_changed.emit(mapping.get(state, "stopped"))

    def _on_error(self, *_args) -> None:
        self.error_occurred.emit(self._player.errorString() or "Playback error")

    def load(self, path: str | Path) -> None:
        p = Path(path)
        if not p.exists():
            self.error_occurred.emit(f"Audio file not found: {p}")
            return
        self._player.setSource(QUrl.fromLocalFile(str(p.resolve())))

    @Slot()
    def play(self) -> None:
        self._player.play()

    @Slot()
    def pause(self) -> None:
        self._player.pause()

    @Slot()
    def stop(self) -> None:
        self._player.stop()

    def seek(self, ms: int) -> None:
        self._player.setPosition(ms)

    def set_volume(self, value: float) -> None:
        self._audio.setVolume(max(0.0, min(1.0, value)))

    @property
    def position(self) -> int:
        return self._player.position()

    @property
    def duration(self) -> int:
        return self._player.duration()
