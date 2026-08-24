"""About dialog with BBNet branding and clean version identity."""

from __future__ import annotations

import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QTextEdit, QVBoxLayout

from bmt_voice_studio import __app_name__, __version__
from bmt_voice_studio.build_info import BUILD_LABEL, BUILD_TIMESTAMP, runtime_diagnostics
from bmt_voice_studio.resources import logo_label


def _redact_user_paths(text: str) -> str:
    """Strip Windows usernames from diagnostic paths shown in About."""
    text = re.sub(r"(?i)([A-Z]:\\Users\\)[^\\/\s]+", r"\1<user>", text)
    text = re.sub(r"(?i)(/Users/)[^/\s]+", r"\1<user>", text)
    text = re.sub(r"(?i)(\\home\\)[^\\/\s]+", r"\1<user>", text)
    return text


class AboutDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"About {__app_name__}")
        self.setMinimumWidth(480)
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.addWidget(logo_label(max_width=220, max_height=120, parent=self), 0, Qt.AlignmentFlag.AlignHCenter)
        title = QLabel(__app_name__)
        title.setObjectName("appTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        ver = QLabel(f"Version {__version__}")
        ver.setObjectName("valueLabel")
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(ver)
        if "dev" in str(__version__).lower():
            label_text = "UI Polish Development Build"
        elif BUILD_LABEL:
            label_text = BUILD_LABEL
        else:
            label_text = ""
        if label_text:
            sub = QLabel(label_text)
            sub.setObjectName("appSubtitle")
            sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(sub)
        build = QLabel(f"Build {BUILD_TIMESTAMP}")
        build.setObjectName("metaLabel")
        build.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(build)
        diag = QTextEdit()
        diag.setReadOnly(True)
        diag.setMaximumHeight(160)
        diag.setPlainText(_redact_user_paths(runtime_diagnostics()))
        layout.addWidget(diag)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
