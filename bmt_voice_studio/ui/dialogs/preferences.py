"""Minimal preferences — appearance and data folder."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from bmt_voice_studio.config.data_root import (
    canonical_documents_location,
    persist_active_root,
    populated_libraries,
)
from bmt_voice_studio.config.paths import EXPORT_DIR_NAME, data_root_display, user_data_root
from bmt_voice_studio.config.settings import get_settings, save_settings


def _open_folder(path: Path) -> None:
    try:
        os.startfile(path)  # noqa: S606
    except Exception as exc:
        QMessageBox.warning(None, "Data Folder", f"Could not open the folder:\n{exc}")


class PreferencesDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.setMinimumWidth(560)
        self._folder_changed = False
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.theme = QComboBox()
        self.theme.addItems(["dark", "light"])
        form.addRow("Appearance", self.theme)

        folder_col = QVBoxLayout()
        self.lbl_current = QLabel()
        self.lbl_current.setWordWrap(True)
        self.lbl_current.setObjectName("valueLabel")
        self.lbl_current.setTextInteractionFlags(self.lbl_current.textInteractionFlags())
        folder_col.addWidget(QLabel("Current Data Folder"))
        folder_col.addWidget(self.lbl_current)

        btns = QHBoxLayout()
        self.btn_default = QPushButton("Use Default")
        self.btn_choose = QPushButton("Choose Folder")
        self.btn_open = QPushButton("Open Folder")
        for b in (self.btn_default, self.btn_choose, self.btn_open):
            b.setObjectName("secondaryButton")
            btns.addWidget(b)
        folder_col.addLayout(btns)
        self.btn_review = QPushButton("Review Existing Libraries")
        self.btn_review.setObjectName("tertiaryButton")
        folder_col.addWidget(self.btn_review)
        hint = QLabel(
            "Daily Audio, Video Maker, History, and Projects share this folder.\n"
            "Changing the folder does not move files automatically. Restart after changing."
        )
        hint.setObjectName("appSubtitle")
        hint.setWordWrap(True)
        folder_col.addWidget(hint)
        form.addRow("Data Folder", folder_col)
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        layout.addWidget(buttons)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        self.btn_default.clicked.connect(self._use_default)
        self.btn_choose.clicked.connect(self._choose)
        self.btn_open.clicked.connect(self._open_current)
        self.btn_review.clicked.connect(self._review)
        self.btn_default_media = QPushButton("Default video clips…")
        self.btn_default_media.setObjectName("secondaryButton")
        self.btn_default_media.clicked.connect(self._open_default_media)
        folder_col.addWidget(self.btn_default_media)
        self._load()

    def _load(self) -> None:
        s = get_settings()
        self.theme.setCurrentText(s.theme or "dark")
        self._refresh_current()

    def _refresh_current(self) -> None:
        self.lbl_current.setText(data_root_display())
        current = user_data_root()
        others = [c for c in populated_libraries() if c.path.resolve() != current.resolve()]
        self.btn_review.setVisible(bool(others))

    def _use_default(self) -> None:
        dest = canonical_documents_location() / EXPORT_DIR_NAME
        persist_active_root(dest, mode="default")
        self._folder_changed = True
        self._refresh_current()

    def _choose(self) -> None:
        start = data_root_display()
        path = QFileDialog.getExistingDirectory(self, "Data Folder", start)
        if not path:
            return
        persist_active_root(Path(path), mode="custom")
        self._folder_changed = True
        self._refresh_current()

    def _open_current(self) -> None:
        _open_folder(user_data_root())

    def _review(self) -> None:
        from bmt_voice_studio.config.data_root import discover_library_candidates
        from bmt_voice_studio.ui.dialogs.data_library import DataLibraryDialog

        dlg = DataLibraryDialog(discover_library_candidates(), self)
        dlg.exec()
        self._folder_changed = True
        self._refresh_current()

    def _open_default_media(self) -> None:
        from bmt_voice_studio.ui.dialogs.default_media import DefaultMediaDialog

        DefaultMediaDialog(self).exec()

    def _save(self) -> None:
        s = get_settings()
        s.theme = self.theme.currentText()
        save_settings(s)
        if self._folder_changed:
            QMessageBox.information(
                self,
                "Data Folder",
                "The data folder was updated. Close and reopen Daily Audio and Video Maker "
                "if a page still shows the previous location.\n\n"
                f"Now using:\n{data_root_display()}",
            )
        self.accept()

    @property
    def selected_theme(self) -> str:
        return self.theme.currentText()
