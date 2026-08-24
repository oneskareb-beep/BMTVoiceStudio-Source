"""Voice Manager — Piper models + Edge voice browser."""

from __future__ import annotations

import asyncio
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from bmt_voice_studio.config.settings import get_settings, save_settings
from bmt_voice_studio.providers.piper import PIPER_CATALOG, PiperProvider, PiperVoiceManager
from bmt_voice_studio.ui.widgets.common import AudioPlayerBar, card, show_error
from bmt_voice_studio.workers.generation import AsyncWorker, WorkerSignals


class VoiceManagerPage(QWidget):
    status_message = Signal(str)
    voices_refreshed = Signal(list)  # list[VoiceInfo] from edge

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.manager = PiperVoiceManager()
        self.edge_voices = []
        self._signals = WorkerSignals()
        self._build()
        self._wire()
        self.refresh_installed()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)
        title = QLabel("Voice Manager")
        title.setObjectName("pageTitle")
        root.addWidget(title)

        edge_card, edge_l = card("ONLINE VOICES (EDGE TTS)", "Refresh catalog — searchable filters")
        filt = QHBoxLayout()
        self.filter_lang = QComboBox()
        self.filter_lang.setEditable(True)
        self.filter_lang.setPlaceholderText("Language")
        self.filter_locale = QComboBox()
        self.filter_locale.setEditable(True)
        self.filter_gender = QComboBox()
        self.filter_gender.addItems(["Any", "Male", "Female"])
        self.filter_name = QComboBox()
        self.filter_name.setEditable(True)
        self.filter_name.setPlaceholderText("Voice name contains…")
        self.btn_refresh_edge = QPushButton("REFRESH ONLINE VOICES")
        self.btn_refresh_edge.setObjectName("primaryButton")
        for w in (QLabel("Lang"), self.filter_lang, QLabel("Locale"), self.filter_locale,
                  QLabel("Gender"), self.filter_gender, self.filter_name, self.btn_refresh_edge):
            filt.addWidget(w)
        edge_l.addLayout(filt)
        self.edge_list = QListWidget()
        edge_l.addWidget(self.edge_list)
        edge_btns = QHBoxLayout()
        self.btn_preview_edge = QPushButton("Audition Online Voice")
        self.btn_set_male_edge = QPushButton("Assign as Male")
        self.btn_set_female_edge = QPushButton("Assign as Female")
        for b in (self.btn_preview_edge, self.btn_set_male_edge, self.btn_set_female_edge):
            edge_btns.addWidget(b)
        edge_l.addLayout(edge_btns)
        root.addWidget(edge_card, 1)

        piper_card, piper_l = card(
            "OFFLINE PIPER VOICES",
            "Models download to %LOCALAPPDATA%\\BMTVoiceStudio\\models\\ — gender is from catalog metadata, not filenames.",
        )
        self.catalog_list = QListWidget()
        piper_l.addWidget(QLabel("Available to install (incl. sw_CD Congo Swahili):"))
        piper_l.addWidget(self.catalog_list)
        self.installed_list = QListWidget()
        piper_l.addWidget(QLabel("Installed:"))
        piper_l.addWidget(self.installed_list)
        self.card_view = QTextEdit()
        self.card_view.setReadOnly(True)
        self.card_view.setMaximumHeight(100)
        piper_l.addWidget(self.card_view)
        pb = QHBoxLayout()
        self.btn_download = QPushButton("Download Selected Model")
        self.btn_delete = QPushButton("Delete Installed")
        self.btn_preview_piper = QPushButton("Audition Piper Voice")
        self.btn_piper_male = QPushButton("Assign Piper → Male")
        self.btn_piper_female = QPushButton("Assign Piper → Female")
        for b in (
            self.btn_download,
            self.btn_delete,
            self.btn_preview_piper,
            self.btn_piper_male,
            self.btn_piper_female,
        ):
            pb.addWidget(b)
        piper_l.addLayout(pb)
        root.addWidget(piper_card, 1)

        self.player = AudioPlayerBar()
        root.addWidget(self.player)
        self._fill_catalog()

    def _wire(self) -> None:
        self.btn_refresh_edge.clicked.connect(self.refresh_edge)
        self.filter_lang.currentTextChanged.connect(lambda _: self._apply_edge_filter())
        self.filter_locale.currentTextChanged.connect(lambda _: self._apply_edge_filter())
        self.filter_gender.currentTextChanged.connect(lambda _: self._apply_edge_filter())
        self.filter_name.editTextChanged.connect(lambda _: self._apply_edge_filter())
        self.btn_download.clicked.connect(self.download_selected)
        self.btn_delete.clicked.connect(self.delete_selected)
        self.installed_list.currentRowChanged.connect(self._show_card)
        self.btn_set_male_edge.clicked.connect(lambda: self._assign_edge("male"))
        self.btn_set_female_edge.clicked.connect(lambda: self._assign_edge("female"))
        self.btn_piper_male.clicked.connect(lambda: self._assign_piper("male"))
        self.btn_piper_female.clicked.connect(lambda: self._assign_piper("female"))
        self.btn_preview_edge.clicked.connect(self._preview_edge)
        self.btn_preview_piper.clicked.connect(self._preview_piper)
        self._signals.finished.connect(self._on_worker_done)
        self._signals.error.connect(lambda h, t: show_error(self, "Voice Manager", h, t))
        self._signals.log.connect(lambda m: self.status_message.emit(m))

    def _fill_catalog(self) -> None:
        self.catalog_list.clear()
        for c in PIPER_CATALOG:
            size = "?"
            self.catalog_list.addItem(
                f"{c['id']}  ·  {c['locale']}  ·  gender={c['gender']}  ·  {c['quality']}"
            )

    def refresh_installed(self) -> None:
        self.installed_list.clear()
        for v in self.manager.installed_voices():
            size_mb = f"{(v.size_bytes or 0) / 1_000_000:.1f} MB" if v.size_bytes else "?"
            self.installed_list.addItem(
                f"{v.id}  ·  {v.locale}  ·  {v.gender}  ·  {v.quality}  ·  {size_mb}"
            )

    def refresh_edge(self) -> None:
        self.status_message.emit("Refreshing online voices…")
        self.btn_refresh_edge.setEnabled(False)

        async def job(worker):
            from bmt_voice_studio.providers import get_provider

            voices = await get_provider("edge").list_voices()
            return {"edge_voices": voices}

        from PySide6.QtCore import QThreadPool

        QThreadPool.globalInstance().start(AsyncWorker(job, self._signals))

    def _on_worker_done(self, result) -> None:
        self.btn_refresh_edge.setEnabled(True)
        if isinstance(result, dict) and "edge_voices" in result:
            self.edge_voices = result["edge_voices"]
            langs = sorted({v.language for v in self.edge_voices if v.language})
            locales = sorted({v.locale for v in self.edge_voices if v.locale})
            self.filter_lang.clear()
            self.filter_lang.addItem("")
            self.filter_lang.addItems(langs)
            self.filter_locale.clear()
            self.filter_locale.addItem("")
            self.filter_locale.addItems(locales)
            self._apply_edge_filter()
            self.voices_refreshed.emit(self.edge_voices)
            self.status_message.emit(f"Loaded {len(self.edge_voices)} online voices")
        elif isinstance(result, dict) and result.get("downloaded"):
            self.refresh_installed()
            QMessageBox.information(self, "Downloaded", f"Installed {result['downloaded']}")
        elif isinstance(result, dict) and result.get("preview"):
            self.player.play_file(result["preview"])

    def _apply_edge_filter(self) -> None:
        self.edge_list.clear()
        lang = self.filter_lang.currentText().strip().lower()
        locale = self.filter_locale.currentText().strip().lower()
        gender = self.filter_gender.currentText().strip().lower()
        name = self.filter_name.currentText().strip().lower()
        for v in self.edge_voices:
            if lang and v.language.lower() != lang and not v.locale.lower().startswith(lang):
                continue
            if locale and locale not in v.locale.lower():
                continue
            if gender and gender != "any" and v.gender.lower() != gender:
                continue
            if name and name not in v.name.lower():
                continue
            self.edge_list.addItem(f"{v.name}  ·  {v.locale}  ·  {v.gender}")

    def download_selected(self) -> None:
        row = self.catalog_list.currentRow()
        if row < 0:
            return
        voice_id = PIPER_CATALOG[row]["id"]
        self.status_message.emit(f"Downloading {voice_id}…")

        async def job(worker):
            await self.manager.ensure_piper_binary(on_progress=lambda m: self._signals.log.emit(m))
            info = await self.manager.download_voice(
                voice_id, on_progress=lambda m: self._signals.log.emit(m)
            )
            return {"downloaded": info.id}

        from PySide6.QtCore import QThreadPool

        QThreadPool.globalInstance().start(AsyncWorker(job, self._signals))

    def delete_selected(self) -> None:
        row = self.installed_list.currentRow()
        if row < 0:
            return
        voices = self.manager.installed_voices()
        if row >= len(voices):
            return
        vid = voices[row].id
        if QMessageBox.question(self, "Delete", f"Delete {vid}?") != QMessageBox.StandardButton.Yes:
            return
        self.manager.delete_voice(vid)
        self.refresh_installed()

    def _show_card(self, row: int) -> None:
        voices = self.manager.installed_voices()
        if row < 0 or row >= len(voices):
            return
        card_text = self.manager.get_model_card(voices[row].id)
        self.card_view.setPlainText(
            f"License / MODEL_CARD for {voices[row].id}:\n\n{card_text}"
        )

    def _selected_edge_name(self) -> str | None:
        item = self.edge_list.currentItem()
        if not item:
            return None
        return item.text().split("  ·  ")[0].strip()

    def _assign_edge(self, which: str) -> None:
        name = self._selected_edge_name()
        if not name:
            return
        settings = get_settings()
        if which == "male":
            settings.default_male_voice = name
        else:
            settings.default_female_voice = name
        save_settings(settings)
        self.status_message.emit(f"Assigned {name} as default {which}")
        self.voices_refreshed.emit(self.edge_voices)

    def _assign_piper(self, which: str) -> None:
        row = self.installed_list.currentRow()
        voices = self.manager.installed_voices()
        if row < 0 or row >= len(voices):
            return
        settings = get_settings()
        if which == "male":
            settings.piper_male_model = voices[row].id
        else:
            settings.piper_female_model = voices[row].id
        save_settings(settings)
        self.status_message.emit(f"Piper {which} → {voices[row].id}")

    def _preview_edge(self) -> None:
        name = self._selected_edge_name()
        if not name:
            return

        async def job(worker):
            from bmt_voice_studio.config.paths import temp_work_dir
            from bmt_voice_studio.providers import get_provider

            out = temp_work_dir() / "preview_edge.mp3"
            result = await get_provider("edge").preview(name, output_path=str(out))
            if not result.success:
                raise RuntimeError(result.error)
            return {"preview": result.output_path}

        from PySide6.QtCore import QThreadPool

        QThreadPool.globalInstance().start(AsyncWorker(job, self._signals))

    def _preview_piper(self) -> None:
        row = self.installed_list.currentRow()
        voices = self.manager.installed_voices()
        if row < 0 or row >= len(voices):
            return
        vid = voices[row].id

        async def job(worker):
            from bmt_voice_studio.config.paths import temp_work_dir

            out = temp_work_dir() / "preview_piper.wav"
            result = await PiperProvider().preview(vid, output_path=str(out))
            if not result.success:
                raise RuntimeError(result.error)
            return {"preview": result.output_path}

        from PySide6.QtCore import QThreadPool

        QThreadPool.globalInstance().start(AsyncWorker(job, self._signals))
