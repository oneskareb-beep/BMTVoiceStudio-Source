"""UI polish / design-system tests for 1.3.1-dev (no business-logic assertions)."""

from __future__ import annotations

from pathlib import Path

import pytest

from bmt_voice_studio import __version__
from bmt_voice_studio.build_info import BUILD_LABEL
from bmt_voice_studio.release_scan import sha256_file
from bmt_voice_studio.ui.theme import (
    COLOR,
    DARK_QSS,
    HEIGHT,
    RADIUS,
    SPACE,
    STABLE_130_SHA256,
    STABLE_130_ZIP_NAME,
    TYPE,
    apply_theme,
    set_badge_state,
)


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    apply_theme(app, "dark")
    return app


def test_final_identity():
    assert __version__ == "1.3.37"
    assert BUILD_LABEL == "Final"
    root = Path(__file__).resolve().parents[1]
    assert (root / "VERSION").read_text(encoding="utf-8").strip() == "1.3.37"


def test_stable_130_final_protected():
    root = Path(__file__).resolve().parents[1]
    zip130 = root / "release" / STABLE_130_ZIP_NAME
    if not zip130.is_file():
        pytest.skip("historical 1.3.0 release zip not present on this machine")
    assert sha256_file(zip130) == STABLE_130_SHA256


def test_design_tokens_present():
    assert SPACE.md == 12
    assert SPACE.section >= SPACE.md
    assert RADIUS.card == 12
    assert TYPE.page_title >= 24
    assert HEIGHT.primary >= HEIGHT.standard
    assert COLOR.gold.startswith("#")
    assert COLOR.blue_primary.startswith("#")
    assert COLOR.app_bg.startswith("#")


def test_dark_theme_stylesheet_coverage():
    assert "QPushButton#primaryButton" in DARK_QSS
    assert "QPushButton#secondaryButton" in DARK_QSS
    assert "QPushButton#tertiaryButton" in DARK_QSS
    assert "QToolButton#iconButton" in DARK_QSS
    assert "QToolButton#templateChip" in DARK_QSS
    assert "QToolButton#disclosureButton" in DARK_QSS
    assert "QLabel#captionPreviewStage" in DARK_QSS
    assert "QPushButton#dangerButton" in DARK_QSS
    assert "QPushButton#modeButton" in DARK_QSS
    assert "QComboBox QAbstractItemView" in DARK_QSS
    assert "QMenu {" in DARK_QSS
    assert "QScrollBar:vertical" in DARK_QSS
    assert "QLabel#statusBadge" in DARK_QSS
    assert "QHeaderView::section" in DARK_QSS


def test_apply_theme_loads(qapp):
    apply_theme(qapp, "dark")
    sheet = qapp.styleSheet()
    assert "primaryButton" in sheet
    assert COLOR.app_bg in sheet


def test_button_helpers_object_names(qapp):
    from bmt_voice_studio.ui.widgets.common import (
        danger_button,
        primary_button,
        secondary_button,
        tertiary_button,
    )

    assert primary_button("Go").objectName() == "primaryButton"
    assert secondary_button("Open").objectName() == "secondaryButton"
    assert tertiary_button("Reset").objectName() == "tertiaryButton"
    assert danger_button("Remove").objectName() == "dangerButton"


def test_status_badge_states(qapp):
    from bmt_voice_studio.ui.widgets.common import status_badge

    badge = status_badge("Ready", "ready")
    assert badge.objectName() == "statusBadge"
    assert badge.property("state") == "ready"
    set_badge_state(badge, "failed")
    assert badge.property("state") == "failed"


def test_main_window_header_layout(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("BMT_SKIP_LIBRARY_DIALOG", "1")
    monkeypatch.setenv("BMT_DOCUMENTS_DIR", str(tmp_path / "docs"))
    monkeypatch.setenv("BMT_PHYSICAL_DOCUMENTS_DIR", str(tmp_path / "phys"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "la"))
    from PySide6.QtWidgets import QWidget

    from bmt_voice_studio.ui.main_window import MainWindow

    win = MainWindow()
    assert __version__ in win.windowTitle()
    assert win.minimumWidth() >= 1100
    assert win.btn_mode_daily.objectName() == "modeButton"
    assert win.btn_mode_video.objectName() == "modeButton"
    switches = [w for w in win.findChildren(QWidget) if w.objectName() == "workspaceSwitch"]
    assert switches
    assert win.job_progress.objectName() == "jobProgressStrip"
    assert win.job_progress.bar.maximum() == 100
    win.close()


def test_video_maker_layout_constraints(qapp, tmp_path, monkeypatch):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QScrollArea, QWidget

    monkeypatch.setenv("BMT_SKIP_LIBRARY_DIALOG", "1")
    monkeypatch.setenv("BMT_DOCUMENTS_DIR", str(tmp_path / "docs"))
    monkeypatch.setenv("BMT_PHYSICAL_DOCUMENTS_DIR", str(tmp_path / "phys"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "la"))
    from bmt_voice_studio.ui.pages.video_maker import VideoMakerPage

    page = VideoMakerPage()
    assert "GENERATE" in page.btn_generate.text().upper()
    assert page.btn_generate.objectName() == "primaryButton"
    assert page.btn_cancel.objectName() == "dangerButton"
    assert page.lbl_today_topic.objectName() == "topicValue"
    assert page.btn_open.text() == "Open folder"
    assert page.btn_open_video.text() == "Open video"
    assert page.btn_select_ready.text() == "Select all ready"
    assert hasattr(page, "logo_picker")
    assert hasattr(page, "music_picker")
    assert hasattr(page, "timeline")
    assert "Choose Logo" in page.logo_picker.btn_choose.text()
    assert "Choose Music" in page.music_picker.btn_choose.text()
    assert hasattr(page, "btn_hist_toggle")
    assert not page._hist_body.isVisible()
    headers = [w for w in page.findChildren(QWidget) if w.objectName() == "pageHeader"]
    assert headers
    for sc in page.findChildren(QScrollArea):
        assert sc.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    assert page._display_duration("285.2s") == "04:45"
    assert page._display_status("complete") == "Complete"
    page.close()


def test_ellipsize_path_helper():
    from bmt_voice_studio.ui.widgets.common import ellipsize_path

    short = r"C:\short\path"
    assert ellipsize_path(short) == short
    long = r"C:\Users\someone\Documents\BMT Voice Studio\Exports\Video\very\long\folder\file.mp4"
    out = ellipsize_path(long, keep=40)
    assert out.startswith("\u2026")
    assert len(out) <= 40
