"""Settings and health-check page."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from bmt_voice_studio.config.pipeline_config import all_settings_match, compare_runtime_to_reference
from bmt_voice_studio.config.presets import BMT_ENGLISH, list_presets
from bmt_voice_studio.config.settings import get_settings, reload_settings, save_settings
from bmt_voice_studio.tools.cloud_fallback_export import export_cloud_fallback_package
from bmt_voice_studio.ui.widgets.common import card
from bmt_voice_studio.workers.generation import HealthController


class SettingsPage(QWidget):
    status_message = Signal(str)
    theme_changed = Signal(str)
    settings_saved = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._health = HealthController()
        self._build()
        self._wire()
        self.load_into_form()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)
        header = QHBoxLayout()
        from bmt_voice_studio.resources import logo_label

        header.addWidget(logo_label(max_width=96, max_height=64))
        title_col = QVBoxLayout()
        title = QLabel("Settings")
        title.setObjectName("pageTitle")
        title_col.addWidget(title)
        brand = QLabel("BBNet • Believers Businessmen Network")
        brand.setObjectName("appSubtitle")
        title_col.addWidget(brand)
        header.addLayout(title_col, 1)
        root.addLayout(header)

        card_f, lay = card("APPLICATION SETTINGS", "Stored locally — no cloud, no telemetry")
        form = QFormLayout()
        self.preset = QComboBox()
        for p in list_presets():
            self.preset.addItem(p.name, p.id)
        self.provider = QComboBox()
        self.provider.addItem("Edge TTS", "edge")
        self.provider.addItem("Piper", "piper")
        self.male = QLineEdit()
        self.female = QLineEdit()
        self.rate = QLineEdit()
        self.pitch = QLineEdit()
        self.pause = QSpinBox()
        self.pause.setRange(0, 5000)
        self.pause.setSingleStep(50)
        self.bitrate = QComboBox()
        for br in (96, 128, 192, 256, 320):
            self.bitrate.addItem(str(br), br)
        self.output = QLineEdit()
        browse = QPushButton("Browse…")
        out_row = QHBoxLayout()
        out_row.addWidget(self.output)
        out_row.addWidget(browse)
        self.theme = QComboBox()
        self.theme.addItems(["dark", "light"])
        self.timeout = QSpinBox()
        self.timeout.setRange(10, 300)
        self.retries = QSpinBox()
        self.retries.setRange(1, 10)
        self.auto_piper = QCheckBox("Automatically fall back to Piper when Edge TTS fails")
        self.norm = QCheckBox("Normalize loudness by default")
        self.start_page = QComboBox()
        self.start_page.addItem("Daily BMT", "daily")
        self.start_page.addItem("TTS Studio", "tts")
        self.start_page.addItem("Last used page", "last")
        form.addRow("Start BMT Voice Studio in", self.start_page)
        form.addRow("Default preset", self.preset)
        form.addRow("Default provider", self.provider)
        form.addRow("Default male voice", self.male)
        form.addRow("Default female voice", self.female)
        form.addRow("Rate", self.rate)
        form.addRow("Pitch", self.pitch)
        form.addRow("Pause (ms)", self.pause)
        form.addRow("MP3 bitrate", self.bitrate)
        form.addRow("Output directory", out_row)
        form.addRow("Theme", self.theme)
        form.addRow("Network timeout (s)", self.timeout)
        form.addRow("Retry count", self.retries)
        form.addRow("", self.auto_piper)
        form.addRow("", self.norm)
        lay.addLayout(form)
        save_row = QHBoxLayout()
        self.btn_save = QPushButton("Save Settings")
        self.btn_save.setObjectName("primaryButton")
        save_row.addWidget(self.btn_save)
        save_row.addStretch(1)
        lay.addLayout(save_row)
        root.addWidget(card_f)
        browse.clicked.connect(self._browse)

        health_card, health_l = card("TEST TTS SERVICES", "Uses a harmless fixed sentence — never your script")
        self.health_out = QTextEdit()
        self.health_out.setReadOnly(True)
        self.btn_health = QPushButton("TEST TTS SERVICES")
        health_l.addWidget(self.btn_health)
        health_l.addWidget(self.health_out)
        root.addWidget(health_card)

        adv_card, adv_l = card(
            "Advanced — Troubleshooting",
            "Optional tools when local Edge TTS or network access fails",
        )
        adv_row = QHBoxLayout()
        self.btn_export_fallback = QPushButton("Export Cloud Fallback Package")
        self.btn_export_fallback.setObjectName("secondaryButton")
        self.btn_verify_ref = QPushButton("Verify against reference config")
        self.btn_verify_ref.setObjectName("tertiaryButton")
        adv_row.addWidget(self.btn_export_fallback)
        adv_row.addWidget(self.btn_verify_ref)
        adv_row.addStretch(1)
        self.fallback_out = QLabel("")
        self.fallback_out.setObjectName("appSubtitle")
        self.fallback_out.setWordWrap(True)
        adv_l.addLayout(adv_row)
        adv_l.addWidget(self.fallback_out)
        root.addWidget(adv_card)
        root.addStretch(1)

    def _wire(self) -> None:
        self.btn_save.clicked.connect(self.save_from_form)
        self.btn_health.clicked.connect(self.run_health)
        self.btn_export_fallback.clicked.connect(self._export_fallback)
        self.btn_verify_ref.clicked.connect(self._verify_reference)
        self._health.signals.finished.connect(self._on_health)
        self._health.signals.error.connect(lambda h, t: self.health_out.append(h))

    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Output folder", self.output.text())
        if path:
            self.output.setText(path)

    def load_into_form(self) -> None:
        s = get_settings()
        idx = self.preset.findData(s.default_preset)
        if idx >= 0:
            self.preset.setCurrentIndex(idx)
        self.provider.setCurrentIndex(0 if s.default_provider == "edge" else 1)
        self.male.setText(s.default_male_voice)
        self.female.setText(s.default_female_voice)
        self.rate.setText(s.rate)
        self.pitch.setText(s.pitch)
        self.pause.setValue(s.pause_ms)
        bi = self.bitrate.findData(s.mp3_bitrate)
        if bi >= 0:
            self.bitrate.setCurrentIndex(bi)
        self.output.setText(s.output_directory)
        self.theme.setCurrentText(s.theme)
        self.timeout.setValue(int(s.network_timeout))
        self.retries.setValue(s.retry_count)
        self.auto_piper.setChecked(s.auto_piper_fallback)
        self.norm.setChecked(s.normalize_loudness)
        sp = self.start_page.findData(getattr(s, "start_page", "daily"))
        if sp >= 0:
            self.start_page.setCurrentIndex(sp)

    def save_from_form(self) -> None:
        s = get_settings()
        s.default_preset = self.preset.currentData()
        s.default_provider = self.provider.currentData()
        s.default_male_voice = self.male.text().strip()
        s.default_female_voice = self.female.text().strip()
        s.rate = self.rate.text().strip() or "+0%"
        s.pitch = self.pitch.text().strip() or "+0Hz"
        s.pause_ms = self.pause.value()
        s.mp3_bitrate = int(self.bitrate.currentData())
        s.output_directory = self.output.text().strip()
        s.theme = self.theme.currentText()
        s.network_timeout = float(self.timeout.value())
        s.retry_count = self.retries.value()
        s.auto_piper_fallback = self.auto_piper.isChecked()
        s.normalize_loudness = self.norm.isChecked()
        s.start_page = self.start_page.currentData() or "daily"
        save_settings(s)
        from bmt_voice_studio.providers import reset_registry

        reset_registry()
        self.theme_changed.emit(s.theme)
        self.settings_saved.emit()
        self.status_message.emit("Settings saved")

    def _export_fallback(self) -> None:
        base = Path(self.output.text().strip() or get_settings().output_directory)
        dest = base / "BMT_Cloud_Fallback_Package"
        try:
            export_cloud_fallback_package(dest)
            self.fallback_out.setText(f"Package exported to: {dest}")
            self.status_message.emit("Cloud fallback package exported")
        except Exception as exc:
            self.fallback_out.setText(f"Export failed: {exc}")

    def _verify_reference(self) -> None:
        s = get_settings()
        preset = BMT_ENGLISH
        rows = compare_runtime_to_reference(
            preset.id,
            pause_ms=s.daily_pause_ms,
            mp3_bitrate=s.daily_bitrate,
            processing_mode="original",
            mastering=s.daily_mastering,
            volume=s.volume,
        )
        lines = []
        for r in rows:
            status = "MATCH" if r.match else "MISMATCH"
            lines.append(f"{r.field}: desktop={r.desktop} reference={r.reference} → {status}")
        header = (
            "ALL SETTINGS MATCH BMT REFERENCE PIPELINE"
            if all_settings_match(rows)
            else "Some settings differ from BMT reference pipeline"
        )
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.information(self, "Reference verification", header + "\n\n" + "\n".join(lines))

    def run_health(self) -> None:
        self.health_out.setPlainText("Running health checks…")
        self._health.start()

    def _on_health(self, status: dict) -> None:
        self.health_out.setPlainText(
            f"Internet: {status.get('internet')}\n"
            f"Edge TTS: {status.get('edge')}\n"
            f"Piper Offline: {status.get('piper')}\n"
            f"FFmpeg: {status.get('ffmpeg')}\n"
        )
