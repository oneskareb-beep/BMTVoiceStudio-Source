"""M3U / Audio Builder page."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from bmt_voice_studio.config.paths import default_exports_dir
from bmt_voice_studio.config.settings import get_settings
from bmt_voice_studio.core.filenames import sanitize_filename, unique_path
from bmt_voice_studio.core.models import PlaylistItem
from bmt_voice_studio.m3u.parser import parse_m3u_content, parse_m3u_file, parse_url_list
from bmt_voice_studio.ui.widgets.common import AudioPlayerBar, card, show_error
from bmt_voice_studio.workers.generation import DownloadMergeController


class AudioBuilderPage(QWidget):
    status_message = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.items: list[PlaylistItem] = []
        self._playlist_text = ""
        self._is_hls = False
        self._playlist_source = ""  # local path or remote m3u8 URL for FFmpeg HLS
        self._controller = DownloadMergeController()
        self._build()
        self._wire()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)
        title = QLabel("Audio / M3U Builder")
        title.setObjectName("pageTitle")
        root.addWidget(title)
        hint = QLabel("Open playlists, paste URLs, drag & drop — downloads run in Python (no browser CORS).")
        hint.setObjectName("cardHint")
        root.addWidget(hint)

        actions = QHBoxLayout()
        self.btn_open = QPushButton("Open M3U / M3U8")
        self.btn_parse = QPushButton("Parse Paste Area")
        self.btn_clear = QPushButton("Clear")
        self.btn_up = QPushButton("Move Up")
        self.btn_down = QPushButton("Move Down")
        self.btn_remove = QPushButton("Remove")
        self.btn_preview = QPushButton("Preview")
        self.btn_merge = QPushButton("DOWNLOAD & MERGE")
        self.btn_merge.setObjectName("primaryButton")
        for b in (
            self.btn_open,
            self.btn_parse,
            self.btn_clear,
            self.btn_up,
            self.btn_down,
            self.btn_remove,
            self.btn_preview,
            self.btn_merge,
        ):
            actions.addWidget(b)
        root.addLayout(actions)

        paste_card, paste_l = card("PASTE AUDIO URLS / M3U", "One URL per line, or full playlist text")
        self.paste = QPlainTextEdit()
        self.paste.setPlaceholderText("#EXTM3U\nhttps://example.com/01.mp3\nhttps://example.com/02.wav")
        self.paste.setMinimumHeight(140)
        paste_l.addWidget(self.paste)
        root.addWidget(paste_card)

        list_card, list_l = card("PLAYLIST ITEMS", "Drag to reorder is supported via Move Up/Down")
        self.list = QListWidget()
        list_l.addWidget(self.list)
        root.addWidget(list_card, 1)

        self.progress = QProgressBar()
        root.addWidget(self.progress)
        self.player = AudioPlayerBar()
        root.addWidget(self.player)
        self.lbl = QLabel("Ready")
        root.addWidget(self.lbl)

    def _wire(self) -> None:
        self.btn_open.clicked.connect(self.open_file)
        self.btn_parse.clicked.connect(self.parse_paste)
        self.btn_clear.clicked.connect(self.clear)
        self.btn_up.clicked.connect(lambda: self._move(-1))
        self.btn_down.clicked.connect(lambda: self._move(1))
        self.btn_remove.clicked.connect(self._remove)
        self.btn_preview.clicked.connect(self._preview)
        self.btn_merge.clicked.connect(self.merge)
        self._controller.signals.progress.connect(self._on_progress)
        self._controller.signals.finished.connect(self._on_done)
        self._controller.signals.error.connect(self._on_error)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls() or event.mimeData().hasText():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                path = Path(url.toLocalFile())
                if path.suffix.lower() in {".m3u", ".m3u8"}:
                    self._load_path(path)
                elif path.suffix.lower() in {".mp3", ".wav", ".m4a", ".aac", ".ogg"}:
                    self.items.append(
                        PlaylistItem(index=len(self.items) + 1, source=str(path), title=path.name)
                    )
                    self._refresh()
        elif event.mimeData().hasText():
            self.paste.setPlainText(event.mimeData().text())
            self.parse_paste()
        event.acceptProposedAction()

    def open_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open playlist", str(Path.home() / "Downloads"), "Playlists (*.m3u *.m3u8);;All (*.*)"
        )
        if path:
            self._load_path(Path(path))

    def _load_path(self, path: Path) -> None:
        result = parse_m3u_file(path)
        self._playlist_text = path.read_text(encoding="utf-8", errors="replace")
        self._is_hls = result.is_hls
        self._playlist_source = str(path.resolve())
        self.items = result.items
        self.paste.setPlainText(self._playlist_text)
        self._refresh()
        msg = f"Loaded {len(self.items)} items"
        if result.is_hls:
            msg += " (HLS detected — FFmpeg ingest will be used when applicable)"
        if result.errors:
            msg += " · " + "; ".join(result.errors)
        self.lbl.setText(msg)
        self.status_message.emit(msg)

    def parse_paste(self) -> None:
        text = self.paste.toPlainText()
        self._playlist_text = text
        if "#EXTM3U" in text or "#EXTINF" in text or "#EXT-X-" in text:
            result = parse_m3u_content(text)
        else:
            result = parse_url_list(text)
        self._is_hls = result.is_hls
        self.items = result.items
        self._refresh()
        self.lbl.setText(f"Parsed {len(self.items)} items" + (" (HLS)" if self._is_hls else ""))

    def clear(self) -> None:
        self.items = []
        self.paste.clear()
        self._refresh()

    def _refresh(self) -> None:
        self.list.clear()
        for i, item in enumerate(self.items, start=1):
            item.index = i
            label = f"{i:02d}  {item.title or item.source}"
            self.list.addItem(QListWidgetItem(label))

    def _move(self, delta: int) -> None:
        row = self.list.currentRow()
        if row < 0:
            return
        new = row + delta
        if new < 0 or new >= len(self.items):
            return
        self.items[row], self.items[new] = self.items[new], self.items[row]
        self._refresh()
        self.list.setCurrentRow(new)

    def _remove(self) -> None:
        row = self.list.currentRow()
        if row < 0:
            return
        self.items.pop(row)
        self._refresh()

    def _preview(self) -> None:
        row = self.list.currentRow()
        if row < 0:
            return
        item = self.items[row]
        if item.local_path and Path(item.local_path).exists():
            self.player.play_file(item.local_path)
        elif Path(item.source).exists():
            self.player.play_file(item.source)
        else:
            QMessageBox.information(self, "Preview", "Download first, or select a local file.")

    def merge(self) -> None:
        if not self.items:
            self.parse_paste()
        if not self.items:
            QMessageBox.warning(self, "Empty", "No playlist items to merge.")
            return
        settings = get_settings()
        out_dir = Path(settings.output_directory or default_exports_dir()) / "M3U_Merges"
        out_dir.mkdir(parents=True, exist_ok=True)
        out = unique_path(out_dir / f"{sanitize_filename('merged_playlist')}.mp3")
        self.btn_merge.setEnabled(False)
        self.lbl.setText("Downloading…")
        self._controller.start(
            self.items,
            out,
            pause_ms=0,
            bitrate_kbps=settings.mp3_bitrate,
            playlist_text=self._playlist_text,
            playlist_source=self._playlist_source,
        )

    def _on_progress(self, c: int, t: int, msg: str) -> None:
        self.progress.setMaximum(max(1, t))
        self.progress.setValue(c)
        self.lbl.setText(msg)
        self.status_message.emit(msg)

    def _on_done(self, result: dict) -> None:
        self.btn_merge.setEnabled(True)
        path = result.get("mp3", "")
        self.lbl.setText(f"Done: {path}")
        if path:
            self.player.play_file(path)
        QMessageBox.information(self, "Merged", f"Created:\n{path}")

    def _on_error(self, human: str, technical: str) -> None:
        self.btn_merge.setEnabled(True)
        show_error(self, "Download / merge failed", human, technical)
