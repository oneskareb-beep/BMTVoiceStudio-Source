"""Help → Troubleshooting — diagnostic tools kept off the main Daily BMT screen."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from bmt_voice_studio.config.pipeline_config import all_settings_match, compare_runtime_to_reference
from bmt_voice_studio.config.data_root import (
    KIND_LEGACY,
    canonical_documents_location,
    custom_folder_from_settings,
    discover_library_candidates,
)
from bmt_voice_studio.config.paths import EXPORT_DIR_NAME, data_root_display, logs_dir, user_data_root
from bmt_voice_studio.config.presets import BMT_ENGLISH, BMT_FRENCH, BMT_PORTUGUESE, BMT_SWAHILI
from bmt_voice_studio.config.settings import get_settings
from bmt_voice_studio.daily.regional_approval import get_regional_entry
from bmt_voice_studio.tools.cloud_fallback_export import export_cloud_fallback_package
from bmt_voice_studio.workers.generation import HealthController


class TroubleshootingDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Troubleshooting")
        self.setMinimumSize(620, 460)
        layout = QVBoxLayout(self)
        hint = QLabel(
            "Diagnostic tools for support and verification.\n"
            "Normal Daily BMT production does not require these."
        )
        hint.setWordWrap(True)
        hint.setObjectName("appSubtitle")
        layout.addWidget(hint)
        self.lbl_data = QLabel(self._data_root_text())
        self.lbl_data.setObjectName("appSubtitle")
        self.lbl_data.setWordWrap(True)
        self.lbl_data.setTextInteractionFlags(self.lbl_data.textInteractionFlags())
        layout.addWidget(self.lbl_data)
        self.btn_open_data = QPushButton("Open Data Folder")
        self.btn_open_data.setObjectName("secondaryButton")
        layout.addWidget(self.btn_open_data)

        row = QHBoxLayout()
        self.btn_verify = QPushButton("Verify Production Configuration")
        self.btn_export = QPushButton("Export Cloud Fallback Package")
        self.btn_health = QPushButton("System Health Check")
        self.btn_logs = QPushButton("Open Logs")
        self.btn_video_log = QPushButton("Video Render Log")
        self.btn_config = QPushButton("Production Configuration")
        self.btn_regional = QPushButton("Regional Voice Setup")
        for b in (
            self.btn_verify,
            self.btn_config,
            self.btn_regional,
            self.btn_export,
            self.btn_health,
            self.btn_logs,
            self.btn_video_log,
        ):
            b.setObjectName("secondaryButton")
            row.addWidget(b)
        layout.addLayout(row)

        self.out = QTextEdit()
        self.out.setReadOnly(True)
        layout.addWidget(self.out, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

        self._health = HealthController()
        self._health.signals.finished.connect(self._on_health)
        self._health.signals.error.connect(lambda h, t: self.out.append(h))

        self.btn_verify.clicked.connect(self._verify)
        self.btn_config.clicked.connect(self._show_config)
        self.btn_regional.clicked.connect(self._regional_setup)
        self.btn_export.clicked.connect(self._export)
        self.btn_health.clicked.connect(self._run_health)
        self.btn_logs.clicked.connect(self._open_logs)
        self.btn_video_log.clicked.connect(self._open_video_log)
        self.btn_open_data.clicked.connect(self._open_data)

    def _data_root_text(self) -> str:
        active = data_root_display()
        default = str(canonical_documents_location() / EXPORT_DIR_NAME)
        legacy = any(c.kind == KIND_LEGACY and c.populated for c in discover_library_candidates())
        custom = custom_folder_from_settings() is not None
        return (
            f"Active Data Folder:\n{active}\n\n"
            f"Default Documents Folder:\n{default}\n\n"
            f"Legacy Library Detected: {'Yes' if legacy else 'No'}\n"
            f"Custom Folder: {'Yes' if custom else 'No'}"
        )

    def _open_data(self) -> None:
        folder = user_data_root()
        try:
            import os

            os.startfile(folder)  # noqa: S606
            self.out.setPlainText(f"Opened data folder:\n{folder}")
        except Exception as exc:
            QMessageBox.warning(self, "Data Folder", f"Could not open the data folder:\n{exc}")

    def _regional_setup(self) -> None:
        from bmt_voice_studio.ui.dialogs.regional_voice_setup import RegionalVoiceSetupDialog

        dlg = RegionalVoiceSetupDialog(self)
        dlg.exec()
        self._show_config()

    def _show_config(self) -> None:
        from bmt_voice_studio.daily.language_config import (
            production_details_text,
            regional_technical_details_text,
        )

        lines = [
            "Production Configuration (troubleshooting)\n",
            f"Data Folder:\n{data_root_display()}\n",
            production_details_text(),
            "",
            "Regional Voice Setup (technical)",
            regional_technical_details_text(),
            "",
            "Provider: Online Neural TTS (Edge)",
            "Piper production policy: forbidden for approved Daily languages",
        ]
        self.out.setPlainText("\n".join(lines))

    def _verify(self) -> None:
        lines = ["Pipeline verification (canonical reference)\n"]
        for preset in (BMT_ENGLISH, BMT_FRENCH):
            rows = compare_runtime_to_reference(
                preset.id,
                pause_ms=preset.pipeline.pause_ms,
                mp3_bitrate=preset.pipeline.mp3_bitrate_kbps,
                processing_mode="original",
                mastering=False,
                volume=preset.volume,
            )
            lines.append(f"{preset.name}:")
            for r in rows:
                status = "MATCH" if r.match else "MISMATCH"
                lines.append(f"  {r.field}: {r.desktop} → {status}")
            lines.append("")
        ok = all_settings_match(
            compare_runtime_to_reference(
                BMT_ENGLISH.id,
                pause_ms=BMT_ENGLISH.pipeline.pause_ms,
                mp3_bitrate=BMT_ENGLISH.pipeline.mp3_bitrate_kbps,
                processing_mode="original",
                mastering=False,
                volume=BMT_ENGLISH.volume,
            )
        ) and all_settings_match(
            compare_runtime_to_reference(
                BMT_FRENCH.id,
                pause_ms=BMT_FRENCH.pipeline.pause_ms,
                mp3_bitrate=BMT_FRENCH.pipeline.mp3_bitrate_kbps,
                processing_mode="original",
                mastering=False,
                volume=BMT_FRENCH.volume,
            )
        )
        header = "ALL SETTINGS MATCH BMT REFERENCE PIPELINE\n" if ok else "MISMATCH DETECTED\n"
        self.out.setPlainText(header + "\n".join(lines))

    def _export(self) -> None:
        dest = Path(get_settings().output_directory) / "BMT_Cloud_Fallback_Package"
        try:
            export_cloud_fallback_package(dest)
            self.out.setPlainText(f"Cloud fallback package exported to:\n{dest}")
        except Exception as exc:
            self.out.setPlainText(f"Export failed: {exc}")

    def _run_health(self) -> None:
        self.out.setPlainText("Running health checks…")
        self._health.start()

    def _on_health(self, status: dict) -> None:
        self.out.setPlainText(
            f"Internet: {status.get('internet')}\n"
            f"Edge TTS: {status.get('edge')}\n"
            f"Piper Offline: {status.get('piper')}\n"
            f"FFmpeg: {status.get('ffmpeg')}\n"
        )

    def _open_logs(self) -> None:
        folder = logs_dir()
        try:
            import os

            os.startfile(folder)  # noqa: S606
            self.out.setPlainText(f"Opened logs folder:\n{folder}")
        except Exception as exc:
            QMessageBox.warning(self, "Logs", f"Could not open logs folder:\n{exc}")

    def _open_video_log(self) -> None:
        from bmt_voice_studio.video.ffmpeg_renderer import last_video_render_log

        path = last_video_render_log()
        if path is None or not path.exists():
            self.out.setPlainText("No video render log yet.")
            return
        try:
            self.out.setPlainText(path.read_text(encoding="utf-8", errors="replace")[-12000:])
        except Exception as exc:
            self.out.setPlainText(f"Could not read video render log:\n{exc}")
