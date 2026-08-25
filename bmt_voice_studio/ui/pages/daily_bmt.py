"""Daily BMT multi-language devotional production page."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from PySide6.QtCore import QDate, QThreadPool, QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from bmt_voice_studio.audio.ffmpeg_service import FFmpegService
from bmt_voice_studio.config.presets import BMT_ENGLISH
from bmt_voice_studio.config.settings import get_settings, save_settings
from bmt_voice_studio.core.job_progress import language_job_percent
from bmt_voice_studio.daily.autosave import (
    clear_draft,
    clear_incomplete,
    draft_has_content,
    load_draft,
    load_incomplete,
    mark_incomplete,
    save_draft,
)
from bmt_voice_studio.daily.history import filter_history, load_history
from bmt_voice_studio.daily.language_config import (
    default_selected_language_ids,
    get_language_config,
    normalize_selected_language_ids,
    production_details_text,
    selectable_daily_languages,
    unapproved_setup_message,
)
from bmt_voice_studio.daily.layout import daily_project_dir
from bmt_voice_studio.daily.naming import display_date, freeze_devotional_date, project_id
from bmt_voice_studio.daily.pipeline import DailyJob, preflight, run_daily_job
from bmt_voice_studio.providers import get_provider
from bmt_voice_studio.ui.studio_keys import bind_shortcut
from bmt_voice_studio.ui.widgets.common import (
    AudioPlayerBar,
    ScrollPage,
    card,
    labeled_field,
    show_error,
    wrap_in_scroll,
)
from bmt_voice_studio.ui.widgets.daily_language_panel import DailyLanguagePanel
from bmt_voice_studio.ui.widgets.language_selector import LanguageSelector
from bmt_voice_studio.workers.generation import AsyncWorker, WorkerSignals


class DailyBMTPage(QWidget):
    status_message = Signal(str)
    job_progress = Signal(int, str)
    job_busy = Signal(bool)
    make_video_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._busy = False
        self._worker: AsyncWorker | None = None
        self._signals = WorkerSignals()
        self._last_result = None
        self._history_entries: list[dict] = []
        self._user_set_date = False
        self._applying_message_date = False
        self._build()
        self._wire()
        self._relayout_panels()
        self._refresh_validation()
        self._load_history()

        if os.environ.get("QT_QPA_PLATFORM") != "offscreen" and os.environ.get("BMT_SKIP_RECOVERY") != "1":
            QTimer.singleShot(400, self._maybe_recover)

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        inner = ScrollPage()
        root = QVBoxLayout(inner)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(16)

        header = QHBoxLayout()
        header.setSpacing(12)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        title = QLabel("Today's audio")
        title.setObjectName("pageTitle")
        subtitle = QLabel("Date and languages, then the scripts — Generate when ready")
        subtitle.setObjectName("appSubtitle")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        header.addLayout(titles, 1)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setObjectName("dangerButton")
        self.btn_cancel.setEnabled(False)
        self.btn_generate = QPushButton("Generate today's devotional")
        self.btn_generate.setObjectName("primaryButton")
        self.btn_generate.setMinimumHeight(44)
        self.btn_generate.setToolTip("Ctrl+Enter")
        self.btn_generate_main = self.btn_generate
        header.addWidget(self.btn_cancel)
        header.addWidget(self.btn_generate)
        root.addLayout(header)

        date_card, date_layout = card("A. Devotional Date", "")
        date_row = QHBoxLayout()
        date_row.setSpacing(16)
        self.date = QDateEdit()
        self.date.setCalendarPopup(True)
        self.date.setDate(QDate.currentDate())
        self.date.setDisplayFormat("dddd, MMMM d, yyyy")
        self.date.setMinimumWidth(260)
        self.date.setToolTip("This follows the date printed in the pasted message, not today's clock date.")
        self.lbl_date_source = QLabel("Paste the script — the date in the message sets the production folder.")
        self.lbl_date_source.setObjectName("appSubtitle")
        self.lbl_date_source.setWordWrap(True)
        self.lbl_project = QLabel()
        self.lbl_project.setObjectName("taskLabel")
        self.lbl_project.setWordWrap(True)
        self.lbl_project.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        date_row.addWidget(labeled_field("Date", self.date), 0)
        date_row.addWidget(self.lbl_project, 1)
        date_layout.addLayout(date_row)
        date_layout.addWidget(self.lbl_date_source)
        root.addWidget(date_card)

        selector_card, selector_layout = card("B. Languages to Generate", "")
        self.language_selector = LanguageSelector()
        saved_ids = getattr(get_settings(), "daily_selected_languages", None)
        self.language_selector.set_selected_ids(
            normalize_selected_language_ids(saved_ids or default_selected_language_ids())
        )
        selector_layout.addWidget(self.language_selector)
        root.addWidget(selector_card)

        root.addWidget(self._make_script_area())

        ready_configs = [
            cfg for cfg in selectable_daily_languages() if cfg.production_approved
        ]
        details_card, details_layout = card("Production Details", "Informational only")
        self.btn_toggle_details = QPushButton("Show production details")
        self.btn_toggle_details.setObjectName("tertiaryButton")
        self.details_body = QLabel(production_details_text(ready_configs))
        self.details_body.setObjectName("appSubtitle")
        self.details_body.setWordWrap(True)
        self.details_body.hide()
        details_layout.addWidget(self.btn_toggle_details)
        details_layout.addWidget(self.details_body)
        root.addWidget(details_card)

        status_card, status_layout = card("Language status", "")
        self.lbl_current = QLabel("Current task: Waiting")
        self.lbl_current.setObjectName("taskLabel")
        self.lbl_current.setWordWrap(True)
        self.lbl_overall = QLabel("Overall Progress: 0%")
        self.lbl_overall.setObjectName("taskLabel")
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("%p%")
        self.progress.setTextVisible(True)
        self.lbl_overall.hide()
        self.progress.hide()
        status_layout.addWidget(self.lbl_overall)
        status_layout.addWidget(self.progress)

        self.lang_states_host = QWidget()
        self._lang_states_layout = QVBoxLayout(self.lang_states_host)
        self._lang_states_layout.setContentsMargins(0, 0, 0, 0)
        self._lang_states_layout.setSpacing(4)
        self.lang_state_labels: dict[str, QLabel] = {}
        for cfg in selectable_daily_languages():
            label = QLabel(f"{cfg.display_name}: NOT SELECTED")
            label.setObjectName("appSubtitle")
            self.lang_state_labels[cfg.language_id] = label
            self._lang_states_layout.addWidget(label)
        self.lbl_en_state = self.lang_state_labels["en"]
        self.lbl_fr_state = self.lang_state_labels["fr"]
        self.lbl_sw_state = self.lang_state_labels["sw"]
        self.lbl_pt_state = self.lang_state_labels["pt"]
        status_layout.addWidget(self.lang_states_host)
        status_layout.addWidget(self.lbl_current)

        self.checklist_host = QWidget()
        self._check_layout = QGridLayout(self.checklist_host)
        self._check_layout.setContentsMargins(0, 4, 0, 0)
        self._check_layout.setHorizontalSpacing(18)
        self._check_layout.setVerticalSpacing(6)
        status_layout.addWidget(self.checklist_host)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(1)
        self.log.hide()
        status_layout.addWidget(self.log)
        root.addWidget(status_card)

        output_card, output_layout = card("Outputs", "")
        self.out_card = output_card
        self.out_summary = QLabel("No production yet.")
        self.out_summary.setObjectName("taskLabel")
        self.out_summary.setWordWrap(True)
        output_layout.addWidget(self.out_summary)
        self.out_rows_host = QWidget()
        self._out_rows_layout = QVBoxLayout(self.out_rows_host)
        self._out_rows_layout.setContentsMargins(0, 8, 0, 0)
        self._out_rows_layout.setSpacing(10)
        self.out_rows_host.hide()
        output_layout.addWidget(self.out_rows_host)

        output_actions = QHBoxLayout()
        self.btn_report = QPushButton("View Production Report")
        self.btn_report.setEnabled(False)
        self.btn_new = QPushButton("New daily production")
        self.btn_new.setObjectName("tertiaryButton")
        self.btn_new.setEnabled(False)
        self.btn_make_video = QPushButton("Make video")
        self.btn_make_video.setObjectName("secondaryButton")
        self.btn_make_video.setEnabled(False)
        self.btn_make_video.setToolTip("Open Video Maker for this date")
        output_actions.addWidget(self.btn_report)
        output_actions.addWidget(self.btn_new)
        output_actions.addWidget(self.btn_make_video)
        output_actions.addStretch(1)
        output_layout.addLayout(output_actions)
        self.player = AudioPlayerBar()
        output_layout.addWidget(self.player)
        root.addWidget(output_card)

        history_card, history_layout = card(
            "Daily production history", "Stored locally on this computer"
        )
        filters = QHBoxLayout()
        self.hist_year = QComboBox()
        self.hist_year.addItem("All years", 0)
        for year in range(date.today().year, date.today().year - 6, -1):
            self.hist_year.addItem(str(year), year)
        self.hist_month = QComboBox()
        self.hist_month.addItem("All months", 0)
        for month, name in enumerate(
            ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
            start=1,
        ):
            self.hist_month.addItem(name, month)
        self.hist_status = QComboBox()
        self.hist_status.addItems(["ALL", "COMPLETE", "WARNING", "FAILED"])
        self.hist_search = QComboBox()
        self.hist_search.setEditable(True)
        if self.hist_search.lineEdit():
            self.hist_search.lineEdit().setPlaceholderText("Search…")
        filters.addWidget(labeled_field("Year", self.hist_year, stretch=0))
        filters.addWidget(labeled_field("Month", self.hist_month, stretch=0))
        filters.addWidget(labeled_field("Status", self.hist_status, stretch=0))
        filters.addWidget(labeled_field("Search", self.hist_search, stretch=1), 1)
        history_layout.addLayout(filters)

        history_actions = QHBoxLayout()
        self.btn_hist_refresh = QPushButton("Refresh")
        self.btn_hist_refresh.setObjectName("tertiaryButton")
        self.btn_open_hist = QPushButton("Open")
        self.btn_open_hist.setObjectName("secondaryButton")
        self.btn_play_hist_en = QPushButton("Play EN")
        self.btn_play_hist_fr = QPushButton("Play FR")
        self.btn_play_hist_sw = QPushButton("Play SW")
        self.btn_play_hist_pt = QPushButton("Play PT")
        self.btn_hist_report = QPushButton("View Report")
        for button in (
            self.btn_hist_refresh,
            self.btn_open_hist,
            self.btn_play_hist_en,
            self.btn_play_hist_fr,
            self.btn_play_hist_sw,
            self.btn_play_hist_pt,
            self.btn_hist_report,
        ):
            button.setMinimumWidth(0)
            history_actions.addWidget(button)
        history_actions.addStretch(1)
        history_layout.addLayout(history_actions)

        self.btn_dup = QPushButton("Use previous day as template")
        self.btn_dup.setObjectName("tertiaryButton")
        duplicate_row = QHBoxLayout()
        duplicate_row.addWidget(self.btn_dup)
        duplicate_row.addStretch(1)
        history_layout.addLayout(duplicate_row)

        self.hist_table = QTableWidget(0, 8)
        self.hist_table.setHorizontalHeaderLabels(
            ["Date", "EN", "FR", "SW", "PT", "Status", "Duration", "Folder"]
        )
        self.hist_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.hist_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.hist_table.setMinimumHeight(180)
        history_layout.addWidget(self.hist_table)
        self._history_expanded = False
        hist_bar = QFrame()
        hist_bar.setObjectName("histCollapseBar")
        hist_bar_l = QHBoxLayout(hist_bar)
        hist_bar_l.setContentsMargins(14, 8, 14, 8)
        hist_bar_l.setSpacing(10)
        self.lbl_hist_title = QLabel("Daily history")
        self.lbl_hist_title.setObjectName("cardTitle")
        self.btn_hist_toggle = QPushButton("Expand")
        self.btn_hist_toggle.setObjectName("tertiaryButton")
        hist_bar_l.addWidget(self.lbl_hist_title)
        hist_bar_l.addStretch(1)
        hist_bar_l.addWidget(self.btn_hist_toggle)
        history_card.hide()
        self._hist_bar = hist_bar
        self._hist_body = history_card
        root.addWidget(hist_bar)
        root.addWidget(history_card)

        self._update_project_label()
        outer.addWidget(wrap_in_scroll(inner))

    def _make_script_area(self) -> QWidget:
        host = QWidget()
        self._panels_host = host
        host.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self._panels_layout = QGridLayout(host)
        self._panels_layout.setContentsMargins(0, 0, 0, 0)
        self._panels_layout.setHorizontalSpacing(16)
        self._panels_layout.setVerticalSpacing(16)

        self.lang_panels: dict[str, DailyLanguagePanel] = {}
        for cfg in selectable_daily_languages():
            self.lang_panels[cfg.language_id] = DailyLanguagePanel(cfg)

        self.en_panel = self.lang_panels["en"]
        self.fr_panel = self.lang_panels["fr"]
        self.sw_panel = self.lang_panels["sw"]
        self.pt_panel = self.lang_panels["pt"]
        self.en_edit = self.en_panel.edit
        self.fr_edit = self.fr_panel.edit
        self.sw_edit = self.sw_panel.edit
        self.pt_edit = self.pt_panel.edit
        self.en_status = self.en_panel.status
        self.fr_status = self.fr_panel.status
        self.sw_status = self.sw_panel.status
        self.pt_status = self.pt_panel.status
        self.en_counts = self.en_panel.counts
        self.fr_counts = self.fr_panel.counts
        self.sw_counts = self.sw_panel.counts
        self.pt_counts = self.pt_panel.counts
        self.en_box = self.en_panel
        self.fr_box = self.fr_panel
        self.sw_box = self.sw_panel
        self.pt_box = self.pt_panel
        return host

    def _wire(self) -> None:
        self.date.dateChanged.connect(self._on_date)
        self.language_selector.selection_changed.connect(self._on_selection_changed)
        for panel in self.lang_panels.values():
            panel.text_changed.connect(self._on_text)
            panel.validate_requested.connect(self._refresh_validation)
        self.btn_generate.clicked.connect(self.generate)
        self.btn_cancel.clicked.connect(self._cancel)
        self.btn_toggle_details.clicked.connect(self._toggle_details)
        self.btn_report.clicked.connect(self._open_report)
        self.btn_new.clicked.connect(self._new_day)
        self.btn_make_video.clicked.connect(self.make_video_requested.emit)
        self.btn_hist_toggle.clicked.connect(self._toggle_history)
        self.btn_hist_refresh.clicked.connect(self._load_history)
        self.hist_year.currentIndexChanged.connect(self._load_history)
        self.hist_month.currentIndexChanged.connect(self._load_history)
        self.hist_status.currentIndexChanged.connect(self._load_history)
        self.hist_search.editTextChanged.connect(self._load_history)
        self.btn_open_hist.clicked.connect(self._open_history_row)
        self.btn_play_hist_en.clicked.connect(lambda: self._play_history("en"))
        self.btn_play_hist_fr.clicked.connect(lambda: self._play_history("fr"))
        self.btn_play_hist_sw.clicked.connect(lambda: self._play_history("sw"))
        self.btn_play_hist_pt.clicked.connect(lambda: self._play_history("pt"))
        self.btn_hist_report.clicked.connect(self._open_history_report)
        self.btn_dup.clicked.connect(self._duplicate_template)
        self._signals.progress.connect(self._on_progress)
        self._signals.log.connect(self._append_log)
        self._signals.finished.connect(self._on_done)
        self._signals.error.connect(self._on_error)
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setInterval(2500)
        self._autosave_timer.timeout.connect(self._autosave)
        self._autosave_timer.start()
        bind_shortcut(self, "Ctrl+Return", self.generate)
        bind_shortcut(self, "Ctrl+Enter", self.generate)
        bind_shortcut(self, "Space", self._play_last_mp3, idle_only=True)

    def selected_date(self) -> date:
        """Return the frozen calendar date selected in the UI."""
        return freeze_devotional_date(self.date.date())

    def _selected_ids(self) -> list[str]:
        return normalize_selected_language_ids(self.language_selector.selected_ids())

    def _on_selection_changed(self, selected_ids: list[str]) -> None:
        selected = normalize_selected_language_ids(selected_ids)
        settings = get_settings()
        settings.daily_selected_languages = selected
        save_settings(settings)
        self._relayout_panels()
        self._reset_unselected_states()
        self._refresh_validation()
        self._autosave()

    def _relayout_panels(self) -> None:
        selected = self._selected_ids()
        while self._panels_layout.count():
            item = self._panels_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(self._panels_host)
        for language_id, panel in self.lang_panels.items():
            panel.setVisible(language_id in selected)
        n = len(selected)
        if n == 1:
            self._panels_layout.addWidget(self.lang_panels[selected[0]], 0, 0, 1, 2)
        elif n == 2:
            self._panels_layout.addWidget(self.lang_panels[selected[0]], 0, 0)
            self._panels_layout.addWidget(self.lang_panels[selected[1]], 0, 1)
        elif n == 3:
            self._panels_layout.addWidget(self.lang_panels[selected[0]], 0, 0)
            self._panels_layout.addWidget(self.lang_panels[selected[1]], 0, 1)
            self._panels_layout.addWidget(self.lang_panels[selected[2]], 1, 0, 1, 2)
        else:
            for index, language_id in enumerate(selected):
                self._panels_layout.addWidget(
                    self.lang_panels[language_id], index // 2, index % 2
                )
        self._reset_unselected_states()
        self.language_selector.refresh_readiness()
        ready_configs = selectable_daily_languages()
        self.details_body.setText(production_details_text(ready_configs))

    def _reset_unselected_states(self) -> None:
        selected = set(self._selected_ids())
        for language_id, label in self.lang_state_labels.items():
            cfg = get_language_config(language_id)
            name = cfg.display_name if cfg else language_id.upper()
            if language_id in selected:
                if "NOT SELECTED" in label.text():
                    label.setText(f"{name}: WAITING")
                label.show()
            else:
                label.setText(f"{name}: NOT SELECTED")
                label.hide()

    def _on_date(self) -> None:
        if not self._applying_message_date:
            self._user_set_date = True
        self._update_project_label()
        self._autosave()

    def _update_project_label(self) -> None:
        devotional_date = self.selected_date()
        self.lbl_project.setText(
            f"{display_date(devotional_date)}  ·  {project_id(devotional_date)}"
        )

    def _on_text(self) -> None:
        self._apply_date_from_message()
        self._refresh_validation()

    def _apply_date_from_message(self) -> None:
        from bmt_voice_studio.daily.message_date import detect_message_date

        blob = "\n".join(panel.text() for panel in self.lang_panels.values())
        found = detect_message_date(blob, today=self.selected_date())
        if found is None:
            self.lbl_date_source.setText(
                "No date found in the message yet. Paste the header so the folder uses that date, not today."
            )
            return
        current = self.selected_date()
        self.lbl_date_source.setText(
            f"Using the date in the message: {found.strftime('%A, %B %d, %Y').replace(' 0', ' ')}"
        )
        if found == current:
            return
        self._applying_message_date = True
        try:
            self.date.setDate(QDate(found.year, found.month, found.day))
            self._user_set_date = False
        finally:
            self._applying_message_date = False

    def _refresh_validation(self) -> None:
        validations = {
            language_id: self.lang_panels[language_id].refresh_validation()
            for language_id in self._selected_ids()
        }
        self._update_checklist(validations)

    def _update_checklist(self, validations: dict[str, object]) -> None:
        items: list[tuple[str, bool]] = []
        for language_id in self._selected_ids():
            cfg = get_language_config(language_id)
            result = validations[language_id]
            items.append((f"{cfg.display_name if cfg else language_id} script ready", bool(result.ok)))
        ffmpeg_ok, _ = FFmpegService().health_check()
        items.append(("Audio tools ready", ffmpeg_ok))
        try:
            get_provider("edge")
            items.append(("Voice service ready", True))
        except Exception:
            items.append(("Voice service ready", False))

        while self._check_layout.count():
            item = self._check_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for index, (name, ok) in enumerate(items):
            label = QLabel(("✓  " if ok else "✗  ") + name)
            label.setObjectName("appSubtitle")
            label.setWordWrap(True)
            label.setStyleSheet(f"color:{'#7FD99A' if ok else '#F07178'};")
            self._check_layout.addWidget(label, index // 2, index % 2)

        enabled = not self._busy and all(ok for _, ok in items)
        self.btn_generate.setEnabled(enabled)
        self.btn_generate_main.setEnabled(enabled)

    def _toggle_details(self) -> None:
        visible = not self.details_body.isVisible()
        self.details_body.setVisible(visible)
        self.btn_toggle_details.setText(
            "Hide production details" if visible else "Show production details"
        )

    @staticmethod
    def _friendly_error(raw: str) -> str:
        text = (raw or "").strip()
        low = text.lower()
        if "piper model" in low or "piperprovider" in low:
            return "BMT VOICE SERVICE TEMPORARILY UNAVAILABLE"
        if "edge tts" in low and any(
            token in low for token in ("unavail", "fail", "connection")
        ):
            return "BMT VOICE SERVICE TEMPORARILY UNAVAILABLE"
        if "internet" in low or "network" in low:
            return "INTERNET CONNECTION REQUIRED"
        if "ffmpeg" in low:
            return "OUTPUT FOLDER ERROR"
        for language in ("english", "french", "swahili", "portuguese"):
            if language in low and any(
                token in low for token in ("invalid", "script", "brace")
            ):
                return f"{language.upper()} SCRIPT INVALID"
        if raw.startswith("PRODUCTION_SETUP_REQUIRED:"):
            parts = raw.split(":", 2)
            return parts[2] if len(parts) > 2 else raw
        return text or "GENERATION FAILED"

    def _job(self, *, only_language: str | None = None) -> DailyJob:
        selected = {only_language} if only_language else set(self._selected_ids())
        return DailyJob(
            date=self.selected_date(),
            english_text=self.en_panel.text(),
            french_text=self.fr_panel.text(),
            swahili_text=self.sw_panel.text(),
            portuguese_text=self.pt_panel.text(),
            generate_english="en" in selected,
            generate_french="fr" in selected,
            generate_swahili="sw" in selected,
            generate_portuguese="pt" in selected,
            pause_ms=BMT_ENGLISH.pipeline.pause_ms,
            target_lufs=-16.0,
            mastering=False,
            export_mp3=True,
            export_wav=False,
            mp3_bitrate=BMT_ENGLISH.pipeline.mp3_bitrate_kbps,
            provider="edge",
            use_piper_fallback=False,
            processing_mode="original",
            strict_source_mode=True,
        )

    def _open_voice_setup(self, language_id: str | None = None) -> None:
        from bmt_voice_studio.ui.dialogs.regional_voice_setup import RegionalVoiceSetupDialog

        dlg = RegionalVoiceSetupDialog(self, focus_language=language_id)
        dlg.exec()
        self.language_selector.refresh_readiness()
        self.details_body.setText(production_details_text(selectable_daily_languages()))
        self._refresh_validation()

    def generate(self) -> None:
        if self._busy:
            return
        for language_id in self._selected_ids():
            cfg = get_language_config(language_id)
            validation = self.lang_panels[language_id].refresh_validation()
            name = cfg.display_name.upper() if cfg else language_id.upper()
            if not self.lang_panels[language_id].text().strip():
                message = f"{name} SCRIPT REQUIRED"
                show_error(self, message, message)
                return
            if not validation.ok:
                message = f"{name} SCRIPT INVALID"
                show_error(self, message, self._friendly_error(message))
                return
            if cfg is not None and not cfg.production_approved:
                box = QMessageBox(self)
                box.setIcon(QMessageBox.Icon.Warning)
                box.setWindowTitle("Production setup required")
                box.setText(unapproved_setup_message(language_id))
                open_btn = box.addButton("Open Voice Setup", QMessageBox.ButtonRole.AcceptRole)
                box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
                box.exec()
                if box.clickedButton() == open_btn:
                    self._open_voice_setup(language_id)
                return
        job = self._job()
        issues = preflight(job)
        if issues:
            setup = next((i for i in issues if i.startswith("PRODUCTION_SETUP_REQUIRED:")), None)
            if setup:
                parts = setup.split(":", 2)
                lang_id = parts[1] if len(parts) > 1 else None
                box = QMessageBox(self)
                box.setIcon(QMessageBox.Icon.Warning)
                box.setWindowTitle("Production setup required")
                box.setText(parts[2] if len(parts) > 2 else setup)
                open_btn = box.addButton("Open Voice Setup", QMessageBox.ButtonRole.AcceptRole)
                box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
                box.exec()
                if box.clickedButton() == open_btn:
                    self._open_voice_setup(lang_id)
                return
            show_error(
                self,
                "Cannot start production",
                "\n".join(self._friendly_error(issue) for issue in issues),
            )
            return
        self._start_job(job)

    def _start_job(self, job: DailyJob) -> None:
        self._busy = True
        self.btn_generate.setEnabled(False)
        self.btn_generate_main.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.progress.setValue(0)
        self.progress.setRange(0, 100)
        self.lbl_overall.setText("Overall Progress: 0%")
        self.job_busy.emit(True)
        self.job_progress.emit(0, f"Starting {display_date(job.date)}")
        generated_ids = set(job.selected_language_ids())
        for language_id, label in self.lang_state_labels.items():
            cfg = get_language_config(language_id)
            name = cfg.display_name if cfg else language_id.upper()
            if language_id in generated_ids:
                label.setText(f"{name}: WAITING")
                label.setVisible(language_id in self._selected_ids())
                self.lang_panels[language_id].set_status_label("WAITING")
            elif language_id not in self._selected_ids():
                label.setText(f"{name}: NOT SELECTED")
                label.hide()
        self.lbl_current.setText(f"Current task: Starting {display_date(job.date)}")
        mark_incomplete(
            {
                "date": job.date.isoformat(),
                "folder": str(daily_project_dir(job.date)),
                "selected_languages": job.selected_language_ids(),
            }
        )
        selected = job.selected_language_ids()
        page = self

        async def work(worker: AsyncWorker):
            def progress(language, current, total, message):
                pct = language_job_percent(language, current, total, selected)
                page._signals.progress.emit(pct, 100, message)
                page._signals.log.emit(message)

            return await run_daily_job(
                job, on_progress=progress, cancel_check=worker.is_cancelled
            )

        self._worker = AsyncWorker(work, self._signals)
        QThreadPool.globalInstance().start(self._worker)

    def _cancel(self) -> None:
        if self._worker:
            self._worker.cancel()
        self.lbl_current.setText(
            "Current task: Cancel requested — completed segments are kept."
        )

    def _on_progress(self, current: int, total: int, message: str) -> None:
        percent = int(round(100 * current / max(1, total)))
        self.progress.setMaximum(100)
        self.progress.setValue(percent)
        short = (message or "").strip()
        if len(short) > 48:
            short = short[:45] + "…"
        self.progress.setFormat(f"{percent}%  {short}" if short else "%p%")
        self.lbl_overall.setText(f"Overall Progress: {percent}%")
        self.lbl_current.setText(f"Current task: {message}")
        self.job_progress.emit(percent, message)
        low = (message or "").lower()
        for language_id, panel in self.lang_panels.items():
            cfg = get_language_config(language_id)
            if cfg and cfg.display_name.lower() in low:
                if any(word in low for word in ("join", "export", "master", "finaliz", "artwork")):
                    state = "EXPORTING"
                elif "complete" in low:
                    state = "COMPLETE"
                else:
                    state = "GENERATING"
                self.lang_state_labels[language_id].setText(
                    f"{cfg.display_name}: {state}"
                )
                panel.set_status_label(state)
        self.status_message.emit(message)

    def _append_log(self, message: str) -> None:
        self.log.append(message)

    @staticmethod
    def _result_block(result, language_id: str):
        return getattr(
            result,
            {"en": "english", "fr": "french", "sw": "swahili", "pt": "portuguese"}[language_id],
        )

    def _on_done(self, result) -> None:
        self._busy = False
        self.btn_cancel.setEnabled(False)
        self._last_result = result
        blocks = [
            self._result_block(result, language_id)
            for language_id in ("en", "fr", "sw", "pt")
        ]
        cancelled = "cancelled" in " ".join(result.errors or []).lower() or any(
            bool(block and block.get("cancelled")) for block in blocks
        )
        if not cancelled:
            clear_incomplete()
        self._refresh_validation()
        self._load_history()
        self.btn_new.setEnabled(True)
        self.btn_report.setEnabled(
            bool(result.report_md and Path(result.report_md).exists())
        )

        for language_id in ("en", "fr", "sw", "pt"):
            block = self._result_block(result, language_id)
            if block and block.get("selected") is not False:
                ok = bool(block.get("ok"))
                cfg = get_language_config(language_id)
                name = cfg.display_name if cfg else language_id.upper()
                state = "COMPLETE" if ok else "FAILED"
                self.lang_state_labels[language_id].setText(f"{name}: {state}")
                self.lang_panels[language_id].set_status_label(state)
        self._reset_unselected_states()
        self._render_outputs(result)

        if result.ok:
            self.lbl_current.setText("Current task: Today's devotional is ready")
            self.progress.setValue(self.progress.maximum())
            self.lbl_overall.setText("Overall Progress: 100%")
            self.job_progress.emit(100, "Today's devotional is ready")
            self.job_busy.emit(False)
            self.btn_make_video.setEnabled(True)
            QMessageBox.information(self, "Ready", "Today's devotional is ready.")
        else:
            detail = (
                "\n".join(self._friendly_error(error) for error in (result.errors or []))
                or ("One or more selected languages failed." if result.status == "WARNING" else result.status)
            )
            self.job_busy.emit(False)
            show_error(self, "GENERATION FAILED", detail)

    def _clear_output_rows(self) -> None:
        while self._out_rows_layout.count():
            item = self._out_rows_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _render_outputs(self, result) -> None:
        self._clear_output_rows()
        generated: list[tuple[str, dict]] = []
        for language_id in ("en", "fr", "sw", "pt"):
            block = self._result_block(result, language_id)
            if block and block.get("selected") is not False:
                generated.append((language_id, block))

        self.out_rows_host.setVisible(bool(generated))
        if not generated:
            self.out_summary.setText("No production yet.")
            return
        summary = [f"Status: {result.status}"]
        if result.folder:
            summary.append(f"Folder: {result.folder}")
        self.out_summary.setText("\n".join(summary))

        for language_id, block in generated:
            cfg = get_language_config(language_id)
            row_widget = QWidget()
            row = QHBoxLayout(row_widget)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(8)
            name = QLabel(cfg.display_name if cfg else language_id.upper())
            name.setObjectName("cardTitle")
            files = QLabel(self._file_line(block))
            files.setObjectName("taskLabel")
            row.addWidget(name)
            row.addWidget(files, 1)

            play = QPushButton("Play")
            play.setObjectName("secondaryButton")
            play.setEnabled(bool(block.get("final_mp3")))
            play.clicked.connect(
                lambda _checked=False, lid=language_id: self._play_lang(lid)
            )
            row.addWidget(play)

            open_mp3 = QPushButton("Open MP3")
            open_mp3.setObjectName("secondaryButton")
            open_mp3.setEnabled(bool(block.get("final_mp3")))
            open_mp3.clicked.connect(
                lambda _checked=False, lid=language_id: self._open_output(lid, "mp3")
            )
            row.addWidget(open_mp3)

            open_folder = QPushButton("Open Folder")
            open_folder.setObjectName("secondaryButton")
            open_folder.clicked.connect(self._open_folder)
            row.addWidget(open_folder)

            if not block.get("ok"):
                retry = QPushButton(f"Retry {cfg.display_name if cfg else language_id.upper()}")
                retry.clicked.connect(
                    lambda _checked=False, lid=language_id: self._retry(lid)
                )
                row.addWidget(retry)
            self._out_rows_layout.addWidget(row_widget)

    @staticmethod
    def _file_line(block: dict | None) -> str:
        if not block:
            return "Not generated"
        probe = block.get("mp3_probe") or {}
        mark = "Complete" if block.get("ok") else "Failed"
        mp3 = "MP3 ✓" if block.get("final_mp3") else "MP3 —"
        duration = probe.get("duration_sec", "?")
        return f"{mark}  ·  {mp3}  ·  {duration} sec"

    def _on_error(self, human: str, technical: str) -> None:
        self._busy = False
        self.btn_cancel.setEnabled(False)
        self._refresh_validation()
        self.job_busy.emit(False)
        show_error(self, "GENERATION FAILED", self._friendly_error(human), technical)

    def _play_lang(self, language_id: str) -> None:
        if not self._last_result:
            return
        block = self._result_block(self._last_result, language_id)
        path = (block or {}).get("final_mp3")
        if path and Path(path).exists():
            self.player.play_file(path)

    def _play_last_mp3(self) -> None:
        if not self._last_result:
            return
        for language_id in list(self._selected_ids()) + ["en", "fr", "sw", "pt"]:
            block = self._result_block(self._last_result, language_id)
            path = (block or {}).get("final_mp3")
            if path and Path(path).exists():
                self.player.play_file(path)
                return

    def _toggle_history(self) -> None:
        self._history_expanded = not self._history_expanded
        self._hist_body.setVisible(self._history_expanded)
        self.btn_hist_toggle.setText("Collapse" if self._history_expanded else "Expand")

    def _open_output(self, language_id: str, kind: str) -> None:
        if not self._last_result:
            return
        block = self._result_block(self._last_result, language_id)
        key = "final_mp3" if kind == "mp3" else "final_wav"
        path = (block or {}).get(key)
        if path and Path(path).exists():
            os.startfile(path)  # noqa: S606

    def _open_folder(self) -> None:
        folder = (
            self._last_result.folder
            if self._last_result and self._last_result.folder
            else str(daily_project_dir(self.selected_date()))
        )
        if folder and Path(folder).exists():
            os.startfile(folder)  # noqa: S606

    def _open_report(self) -> None:
        if (
            self._last_result
            and self._last_result.report_md
            and Path(self._last_result.report_md).exists()
        ):
            os.startfile(self._last_result.report_md)  # noqa: S606

    def _new_day(self) -> None:
        for panel in self.lang_panels.values():
            panel.edit.clear()
        self.date.setDate(QDate.currentDate())
        self._last_result = None
        self.out_summary.setText("No production yet.")
        self._clear_output_rows()
        self.out_rows_host.hide()
        self.btn_report.setEnabled(False)
        self.btn_new.setEnabled(False)
        self.btn_make_video.setEnabled(False)
        clear_draft()
        self._reset_unselected_states()
        self._refresh_validation()

    def _retry(self, language_id: str) -> None:
        if self._busy or not self._last_result:
            return
        block = self._result_block(self._last_result, language_id)
        if not block or block.get("selected") is False or block.get("ok"):
            return
        cfg = get_language_config(language_id)
        if cfg is not None and not cfg.production_approved:
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Icon.Warning)
            box.setWindowTitle("Production setup required")
            box.setText(unapproved_setup_message(language_id))
            open_btn = box.addButton("Open Voice Setup", QMessageBox.ButtonRole.AcceptRole)
            box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
            box.exec()
            if box.clickedButton() == open_btn:
                self._open_voice_setup(language_id)
            return
        self._start_job(self._job(only_language=language_id))

    def _autosave(self) -> None:
        selected = self._selected_ids()
        save_draft(
            {
                "date": self.selected_date().isoformat(),
                "english_text": self.en_edit.toPlainText(),
                "french_text": self.fr_edit.toPlainText(),
                "swahili_text": self.sw_edit.toPlainText(),
                "portuguese_text": self.pt_edit.toPlainText(),
                "selected_languages": selected,
                "generate_english": "en" in selected,
                "generate_french": "fr" in selected,
                "generate_swahili": "sw" in selected,
                "generate_portuguese": "pt" in selected,
                "pause_ms": BMT_ENGLISH.pipeline.pause_ms,
            }
        )

    def _maybe_recover(self) -> None:
        incomplete = load_incomplete()
        if incomplete:
            answer = QMessageBox.question(
                self,
                "Incomplete production found",
                "An interrupted Daily BMT production was found.\nResume from cached segments?",
            )
            if answer == QMessageBox.StandardButton.Yes:
                iso = incomplete.get("date")
                if iso:
                    devotional_date = freeze_devotional_date(iso)
                    self.date.setDate(
                        QDate(devotional_date.year, devotional_date.month, devotional_date.day)
                    )
                draft = load_draft()
                if draft:
                    self._apply_draft(draft)
                clear_incomplete()
                return
            clear_incomplete()
        draft = load_draft()
        has_draft_text = draft_has_content(draft) or bool(
            draft
            and (
                (draft.get("swahili_text") or "").strip()
                or (draft.get("portuguese_text") or "").strip()
            )
        )
        if has_draft_text:
            answer = QMessageBox.question(
                self,
                "Recover unsaved daily production",
                "A local Daily BMT draft was found. Restore it?",
            )
            if answer == QMessageBox.StandardButton.Yes:
                self._apply_draft(draft)

    def _apply_draft(self, draft: dict) -> None:
        iso = draft.get("date")
        if iso:
            try:
                devotional_date = freeze_devotional_date(iso)
                self.date.setDate(
                    QDate(devotional_date.year, devotional_date.month, devotional_date.day)
                )
            except Exception:
                pass
        self.en_edit.setPlainText(draft.get("english_text") or "")
        self.fr_edit.setPlainText(draft.get("french_text") or "")
        self.sw_edit.setPlainText(draft.get("swahili_text") or "")
        self.pt_edit.setPlainText(draft.get("portuguese_text") or "")
        selected = normalize_selected_language_ids(
            draft.get("selected_languages") or default_selected_language_ids()
        )
        self.language_selector.set_selected_ids(selected)
        settings = get_settings()
        settings.daily_selected_languages = selected
        save_settings(settings)
        self._relayout_panels()
        self._reset_unselected_states()
        self._apply_date_from_message()
        self._refresh_validation()

    @staticmethod
    def _history_mark(value) -> str:
        if value is True:
            return "✓"
        if value is False:
            return "✕"
        return "—"

    def _load_history(self) -> None:
        entries = filter_history(
            load_history(),
            year=self.hist_year.currentData() or None,
            month=self.hist_month.currentData() or None,
            status=self.hist_status.currentText(),
            query=self.hist_search.currentText(),
        )
        self.hist_table.setRowCount(len(entries))
        for row, entry in enumerate(entries):
            duration = (
                entry.get("en_duration")
                or entry.get("fr_duration")
                or entry.get("sw_duration")
                or entry.get("pt_duration")
                or ""
            )
            values = [
                entry.get("display_date") or entry.get("date") or "",
                self._history_mark(entry.get("english")),
                self._history_mark(entry.get("french")),
                self._history_mark(entry.get("swahili")),
                self._history_mark(entry.get("portuguese")),
                entry.get("status") or "",
                str(duration),
                entry.get("folder") or "",
            ]
            for column, value in enumerate(values):
                self.hist_table.setItem(row, column, QTableWidgetItem(str(value)))
        self._history_entries = entries

    def _selected_history(self) -> dict | None:
        row = self.hist_table.currentRow()
        if row < 0 or row >= len(self._history_entries):
            return None
        return self._history_entries[row]

    def _open_history_row(self) -> None:
        entry = self._selected_history()
        folder = (entry or {}).get("folder")
        if folder and Path(folder).exists():
            os.startfile(folder)  # noqa: S606

    def _play_history(self, language_id: str) -> None:
        entry = self._selected_history()
        if not entry:
            return
        path = entry.get(f"{language_id}_mp3") or ""
        if path and Path(path).exists():
            self.player.play_file(path)

    def _open_history_report(self) -> None:
        entry = self._selected_history()
        path = (entry or {}).get("report") or ""
        if path and Path(path).exists():
            os.startfile(path)  # noqa: S606

    def _duplicate_template(self) -> None:
        selected_names = [
            (get_language_config(language_id).display_name)
            for language_id in self._selected_ids()
            if get_language_config(language_id)
        ]
        answer = QMessageBox.question(
            self,
            "Copy previous text?",
            f"Copy the previous day's {', '.join(selected_names)} text into today?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        entries = load_history()
        if entries:
            folder = Path(entries[0].get("folder") or "")
            for language_id, source_name in (
                ("en", "english_source.txt"),
                ("fr", "french_source.txt"),
                ("sw", "swahili_source.txt"),
                ("pt", "portuguese_source.txt"),
            ):
                if language_id not in self._selected_ids():
                    continue
                source = folder / "SOURCE" / source_name
                if source.exists():
                    self.lang_panels[language_id].set_text(
                        source.read_text(encoding="utf-8")
                    )
        QMessageBox.information(self, "Template", "Ready. Date stays as selected.")
