"""Keyboard helpers that stay out of the way while typing."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QLineEdit,
    QPlainTextEdit,
    QTextEdit,
    QWidget,
)

TYPING_WIDGETS = (QLineEdit, QPlainTextEdit, QTextEdit, QAbstractSpinBox, QComboBox)


def is_typing_focus() -> bool:
    widget = QApplication.focusWidget()
    return isinstance(widget, TYPING_WIDGETS)


def bind_shortcut(
    page: QWidget,
    sequence: str,
    slot: Callable[[], None],
    *,
    idle_only: bool = False,
) -> QShortcut:
    shortcut = QShortcut(QKeySequence(sequence), page)
    shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)

    def _fire() -> None:
        if idle_only and is_typing_focus():
            return
        slot()

    shortcut.activated.connect(_fire)
    if idle_only:
        app = QApplication.instance()
        if app is not None:
            app.focusChanged.connect(
                lambda _old, new: shortcut.setEnabled(not isinstance(new, TYPING_WIDGETS))
            )
        shortcut.setEnabled(not is_typing_focus())
    return shortcut
