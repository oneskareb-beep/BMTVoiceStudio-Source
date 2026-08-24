"""Replace bundled default video clips (Preferences)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from bmt_voice_studio.config.settings import get_settings, save_settings
from bmt_voice_studio.ui.widgets.common import ellipsize_path
from bmt_voice_studio.video.bundled_media import (
    BUNDLED_CLIP_COUNT,
    bundled_clip_path,
    clear_override_clip,
    reset_template_overrides,
    resolve_clip_path,
    save_override_clip,
)
from bmt_voice_studio.video.models import TEMPLATE_BMT_CLASSIC, TEMPLATE_LABELS


class DefaultMediaDialog(QDialog):
    """Pick or replace the five locked 16:9 clips bundled with each template."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Default Video Clips")
        self.setMinimumWidth(620)
        layout = QVBoxLayout(self)
        intro = QLabel(
            "BMT Voice Studio ships with five 16:9 clips per template. "
            "Video Maker uses these automatically — no upload needed each day. "
            "Replace individual slots here if you want your own footage."
        )
        intro.setWordWrap(True)
        intro.setObjectName("appSubtitle")
        layout.addWidget(intro)

        row = QHBoxLayout()
        self.cmb_template = QComboBox()
        for tid, label in TEMPLATE_LABELS.items():
            self.cmb_template.addItem(label, tid)
        self.cmb_template.setCurrentIndex(self.cmb_template.findData(TEMPLATE_BMT_CLASSIC))
        row.addWidget(QLabel("Template"))
        row.addWidget(self.cmb_template, 1)
        layout.addLayout(row)

        self._slot_labels: list[QLabel] = []
        slots_col = QVBoxLayout()
        for i in range(1, BUNDLED_CLIP_COUNT + 1):
            slot_row = QHBoxLayout()
            title = QLabel(f"Clip {i}")
            title.setObjectName("fieldLabel")
            title.setFixedWidth(52)
            path_lbl = QLabel("")
            path_lbl.setObjectName("valueLabel")
            path_lbl.setWordWrap(True)
            btn_replace = QPushButton("Replace…")
            btn_replace.setObjectName("secondaryButton")
            btn_reset = QPushButton("Bundled")
            btn_reset.setObjectName("tertiaryButton")
            btn_replace.clicked.connect(lambda _=False, slot=i: self._replace_slot(slot))
            btn_reset.clicked.connect(lambda _=False, slot=i: self._reset_slot(slot))
            slot_row.addWidget(title)
            slot_row.addWidget(path_lbl, 1)
            slot_row.addWidget(btn_replace)
            slot_row.addWidget(btn_reset)
            slots_col.addLayout(slot_row)
            self._slot_labels.append(path_lbl)
        layout.addLayout(slots_col)

        reset_row = QHBoxLayout()
        self.btn_reset_all = QPushButton("Reset all clips to bundled defaults")
        self.btn_reset_all.setObjectName("tertiaryButton")
        self.btn_reset_all.clicked.connect(self._reset_all)
        reset_row.addStretch(1)
        reset_row.addWidget(self.btn_reset_all)
        layout.addLayout(reset_row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.cmb_template.currentIndexChanged.connect(self._refresh_paths)
        self._refresh_paths()

    def _template_id(self) -> str:
        return str(self.cmb_template.currentData() or TEMPLATE_BMT_CLASSIC)

    def _refresh_paths(self) -> None:
        tid = self._template_id()
        for i, lbl in enumerate(self._slot_labels, start=1):
            path = resolve_clip_path(tid, i)
            bundled = bundled_clip_path(tid, i)
            if path and path.is_file():
                name = ellipsize_path(str(path), 56)
                if bundled and path.resolve() == bundled.resolve():
                    lbl.setText(f"{name} (bundled)")
                else:
                    lbl.setText(f"{name} (custom)")
            else:
                lbl.setText("Missing bundled clip")

    def _replace_slot(self, slot: int) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            f"Replace clip {slot}",
            str(Path.home()),
            "Video (*.mp4 *.mov *.mkv *.webm);;All files (*.*)",
        )
        if not path:
            return
        try:
            save_override_clip(self._template_id(), slot, Path(path))
        except Exception as exc:
            QMessageBox.warning(self, "Default Video Clips", f"Could not save that clip:\n{exc}")
            return
        self._refresh_paths()

    def _reset_slot(self, slot: int) -> None:
        clear_override_clip(self._template_id(), slot)
        self._refresh_paths()

    def _reset_all(self) -> None:
        reset_template_overrides(self._template_id())
        self._refresh_paths()

    def accept(self) -> None:
        save_settings(get_settings())
        super().accept()
