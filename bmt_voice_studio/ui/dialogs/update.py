"""Help → Check for Updates — apply a newer portable zip without a fresh setup."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from bmt_voice_studio import __version__
from bmt_voice_studio.config.settings import get_settings, save_settings
from bmt_voice_studio.update import (
    apply_zip_update,
    default_feed_url,
    download_update_zip,
    fetch_feed,
    is_newer,
    sibling_update_zips,
)


def _fmt_mb(num: int) -> str:
    return f"{max(0, num) / (1024 * 1024):.1f} MB"


class _FeedWorker(QObject):
    finished = Signal(dict)
    failed = Signal(str)

    def __init__(self, url: str) -> None:
        super().__init__()
        self._url = url

    def run(self) -> None:
        try:
            self.finished.emit(fetch_feed(self._url))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class _DownloadWorker(QObject):
    finished = Signal(str)
    failed = Signal(str)
    progress = Signal(int, int)
    status = Signal(str)

    def __init__(self, zip_url: str, dest: Path, asset_api_url: str) -> None:
        super().__init__()
        self._zip_url = zip_url
        self._dest = dest
        self._asset_api_url = asset_api_url
        self._cancel = False

    def request_cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        try:
            self.status.emit("Connecting to GitHub…")

            def on_progress(received: int, total: int) -> None:
                self.progress.emit(int(received), int(total))

            path = download_update_zip(
                self._zip_url,
                self._dest,
                asset_api_url=self._asset_api_url,
                on_progress=on_progress,
                cancel_check=lambda: self._cancel,
            )
            if self._cancel:
                self.failed.emit("Download cancelled.")
                return
            self.finished.emit(str(path))
        except InterruptedError:
            self.failed.emit("Download cancelled.")
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class UpdateDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Check for Updates")
        self.setMinimumWidth(540)
        self._zip: Path | None = None
        self._zip_url = ""
        self._asset_api_url = ""
        self._feed_version = ""
        self._thread: QThread | None = None
        self._worker: _FeedWorker | _DownloadWorker | None = None
        self._busy = False
        self._phase = ""

        layout = QVBoxLayout(self)
        intro = QLabel(
            "Updates come from the public GitHub Releases feed. "
            "Progress is shown below while checking or downloading."
        )
        intro.setWordWrap(True)
        intro.setObjectName("appSubtitle")
        layout.addWidget(intro)
        layout.addWidget(QLabel(f"This install: {__version__}"))

        form = QFormLayout()
        self.ed_feed = QLineEdit()
        self.ed_feed.setPlaceholderText(
            "https://api.github.com/repos/OWNER/BMTVoiceStudio/releases/latest"
        )
        settings = get_settings()
        feed = str(getattr(settings, "update_feed_url", "") or "").strip() or default_feed_url()
        self.ed_feed.setText(feed)
        form.addRow("GitHub releases URL", self.ed_feed)
        layout.addLayout(form)

        self.lbl_status = QLabel("Looking for a newer portable zip…")
        self.lbl_status.setWordWrap(True)
        layout.addWidget(self.lbl_status)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(True)
        self.progress.setFormat("Waiting…")
        self.progress.setMinimumHeight(22)
        self.progress.hide()
        layout.addWidget(self.progress)

        self.lbl_detail = QLabel("")
        self.lbl_detail.setObjectName("metaLabel")
        self.lbl_detail.setWordWrap(True)
        layout.addWidget(self.lbl_detail)

        row = QHBoxLayout()
        self.btn_browse = QPushButton("Choose update zip…")
        self.btn_feed = QPushButton("Check feed")
        self.btn_download = QPushButton("Download update")
        self.btn_browser = QPushButton("Open zip in browser")
        self.btn_stop = QPushButton("Stop")
        self.btn_browse.setObjectName("secondaryButton")
        self.btn_feed.setObjectName("secondaryButton")
        self.btn_download.setObjectName("secondaryButton")
        self.btn_browser.setObjectName("tertiaryButton")
        self.btn_stop.setObjectName("tertiaryButton")
        self.btn_browser.setEnabled(False)
        self.btn_download.setEnabled(False)
        self.btn_stop.setEnabled(False)
        self.btn_browse.setToolTip(
            "Always available. Pick a zip you already downloaded if the in-app download stalls."
        )
        self.btn_browser.setToolTip(
            "Open the GitHub zip in your browser, then Choose update zip."
        )
        self.btn_stop.setToolTip("Cancel the current check or download and unlock this dialog.")
        row.addWidget(self.btn_browse)
        row.addWidget(self.btn_feed)
        row.addWidget(self.btn_download)
        row.addWidget(self.btn_stop)
        layout.addLayout(row)
        layout.addWidget(self.btn_browser)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Install update and restart")
        layout.addWidget(buttons)
        self._ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self._ok.setEnabled(False)
        buttons.accepted.connect(self._apply)
        buttons.rejected.connect(self._cancel_or_close)
        self.btn_browse.clicked.connect(self._browse)
        self.btn_feed.clicked.connect(self._check_feed)
        self.btn_download.clicked.connect(self._start_download)
        self.btn_browser.clicked.connect(self._open_zip_in_browser)
        self.btn_stop.clicked.connect(self._stop_task)

        self._stall_timer = QTimer(self)
        self._stall_timer.setSingleShot(True)
        self._stall_timer.timeout.connect(self._on_stall_watchdog)

        self._scan_local()
        if not self._ok.isEnabled() and self.ed_feed.text().strip():
            self._check_feed()

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._busy:
            self._stop_task()
        self._cleanup_thread()
        super().closeEvent(event)

    def _cancel_or_close(self) -> None:
        if self._busy:
            self._stop_task()
            return
        self.reject()

    def _set_busy(self, busy: bool, *, phase: str = "") -> None:
        self._busy = busy
        self._phase = phase if busy else ""
        self.btn_feed.setEnabled(not busy)
        can_download = bool(self._zip_url) and is_newer(self._feed_version)
        self.btn_download.setEnabled((not busy) and can_download)
        # Escape hatches stay usable even while a task runs.
        self.btn_browse.setEnabled(True)
        self.btn_browser.setEnabled(bool(self._zip_url) or bool(self._feed_version))
        self.btn_stop.setEnabled(busy)
        if busy:
            self.progress.show()
            if phase == "download":
                self.progress.setRange(0, 100)
                self.progress.setValue(0)
                self.progress.setFormat("Downloading… %p%")
            else:
                self.progress.setRange(0, 0)
                self.progress.setFormat("Working…")
            self._stall_timer.start(180_000)
        else:
            self._stall_timer.stop()
            if self.progress.maximum() == 0:
                self.progress.hide()
                self.progress.setFormat("Waiting…")

    def _on_stall_watchdog(self) -> None:
        if not self._busy:
            return
        self.lbl_status.setText(
            "This is taking longer than expected. "
            "Click Stop, then Open zip in browser + Choose update zip."
        )
        self.lbl_detail.setText("In-app download may be blocked on this network.")
        self.btn_stop.setEnabled(True)
        self.btn_browse.setEnabled(True)
        self.btn_browser.setEnabled(True)

    def _stop_task(self) -> None:
        if isinstance(self._worker, _DownloadWorker):
            self._worker.request_cancel()
        self._cleanup_thread(force=True)
        self._set_busy(False)
        self.progress.hide()
        self.progress.setRange(0, 0)
        self.lbl_status.setText(
            "Update task stopped. Use Open zip in browser, then Choose update zip, "
            "or click Check feed / Download update again."
        )
        self.lbl_detail.setText("")
        self.btn_download.setEnabled(bool(self._zip_url) and is_newer(self._feed_version))
        self.btn_browser.setEnabled(bool(self._zip_url))

    def _cleanup_thread(self, *, force: bool = False) -> None:
        if self._thread is None:
            return
        thread = self._thread
        self._thread = None
        self._worker = None
        if force:
            thread.requestInterruption()
        thread.quit()
        if not thread.wait(1500) and force:
            thread.terminate()
            thread.wait(500)

    def _scan_local(self) -> None:
        zips = sibling_update_zips()
        for path in zips:
            from bmt_voice_studio.update import _version_from_name

            ver = _version_from_name(path.name)
            if is_newer(ver):
                self._zip = path
                self.lbl_status.setText(f"Found newer package:\n{path.name}")
                self._ok.setEnabled(True)
                return
        self.lbl_status.setText(
            "No newer zip next to the app. Checking the GitHub Releases feed…"
        )

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose update zip",
            str(Path.home() / "Downloads"),
            "Portable zip (*.zip)",
        )
        if not path:
            return
        if self._busy:
            self._stop_task()
        self._zip = Path(path)
        self.lbl_status.setText(f"Ready to apply:\n{self._zip.name}")
        self.lbl_detail.setText("Install update and restart will replace this copy.")
        self.progress.hide()
        self._ok.setEnabled(True)

    def _check_feed(self) -> None:
        if self._busy:
            return
        url = self.ed_feed.text().strip()
        settings = get_settings()
        settings.update_feed_url = url
        save_settings(settings)
        if not url:
            QMessageBox.information(
                self,
                "Updates",
                "GitHub is not connected yet. Run tools\\connect_github.ps1 once on this PC, "
                "then rebuild so every user checks the same Releases feed.",
            )
            return

        self._cleanup_thread()
        self._set_busy(True, phase="feed")
        self.lbl_status.setText("Checking GitHub Releases…")
        self.lbl_detail.setText("Reading release metadata (not downloading the zip yet).")
        thread = QThread(self)
        worker = _FeedWorker(url)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_feed_ok)
        worker.failed.connect(self._on_feed_fail)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        self._thread = thread
        self._worker = worker
        thread.start()

    def _on_feed_ok(self, feed: dict) -> None:
        self._set_busy(False)
        self.progress.hide()
        version = str(feed.get("version") or "")
        zip_url = str(feed.get("zip_url") or feed.get("url") or "")
        asset_api = str(feed.get("asset_api_url") or "")
        self._feed_version = version
        self._zip_url = zip_url
        self._asset_api_url = asset_api
        self.btn_browser.setEnabled(bool(zip_url))
        if not is_newer(version):
            self.lbl_status.setText(
                f"Feed version {version or '?'} is not newer than {__version__}."
            )
            self.lbl_detail.setText("You are up to date.")
            self.btn_download.setEnabled(False)
            return
        if not zip_url:
            self.lbl_status.setText(
                f"Feed has {version} but no zip_url. Place "
                f"BMTVoiceStudio-{version}-Windows-x64-Portable.zip next to the app, or choose it here."
            )
            self.btn_download.setEnabled(False)
            return
        self.lbl_status.setText(f"GitHub has {version}. Starting download…")
        self.lbl_detail.setText("Progress bar updates while the portable zip downloads.")
        self.btn_download.setEnabled(True)
        # Auto-start download so users are not stuck after “check” with no progress.
        QTimer.singleShot(0, self._start_download)

    def _on_feed_fail(self, message: str) -> None:
        self._set_busy(False)
        self.progress.hide()
        self.lbl_status.setText(f"Could not read the GitHub feed.\n{message}")
        self.lbl_detail.setText("Use Open zip in browser if you already know the release URL.")
        QMessageBox.warning(self, "Updates", f"Could not read the feed.\n{message}")

    def _start_download(self) -> None:
        if self._busy or not self._zip_url or not self._feed_version:
            return
        dest = Path.home() / "Downloads" / f"BMTVoiceStudio-{self._feed_version}-Windows-x64-Portable.zip"
        self._cleanup_thread()
        self._set_busy(True, phase="download")
        self.lbl_status.setText(f"Downloading {self._feed_version}…")
        self.lbl_detail.setText("0 MB received")
        thread = QThread(self)
        worker = _DownloadWorker(self._zip_url, dest, self._asset_api_url)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._on_download_progress)
        worker.status.connect(self.lbl_detail.setText)
        worker.finished.connect(self._on_download_ok)
        worker.failed.connect(self._on_download_fail)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        self._thread = thread
        self._worker = worker
        thread.start()

    def _on_download_progress(self, received: int, total: int) -> None:
        if total > 0:
            pct = max(0, min(100, int(round(100.0 * received / total))))
            self.progress.setRange(0, 100)
            self.progress.setValue(pct)
            self.progress.setFormat(f"Downloading… {pct}%")
            self.lbl_detail.setText(f"{_fmt_mb(received)} / {_fmt_mb(total)}")
        else:
            self.progress.setRange(0, 0)
            self.progress.setFormat("Downloading…")
            self.lbl_detail.setText(f"{_fmt_mb(received)} received")
        # Activity resets the stall watchdog.
        if self._stall_timer.isActive():
            self._stall_timer.start(180_000)

    def _on_download_ok(self, path: str) -> None:
        self._set_busy(False)
        self._zip = Path(path)
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.progress.setFormat("Download complete")
        self.progress.show()
        self.lbl_status.setText(
            f"Downloaded {self._zip.name}. Click Install update and restart to replace this copy."
        )
        self.lbl_detail.setText(_fmt_mb(self._zip.stat().st_size) if self._zip.is_file() else "")
        self._ok.setEnabled(True)

    def _on_download_fail(self, message: str) -> None:
        self._set_busy(False)
        self.progress.hide()
        self.btn_download.setEnabled(bool(self._zip_url) and is_newer(self._feed_version))
        self.btn_browser.setEnabled(bool(self._zip_url))
        self.lbl_status.setText(
            f"Could not finish downloading {self._feed_version or 'the update'}.\n"
            "Use Open zip in browser, then Choose update zip.\n"
            f"{message}"
        )
        self.lbl_detail.setText("")

    def _open_zip_in_browser(self) -> None:
        if self._zip_url:
            QDesktopServices.openUrl(QUrl(self._zip_url))
            return
        # Fallback: open the releases page for this repo.
        feed = self.ed_feed.text().strip()
        if "/repos/" in feed and "/releases" in feed:
            # https://api.github.com/repos/owner/name/releases/latest -> html releases
            try:
                parts = feed.split("/repos/")[1].split("/releases")[0]
                QDesktopServices.openUrl(QUrl(f"https://github.com/{parts}/releases/latest"))
            except Exception:
                pass

    def _apply(self) -> None:
        if self._busy:
            QMessageBox.information(
                self,
                "Updates",
                "Wait for the download to finish, or click Stop and Choose update zip.",
            )
            return
        if self._zip is None or not self._zip.is_file():
            return
        try:
            script = apply_zip_update(self._zip)
        except Exception as exc:
            QMessageBox.warning(self, "Updates", f"Could not prepare the update.\n{exc}")
            return
        QMessageBox.information(
            self,
            "Updates",
            "BMT Voice Studio will close and replace this install with the newer portable build.",
        )
        import os
        import sys

        os.startfile(str(script))  # noqa: S606
        sys.exit(0)
