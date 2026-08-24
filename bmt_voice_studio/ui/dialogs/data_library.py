"""One-time choice when more than one BMT library is found."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QLabel,
    QMessageBox,
    QRadioButton,
    QVBoxLayout,
)

from bmt_voice_studio.config.data_root import (
    LibraryCandidate,
    persist_active_root,
)
from bmt_voice_studio.config.migrate_library import migrate_library
from bmt_voice_studio.config.paths import EXPORT_DIR_NAME, documents_location


class DataLibraryDialog(QDialog):
    def __init__(self, candidates: list[LibraryCandidate], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("BMT Data Library Found")
        self.setMinimumWidth(560)
        self._candidates = [c for c in candidates if c.populated]
        self._choice = "use"
        layout = QVBoxLayout(self)
        title = QLabel("BMT DATA LIBRARY FOUND")
        title.setObjectName("cardTitle")
        layout.addWidget(title)
        intro = QLabel("We found existing BMT files in more than one location.")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        for cand in self._candidates:
            row = QLabel(f"{cand.label}:\n{cand.display_path()}")
            row.setWordWrap(True)
            row.setObjectName("appSubtitle")
            layout.addWidget(row)

        self.radio_use = QRadioButton("USE EXISTING LIBRARY")
        self.radio_move = QRadioButton("MOVE LIBRARY TO DEFAULT LOCATION")
        self.radio_choose = QRadioButton("CHOOSE ANOTHER FOLDER")
        self.radio_use.setChecked(True)
        group = QButtonGroup(self)
        for btn in (self.radio_use, self.radio_move, self.radio_choose):
            group.addButton(btn)
            layout.addWidget(btn)

        if self._candidates:
            self._selected = QRadioButton(self._candidates[0].display_path())
            # pick which existing library when using existing
        self._lib_group = QButtonGroup(self)
        self._lib_radios: list[QRadioButton] = []
        for cand in self._candidates:
            btn = QRadioButton(cand.display_path())
            self._lib_group.addButton(btn)
            self._lib_radios.append(btn)
            layout.addWidget(btn)
        if self._lib_radios:
            self._lib_radios[0].setChecked(True)

        hint = QLabel("Files are not moved unless you choose Move Library.")
        hint.setWordWrap(True)
        hint.setObjectName("appSubtitle")
        layout.addWidget(hint)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self._apply)
        layout.addWidget(buttons)

    def selected_existing(self) -> Path:
        for btn, cand in zip(self._lib_radios, self._candidates, strict=False):
            if btn.isChecked():
                return cand.path
        return self._candidates[0].path

    def _apply(self) -> None:
        canonical = documents_location() / EXPORT_DIR_NAME
        if self.radio_choose.isChecked():
            path = QFileDialog.getExistingDirectory(self, "Data Folder", str(self.selected_existing()))
            if not path:
                return
            persist_active_root(Path(path), mode="custom")
            self.accept()
            return
        if self.radio_use.isChecked():
            chosen = self.selected_existing()
            mode = "default" if chosen.resolve() == canonical.resolve() else "custom"
            persist_active_root(chosen, mode=mode)
            self.accept()
            return
        source = self.selected_existing()
        if source.resolve() == canonical.resolve():
            persist_active_root(canonical, mode="default")
            QMessageBox.information(self, "Data Folder", "That library is already in the default location.")
            self.accept()
            return
        confirm = QMessageBox.question(
            self,
            "Move Library",
            f"Copy this library to the default Documents folder?\n\nFrom:\n{source}\n\nTo:\n{canonical}\n\n"
            "The original folder is not deleted.",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        result = migrate_library(source, canonical)
        if not result.get("ok"):
            QMessageBox.warning(
                self,
                "Move Library",
                "The library could not be copied completely.\n" + "\n".join(result.get("errors") or ["Unknown error"]),
            )
            return
        extra = ""
        if result.get("conflicts"):
            extra = f"\n{len(result['conflicts'])} files were kept under a different name because a copy already existed."
        remove = QMessageBox.question(
            self,
            "Remove old library",
            "The library was copied to the default location.\n\nRemove the old folder now?\n\nDefault is No.",
            QMessageBox.StandardButton.No | QMessageBox.StandardButton.Yes,
            QMessageBox.StandardButton.No,
        )
        if extra:
            QMessageBox.information(self, "Move Library", "Copy complete." + extra)
        if remove == QMessageBox.StandardButton.Yes:
            QMessageBox.information(
                self,
                "Remove old library",
                "Please delete the old folder yourself after confirming the new copy.\n"
                "BMT Voice Studio does not delete libraries automatically.",
            )
        self.accept()
