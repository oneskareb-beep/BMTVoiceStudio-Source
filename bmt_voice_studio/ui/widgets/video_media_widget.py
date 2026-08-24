"""Media strip for Video Maker — add many clips, see them all, reorder."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QByteArray, QMimeData, QSize, Qt, Signal
from PySide6.QtGui import QDrag, QDragEnterEvent, QDragMoveEvent, QDropEvent, QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from bmt_voice_studio.ui.widgets.common import icon_button, toolbar_icon
from bmt_voice_studio.video.models import MediaItem, MediaType
from bmt_voice_studio.video.reorder import reorder_items
from bmt_voice_studio.video.thumbs import extract_thumbnail


MEDIA_INDEX_MIME = "application/x-bmt-media-index"


class _MediaList(QListWidget):
    files_dropped = Signal(list)

    def startDrag(self, supported_actions) -> None:  # noqa: N802
        indexes = self.selectedIndexes()
        if not indexes:
            return
        mime = self.model().mimeData(indexes)
        row = self.currentRow()
        mime.setData(MEDIA_INDEX_MIME, QByteArray(str(row).encode("utf-8")))
        drag = QDrag(self)
        drag.setMimeData(mime)
        item = self.currentItem()
        if item is not None and not item.icon().isNull():
            drag.setPixmap(item.icon().pixmap(self.iconSize()))
        actions = supported_actions | Qt.DropAction.CopyAction | Qt.DropAction.MoveAction
        drag.exec(actions, Qt.DropAction.MoveAction)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
            if paths:
                self.files_dropped.emit(paths)
            event.acceptProposedAction()
            return
        super().dropEvent(event)


class VideoMediaStrip(QWidget):
    changed = Signal()
    selected_changed = Signal()
    request_replace = Signal(int)
    request_add = Signal()
    files_dropped = Signal(list)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._items: list[MediaItem] = []
        self._selected = 0
        self._syncing = False
        self._locked_defaults = False
        self.setAcceptDrops(True)
        self.setMinimumWidth(0)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)

        tools = QHBoxLayout()
        tools.setContentsMargins(0, 0, 0, 0)
        tools.setSpacing(4)
        self.btn_add = QPushButton("Add media")
        self.btn_add.setObjectName("secondaryButton")
        self.btn_add.setIcon(toolbar_icon("add"))
        self.btn_add.setIconSize(QSize(14, 14))
        self.btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add.setToolTip("Add another photo or video. You can keep adding more.")
        self.btn_add.setAccessibleName("Add media")
        self.btn_left = icon_button("Move earlier in order", "left")
        self.btn_right = icon_button("Move later in order", "right")
        self.btn_replace = icon_button("Replace selected", "replace")
        self.btn_remove = icon_button("Remove selected", "trash", color="#F07178")
        for b in (self.btn_left, self.btn_right, self.btn_replace, self.btn_remove):
            b.setEnabled(False)
        tools.addWidget(self.btn_add)
        tools.addWidget(self.btn_left)
        tools.addWidget(self.btn_right)
        tools.addWidget(self.btn_replace)
        tools.addWidget(self.btn_remove)
        tools.addStretch(1)
        outer.addLayout(tools)

        self.lbl_count = QLabel("No media yet")
        self.lbl_count.setObjectName("metaLabel")
        self.lbl_count.setWordWrap(True)
        outer.addWidget(self.lbl_count)

        self.btn_add.clicked.connect(self.request_add.emit)
        self.btn_left.clicked.connect(self._move_left)
        self.btn_right.clicked.connect(self._move_right)
        self.btn_replace.clicked.connect(self._emit_replace)
        self.btn_remove.clicked.connect(self._remove_selected)

        self.list = _MediaList()
        self.list.setObjectName("mediaStrip")
        self.list.setViewMode(QListWidget.ViewMode.IconMode)
        self.list.setFlow(QListWidget.Flow.LeftToRight)
        self.list.setWrapping(True)
        self.list.setMovement(QListWidget.Movement.Snap)
        self.list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.list.setDragEnabled(True)
        self.list.setAcceptDrops(True)
        self.list.viewport().setAcceptDrops(True)
        self.list.setDropIndicatorShown(True)
        self.list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.list.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list.setIconSize(QSize(84, 148))
        self.list.setSpacing(8)
        self.list.setMinimumHeight(200)
        self.list.setMaximumHeight(360)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.list.setToolTip(
            "All media stays visible here. Drag to reorder, use ← →, or drag a thumbnail onto the 9:16 preview."
        )
        outer.addWidget(self.list)

        self._placeholder = QLabel("Drop photos and clips here, or click Add media. PNG keeps transparency.")
        self._placeholder.setObjectName("emptyStateBody")
        self._placeholder.setWordWrap(True)
        self._placeholder.setMinimumWidth(0)
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignLeft)
        outer.addWidget(self._placeholder)
        self.list.hide()
        self._thumb_hint = QSize(96, 188)

        self.list.itemSelectionChanged.connect(self._on_select)
        self.list.itemDoubleClicked.connect(self._on_double_click)
        self.list.model().rowsMoved.connect(self._on_rows_moved)
        self.list.files_dropped.connect(self.files_dropped.emit)

    def set_locked_defaults(self, locked: bool = True) -> None:
        """Bundled 5-clip mode: reorder only, no add/remove/replace/drop."""
        self._locked_defaults = bool(locked)
        self.btn_add.setVisible(not locked)
        self.btn_remove.setVisible(not locked)
        self.btn_replace.setVisible(not locked)
        self.btn_add.setEnabled(not locked)
        self.btn_remove.setEnabled(not locked and bool(self._items))
        self.btn_replace.setEnabled(not locked and bool(self._items))
        self.setAcceptDrops(not locked)
        self.list.setAcceptDrops(not locked)
        self.list.viewport().setAcceptDrops(not locked)
        self.list.setDragEnabled(True)
        if locked:
            self._placeholder.setText(
                "Five 16:9 clips are included with this template. "
                "Drag to reorder or use ← →. Replace clips in Preferences → Default video clips."
            )
        else:
            self._placeholder.setText("Drop photos and clips here, or click Add media. PNG keeps transparency.")
        self._rebuild()

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if self._locked_defaults:
            return
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        if self._locked_defaults:
            return
        if event.mimeData().hasUrls():
            paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
            if paths:
                self.files_dropped.emit(paths)
            event.acceptProposedAction()
            return
        super().dropEvent(event)

    def items(self) -> list[MediaItem]:
        return list(self._items)

    def set_items(self, items: list[MediaItem]) -> None:
        self._items = []
        for i, item in enumerate(items):
            copy = MediaItem.from_dict(item.to_dict())
            copy.order = i
            copy.missing = not copy.exists()
            self._items.append(copy)
        if self._selected >= len(self._items):
            self._selected = max(0, len(self._items) - 1)
        self._rebuild()

    def add_items(self, items: list[MediaItem]) -> None:
        start = len(self._items)
        for i, item in enumerate(items):
            copy = MediaItem.from_dict(item.to_dict())
            copy.order = start + i
            copy.missing = not copy.exists()
            self._items.append(copy)
        if items:
            self._selected = start
        self._rebuild()
        self.changed.emit()
        self.selected_changed.emit()

    def selected_index(self) -> int:
        return self._selected

    def select_index(self, index: int) -> None:
        if not self._items:
            return
        self._selected = max(0, min(int(index), len(self._items) - 1))
        self._syncing = True
        try:
            self.list.setCurrentRow(self._selected)
            self._sync_action_enabled()
        finally:
            self._syncing = False
        self.selected_changed.emit()

    def selected_item(self) -> MediaItem | None:
        if 0 <= self._selected < len(self._items):
            return self._items[self._selected]
        return None

    def update_selected(self, **kwargs) -> None:
        item = self.selected_item()
        if item is None:
            return
        for key, value in kwargs.items():
            if hasattr(item, key):
                setattr(item, key, value)
        self.changed.emit()

    def replace_at(self, index: int, item: MediaItem) -> None:
        if 0 <= index < len(self._items):
            item.order = index
            item.missing = not item.exists()
            self._items[index] = item
            self._rebuild()
            self.changed.emit()

    def _rebuild(self) -> None:
        self._syncing = True
        try:
            self.list.clear()
            has = bool(self._items)
            self.list.setVisible(has)
            self._placeholder.setVisible(not has)
            n = len(self._items)
            if n == 0:
                self.lbl_count.setText("No media yet — Add media keeps accepting more files.")
            elif n == 1:
                self.lbl_count.setText("1 item · Add media to include more · drag or ← → to order")
            elif self._locked_defaults:
                self.lbl_count.setText(f"{n} bundled clips · drag or ← → to set playback order")
            else:
                self.lbl_count.setText(f"{n} items in order · drag thumbnails or use ← →")
            for i, item in enumerate(self._items):
                qitem = QListWidgetItem(self._item_label(i, item))
                qitem.setData(Qt.ItemDataRole.UserRole, i)
                qitem.setToolTip(str(item.path or Path(item.path).name if item.path else "Untitled"))
                qitem.setSizeHint(self._thumb_hint)
                icon = self._icon_for(item)
                if icon is not None:
                    qitem.setIcon(icon)
                self.list.addItem(qitem)
            if self._items:
                self.list.setCurrentRow(min(self._selected, len(self._items) - 1))
            self._sync_action_enabled()
        finally:
            self._syncing = False

    def _item_label(self, index: int, item: MediaItem) -> str:
        name = Path(item.path).name if item.path else "Untitled"
        if item.missing or not item.exists():
            return f"{index + 1}. Missing"
        kind = "Overlay" if getattr(item, "overlay", False) else (
            "Video" if str(item.media_type) == MediaType.VIDEO.value else "Photo"
        )
        dur = ""
        if str(item.media_type) == MediaType.VIDEO.value and getattr(item, "duration", None):
            try:
                sec = int(round(float(item.duration or 0)))
                if sec > 0:
                    dur = f" · {sec // 60:02d}:{sec % 60:02d}"
            except (TypeError, ValueError):
                dur = ""
        short = name if len(name) <= 16 else name[:13] + "…"
        return f"{index + 1}. {kind}\n{short}{dur}"

    def _sync_action_enabled(self) -> None:
        has = bool(self._items)
        n = len(self._items)
        self.btn_replace.setEnabled(has)
        self.btn_remove.setEnabled(has)
        self.btn_left.setEnabled(has and self._selected > 0)
        self.btn_right.setEnabled(has and self._selected < n - 1)

    def _icon_for(self, item: MediaItem) -> QIcon | None:
        if item.missing or not item.exists():
            return None
        thumb = extract_thumbnail(
            item.path,
            media_type=item.media_type,
            rotation=int(getattr(item, "rotation", 0) or 0),
        )
        if thumb and thumb.is_file():
            pix = QPixmap(str(thumb))
            if not pix.isNull():
                return QIcon(pix)
        return None

    def _on_select(self) -> None:
        if self._syncing:
            return
        row = self.list.currentRow()
        if row >= 0:
            self._selected = row
            self._sync_action_enabled()
            self.selected_changed.emit()

    def _on_double_click(self, *_args) -> None:
        if self._locked_defaults:
            return
        if self._items:
            self.request_replace.emit(self._selected)

    def _on_rows_moved(self, *_args) -> None:
        if self._syncing:
            return
        new_order: list[MediaItem] = []
        for i in range(self.list.count()):
            qitem = self.list.item(i)
            src = int(qitem.data(Qt.ItemDataRole.UserRole) or 0)
            if 0 <= src < len(self._items):
                new_order.append(self._items[src])
            qitem.setData(Qt.ItemDataRole.UserRole, i)
        if len(new_order) == len(self._items):
            self._items = new_order
            for i, item in enumerate(self._items):
                item.order = i
                qitem = self.list.item(i)
                if qitem is not None:
                    qitem.setText(self._item_label(i, item))
            self._selected = self.list.currentRow()
            self._sync_action_enabled()
            self.changed.emit()

    def _move_left(self) -> None:
        idx = self._selected
        if idx <= 0:
            return
        self._items = reorder_items(self._items, idx, idx - 1)
        self._selected = idx - 1
        self._rebuild()
        self.changed.emit()
        self.selected_changed.emit()

    def _move_right(self) -> None:
        idx = self._selected
        if idx >= len(self._items) - 1:
            return
        self._items = reorder_items(self._items, idx, idx + 1)
        self._selected = idx + 1
        self._rebuild()
        self.changed.emit()
        self.selected_changed.emit()

    def _emit_replace(self) -> None:
        if self._locked_defaults:
            return
        if self._items:
            self.request_replace.emit(self._selected)

    def _remove_selected(self) -> None:
        if self._locked_defaults:
            return
        if 0 <= self._selected < len(self._items):
            del self._items[self._selected]
            for i, item in enumerate(self._items):
                item.order = i
            self._selected = min(self._selected, max(0, len(self._items) - 1))
            self._rebuild()
            self.changed.emit()
            self.selected_changed.emit()
