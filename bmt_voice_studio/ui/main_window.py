"""Main application window — Daily BMT production only."""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from bmt_voice_studio.daily.naming import display_date
from bmt_voice_studio.ui.studio_keys import bind_shortcut

from bmt_voice_studio import __app_name__, __version__
from bmt_voice_studio.config.paths import first_run_marker
from bmt_voice_studio.config.settings import get_settings, save_settings
from bmt_voice_studio.daily.layout import daily_exports_root
from bmt_voice_studio.resources import apply_logo_label, load_app_icon, logo_label
from bmt_voice_studio.ui.dialogs.about import AboutDialog
from bmt_voice_studio.ui.dialogs.daily_welcome import DailyWelcomeDialog
from bmt_voice_studio.ui.dialogs.first_run import FirstRunDialog
from bmt_voice_studio.ui.dialogs.preferences import PreferencesDialog
from bmt_voice_studio.ui.dialogs.troubleshooting import TroubleshootingDialog
from bmt_voice_studio.ui.pages.daily_bmt import DailyBMTPage
from bmt_voice_studio.ui.pages.video_maker import VideoMakerPage
from bmt_voice_studio.ui.widgets.common import Toast
from bmt_voice_studio.ui.widgets.job_progress import JobProgressStrip


class MainWindow(QMainWindow):
    """Two primary workspaces: Daily Audio and Video Maker. No technical sidebar."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{__app_name__} — {__version__}")
        self.resize(1360, 900)
        self.setMinimumSize(1180, 720)
        icon = load_app_icon()
        if not icon.isNull():
            self.setWindowIcon(icon)

        central = QWidget()
        central.setObjectName("centralRoot")
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QWidget()
        header.setObjectName("appHeader")
        header.setFixedHeight(88)
        self.app_header = header
        h = QHBoxLayout(header)
        h.setContentsMargins(20, 8, 20, 8)
        h.setSpacing(12)
        self.header_logo = logo_label(max_width=96, max_height=50, parent=header)
        h.addWidget(self.header_logo)
        titles = QVBoxLayout()
        titles.setSpacing(1)
        titles.setContentsMargins(0, 2, 0, 2)
        self.lbl_app_title = QLabel("BMT Voice Studio")
        self.lbl_app_title.setObjectName("appTitle")
        self.lbl_app_tagline = QLabel("Believers Manna Today")
        self.lbl_app_tagline.setObjectName("appTagline")
        self.lbl_header_date = QLabel("")
        self.lbl_header_date.setObjectName("headerDate")
        titles.addWidget(self.lbl_app_title)
        titles.addWidget(self.lbl_app_tagline)
        titles.addWidget(self.lbl_header_date)
        h.addLayout(titles, 1)
        product_wrap = QWidget()
        product_wrap.setObjectName("workspaceSwitch")
        product_row = QHBoxLayout(product_wrap)
        product_row.setContentsMargins(4, 4, 4, 4)
        product_row.setSpacing(4)
        self.btn_product_bmt = QPushButton("BMT")
        self.btn_product_hhr = QPushButton("HHR")
        self.btn_product_bmt.setToolTip("Believers Manna Today")
        self.btn_product_hhr.setToolTip("Hope & Healing Africa — Ruhuka Umutima")
        for btn in (self.btn_product_bmt, self.btn_product_hhr):
            btn.setObjectName("modeButton")
            btn.setCheckable(True)
            btn.setMinimumWidth(72)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            product_row.addWidget(btn)
        h.addWidget(product_wrap)
        mode_wrap = QWidget()
        mode_wrap.setObjectName("workspaceSwitch")
        mode_row = QHBoxLayout(mode_wrap)
        mode_row.setContentsMargins(4, 4, 4, 4)
        mode_row.setSpacing(4)
        self.btn_mode_daily = QPushButton("Audio")
        self.btn_mode_video = QPushButton("Video")
        for btn in (self.btn_mode_daily, self.btn_mode_video):
            btn.setObjectName("modeButton")
            btn.setCheckable(True)
            btn.setMinimumWidth(88)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            mode_row.addWidget(btn)
        self.btn_mode_daily.setChecked(True)
        h.addWidget(mode_wrap)
        layout.addWidget(header)

        self.job_progress = JobProgressStrip()
        layout.addWidget(self.job_progress)
        self._job_idle_timer = QTimer(self)
        self._job_idle_timer.setSingleShot(True)
        self._job_idle_timer.setInterval(2800)
        self._job_idle_timer.timeout.connect(self.job_progress.set_idle)

        self.workspace = QStackedWidget()
        self._resolve_data_library()
        self.page_daily = DailyBMTPage()
        self.page_video = VideoMakerPage()
        self.page_video.bind_daily_page(self.page_daily)
        self.workspace.addWidget(self.page_daily)
        self.workspace.addWidget(self.page_video)
        self.workspace.setCurrentWidget(self.page_daily)
        layout.addWidget(self.workspace, 1)
        self.page_daily.date.dateChanged.connect(self._sync_header_date)
        self.page_daily.make_video_requested.connect(self._open_video_from_daily)
        self._sync_header_date()
        bind_shortcut(self, "Ctrl+1", lambda: self.show_workspace("daily"))
        bind_shortcut(self, "Ctrl+2", lambda: self.show_workspace("video"))

        self.toast = Toast(central)
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage("Daily BMT ready")

        file_menu = self.menuBar().addMenu("&File")
        act_new = QAction("New Daily Production", self)
        act_new.triggered.connect(self.page_daily._new_day)
        act_open = QAction("Open Export Folder", self)
        act_open.triggered.connect(self._open_exports)
        act_prefs = QAction("Preferences…", self)
        act_prefs.triggered.connect(self._show_preferences)
        act_quit = QAction("Exit", self)
        act_quit.triggered.connect(self.close)
        file_menu.addAction(act_new)
        file_menu.addAction(act_open)
        file_menu.addSeparator()
        file_menu.addAction(act_prefs)
        file_menu.addSeparator()
        file_menu.addAction(act_quit)

        help_menu = self.menuBar().addMenu("&Help")
        act_trouble = QAction("Troubleshooting…", self)
        act_trouble.triggered.connect(self._show_troubleshooting)
        act_about = QAction("About BMT Voice Studio", self)
        act_about.triggered.connect(self._show_about)
        help_menu.addAction(act_trouble)
        help_menu.addSeparator()
        act_update = QAction("Check for Updates…", self)
        act_update.triggered.connect(self._show_update)
        help_menu.addAction(act_update)
        help_menu.addSeparator()
        help_menu.addAction(act_about)

        self.page_daily.status_message.connect(self.status.showMessage)
        self.page_video.status_message.connect(self.status.showMessage)
        self.page_daily.job_progress.connect(self._on_job_progress)
        self.page_video.job_progress.connect(self._on_job_progress)
        self.page_daily.job_busy.connect(self._on_job_busy)
        self.page_video.job_busy.connect(self._on_job_busy)
        self.btn_mode_daily.clicked.connect(lambda: self.show_workspace("daily"))
        self.btn_mode_video.clicked.connect(lambda: self.show_workspace("video"))
        self.btn_product_bmt.clicked.connect(lambda: self.set_product_mode("bmt"))
        self.btn_product_hhr.clicked.connect(lambda: self.set_product_mode("hhr"))

        s = get_settings()
        s.last_page = "daily"
        s.start_page = "daily"
        save_settings(s)
        self.set_product_mode(getattr(s, "product_mode", "bmt") or "bmt", persist=False)

    def set_product_mode(self, product: str, *, persist: bool = True) -> None:
        from bmt_voice_studio.config.product import get_product, normalize_product

        mode = normalize_product(product)
        profile = get_product(mode)
        self.btn_product_bmt.setChecked(mode == "bmt")
        self.btn_product_hhr.setChecked(mode == "hhr")
        self.lbl_app_title.setText(profile.title)
        self.lbl_app_tagline.setText(profile.tagline)
        apply_logo_label(self.header_logo, max_width=96, max_height=50, product=mode)
        self.setWindowTitle(f"{profile.title} — {__version__}")
        if mode == "hhr":
            self.app_header.setStyleSheet(
                "QWidget#appHeader { background-color: #0A2E22; border-bottom: 1px solid #1E5A44; }"
            )
            self.lbl_app_title.setStyleSheet("color: #F4F7F2;")
            self.lbl_app_tagline.setStyleSheet("color: #A8C4B4;")
            self.lbl_header_date.setStyleSheet("color: #D6E2D8;")
        else:
            self.app_header.setStyleSheet("")
            self.lbl_app_title.setStyleSheet("")
            self.lbl_app_tagline.setStyleSheet("")
            self.lbl_header_date.setStyleSheet("")
        if persist:
            s = get_settings()
            s.product_mode = mode
            save_settings(s)
        self.page_daily.apply_product_mode(mode)
        self.page_video.apply_product_mode(mode)
        video = self.workspace.currentWidget() is self.page_video
        self.status.showMessage(
            "Video Maker" if video else f"{profile.short_label} ready — {profile.tagline}"
        )

    def _product_ready_message(self) -> str:
        from bmt_voice_studio.config.product import get_product

        profile = get_product(getattr(get_settings(), "product_mode", "bmt"))
        return f"{profile.short_label} ready — {profile.tagline}"

    def _resolve_data_library(self) -> None:
        skip = (os.environ.get("BMT_SKIP_LIBRARY_DIALOG") or "").strip().lower() in {"1", "true", "yes"}
        from bmt_voice_studio.config.data_root import activate_decided_root, decide_startup_root

        decision = decide_startup_root(allow_prompt=not skip)
        if decision.needs_prompt and not skip:
            from bmt_voice_studio.ui.dialogs.data_library import DataLibraryDialog

            DataLibraryDialog(decision.candidates, self).exec()
            decision = decide_startup_root(allow_prompt=False)
        activate_decided_root(decision)

    def _on_job_progress(self, percent: int, message: str) -> None:
        self._job_idle_timer.stop()
        self.job_progress.set_progress(percent, message)

    def _on_job_busy(self, busy: bool) -> None:
        if busy:
            self._job_idle_timer.stop()
            return
        self._job_idle_timer.start()

    def show_workspace(self, name: str) -> None:
        video = name == "video"
        self.workspace.setCurrentWidget(self.page_video if video else self.page_daily)
        self.btn_mode_daily.setChecked(not video)
        self.btn_mode_video.setChecked(video)
        self.status.showMessage("Video Maker" if video else self._product_ready_message())
        self._sync_header_date()
        if video:
            self.page_video._refresh_date_label()
            self.page_video._refresh_todays_audio()
            self.page_video._refresh_header()
        s = get_settings()
        s.last_page = "video" if video else "daily"
        save_settings(s)

    def _sync_header_date(self, *_args) -> None:
        try:
            self.lbl_header_date.setText(display_date(self.page_daily.selected_date()))
        except Exception:
            pass

    def _open_video_from_daily(self) -> None:
        self.show_workspace("video")
        self.page_video._restore()

    def _open_exports(self) -> None:
        folder = daily_exports_root()
        if folder.exists():
            os.startfile(folder)  # noqa: S606

    def _show_preferences(self) -> None:
        dlg = PreferencesDialog(self)
        if dlg.exec():
            from PySide6.QtWidgets import QApplication

            from bmt_voice_studio.ui.theme import apply_theme

            app = QApplication.instance()
            if app:
                apply_theme(app, dlg.selected_theme)

    def _show_about(self) -> None:
        AboutDialog(self).exec()

    def _show_update(self) -> None:
        from bmt_voice_studio.ui.dialogs.update import UpdateDialog

        UpdateDialog(self).exec()

    def _show_troubleshooting(self) -> None:
        TroubleshootingDialog(self).exec()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not getattr(self, "_win32_icon_applied", False):
            from bmt_voice_studio.resources import apply_win32_hwnd_icon

            self._win32_icon_applied = apply_win32_hwnd_icon(self)
        if not getattr(self, "_first_run_checked", False):
            self._first_run_checked = True
            from PySide6.QtCore import QTimer

            QTimer.singleShot(200, self._maybe_first_run)
            QTimer.singleShot(800, self._maybe_qa_capture)

    def _maybe_qa_capture(self) -> None:
        """Packaged-EXE visual proof: set BMT_QA_CAPTURE=<dir> before launch."""
        import os
        from datetime import datetime, timezone
        from pathlib import Path

        dest_root = os.environ.get("BMT_QA_CAPTURE", "").strip()
        if not dest_root:
            return
        out = Path(dest_root)
        out.mkdir(parents=True, exist_ok=True)
        from bmt_voice_studio.build_info import BUILD_TIMESTAMP, runtime_diagnostics

        (out / "runtime_identity.txt").write_text(runtime_diagnostics(), encoding="utf-8")
        sizes = [(1920, 1080), (1600, 900), (1366, 768)]
        scenarios = [
            ("en_only", ["en"]),
            ("en_fr", ["en", "fr"]),
            ("en_fr_sw", ["en", "fr", "sw"]),
            ("all_four", ["en", "fr", "sw", "pt"]),
        ]
        from PySide6.QtCore import QSize
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        page = getattr(self, "page_daily", None)
        self.show_workspace("daily")
        for scenario_name, langs in scenarios:
            if page is not None and hasattr(page, "language_selector"):
                page.language_selector.set_selected_ids(langs)
                page._relayout_panels()
                page.en_edit.setPlainText("English sample. {Female line.}")
                if "fr" in langs:
                    page.fr_edit.setPlainText("Français exemple. {Ligne femme.}")
                if "sw" in langs:
                    page.sw_edit.setPlainText("Swahili sample. {Female line.}")
                if "pt" in langs:
                    page.pt_edit.setPlainText("Português exemplo. {Linha feminina.}")
                page._refresh_validation()
            for w, h in sizes:
                self.resize(QSize(w, h))
                self.repaint()
                if app:
                    app.processEvents()
                pix = self.grab()
                dest = out / f"packaged_{scenario_name}_{w}x{h}.png"
                pix.save(str(dest))
        self.show_workspace("video")
        if app:
            app.processEvents()
        for w, h in sizes:
            self.resize(QSize(w, h))
            self.repaint()
            if app:
                app.processEvents()
            pix = self.grab()
            (out / f"video_maker_{w}x{h}.png").write_bytes(b"")  # ensure path exists if save fails
            pix.save(str(out / f"video_maker_{w}x{h}.png"))
        (out / "capture_ok.txt").write_text(
            f"ok\n{BUILD_TIMESTAMP}\n{datetime.now(timezone.utc).isoformat()}\n",
            encoding="utf-8",
        )
        if os.environ.get("BMT_QA_CAPTURE_QUIT", "1") == "1":
            self.close()

    def _maybe_first_run(self) -> None:
        settings = get_settings()
        if not settings.first_run_complete and not first_run_marker().exists():
            FirstRunDialog(self).exec()
        from bmt_voice_studio.config.paths import daily_v11_welcome_marker

        if not settings.daily_v11_welcome_seen and not daily_v11_welcome_marker().exists():
            DailyWelcomeDialog(self).exec()
