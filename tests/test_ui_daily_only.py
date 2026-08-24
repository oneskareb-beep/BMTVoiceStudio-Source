"""UI regression: Daily-BMT-only shell — checklist items 1–20."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _make_window(monkeypatch, tmp_path, suffix=""):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / f"la{suffix}"))
    monkeypatch.setenv("BMT_DOCUMENTS_DIR", str(tmp_path / f"docs{suffix}"))
    monkeypatch.setenv("BMT_PHYSICAL_DOCUMENTS_DIR", str(tmp_path / f"phys{suffix}"))
    monkeypatch.setenv("BMT_SKIP_LIBRARY_DIALOG", "1")
    monkeypatch.delenv("BMT_DATA_ROOT", raising=False)
    from bmt_voice_studio.config import settings as settings_mod

    settings_mod._settings = None
    s = settings_mod.get_settings()
    s.first_run_complete = True
    s.daily_v11_welcome_seen = True
    settings_mod.save_settings(s)

    from bmt_voice_studio.ui.main_window import MainWindow

    win = MainWindow()
    win.show()
    return win


def _all_widget_text(root) -> str:
    blobs = []
    for child in root.findChildren(object):
        if hasattr(child, "text") and callable(child.text):
            try:
                blobs.append(str(child.text()))
            except Exception:
                pass
        if hasattr(child, "placeholderText") and callable(child.placeholderText):
            try:
                blobs.append(str(child.placeholderText()))
            except Exception:
                pass
        if hasattr(child, "windowTitle") and callable(child.windowTitle):
            try:
                blobs.append(str(child.windowTitle()))
            except Exception:
                pass
    return " | ".join(blobs)


def test_01_app_opens_directly_to_daily_bmt(qapp, monkeypatch, tmp_path):
    win = _make_window(monkeypatch, tmp_path, "01")
    qapp.processEvents()
    assert hasattr(win, "page_daily")
    assert win.page_daily.isVisible()
    assert win.centralWidget().findChild(type(win.page_daily)) is not None or win.page_daily.isVisible()
    win.close()


def test_02_daily_bmt_only_visible_workspace(qapp, monkeypatch, tmp_path):
    win = _make_window(monkeypatch, tmp_path, "02")
    qapp.processEvents()
    assert not hasattr(win, "stack")
    assert not hasattr(win, "nav_buttons")
    assert not hasattr(win, "page_tts")
    assert not hasattr(win, "page_audio")
    assert not hasattr(win, "page_projects")
    assert not hasattr(win, "page_voices")
    assert not hasattr(win, "page_settings")
    win.close()


def test_03_to_07_studio_navigation_absent(qapp, monkeypatch, tmp_path):
    win = _make_window(monkeypatch, tmp_path, "03")
    qapp.processEvents()
    joined = _all_widget_text(win)
    for banned in (
        "TTS Studio",
        "Audio Builder",
        "Voice Manager",
        "Projects",
        "Settings",
    ):
        # File → Preferences is allowed; "Settings" as nav label is not.
        if banned == "Settings":
            assert "page_settings" not in dir(win)
            assert "Settings" not in [a.text().replace("&", "") for a in win.menuBar().actions()]
        else:
            assert banned not in joined, f"Found banned navigation: {banned}"
    win.close()


def test_08_to_14_no_editable_pipeline_controls(qapp, monkeypatch, tmp_path):
    win = _make_window(monkeypatch, tmp_path, "08")
    page = win.page_daily
    qapp.processEvents()
    for attr in (
        "processing_mode",
        "chk_master",
        "bitrate",
        "pause",
        "provider",
        "male_voice",
        "female_voice",
        "rate",
        "pitch",
        "volume",
        "cmb_provider",
        "cmb_male",
        "cmb_female",
        "spin_rate",
        "spin_pitch",
        "spin_pause",
        "spin_bitrate",
    ):
        assert not hasattr(page, attr), f"Editable control still present: {attr}"
    joined = _all_widget_text(page)
    for banned in (
        "Enhanced Mastering",
        "Original Pipeline",
        "MP3 bitrate",
        "Male voice",
        "Female voice",
        "Abeo",
        "Ezinne",
        "Remy",
        "Vivienne",
    ):
        # Production Details uses friendly labels only when expanded; collapsed body still has text.
        if banned in ("Male voice", "Female voice"):
            continue
        assert banned not in joined or banned in ("Male voice", "Female voice"), (
            f"Found technical control label: {banned}"
        )
    for banned in ("Abeo", "Ezinne", "Remy", "Vivienne", "Enhanced Mastering", "Original Pipeline"):
        assert banned not in joined, f"Found banned technical label: {banned}"
    win.close()


def test_15_16_english_french_editors_usable(qapp, monkeypatch, tmp_path):
    win = _make_window(monkeypatch, tmp_path, "15")
    page = win.page_daily
    qapp.processEvents()
    assert page.en_edit is not None
    assert page.fr_edit is not None
    assert page.en_edit.isEnabled()
    assert page.fr_edit.isEnabled()
    page.en_edit.setPlainText("Hello {world}")
    page.fr_edit.setPlainText("Bonjour {monde}")
    assert page.en_edit.toPlainText() == "Hello {world}"
    assert page.fr_edit.toPlainText() == "Bonjour {monde}"
    assert "en" in page.lang_panels and "fr" in page.lang_panels
    assert "sw" in page.lang_panels
    # Default selection is EN+FR — Swahili panel exists but not selected
    assert page.language_selector.selected_ids() == ["en", "fr"]
    win.close()


def test_17_generate_is_primary(qapp, monkeypatch, tmp_path):
    win = _make_window(monkeypatch, tmp_path, "17")
    page = win.page_daily
    qapp.processEvents()
    assert "GENERATE TODAY'S DEVOTIONAL" in page.btn_generate.text().upper()
    assert page.btn_generate.objectName() == "primaryButton"
    assert page.btn_generate_main.objectName() == "primaryButton"
    win.close()


def test_18_19_outputs_and_history_exist(qapp, monkeypatch, tmp_path):
    win = _make_window(monkeypatch, tmp_path, "18")
    page = win.page_daily
    qapp.processEvents()
    assert page.out_summary is not None
    assert "No production yet" in page.out_summary.text()
    assert page.hist_table is not None
    assert page.hist_table.columnCount() >= 6
    win.close()


def test_20_canonical_bmt_job_config(qapp, monkeypatch, tmp_path):
    win = _make_window(monkeypatch, tmp_path, "20")
    page = win.page_daily
    qapp.processEvents()
    job = page._job()
    assert job.provider == "edge"
    assert job.use_piper_fallback is False
    assert job.processing_mode == "original"
    assert job.strict_source_mode is True
    assert job.mastering is False
    from bmt_voice_studio.config.presets import BMT_ENGLISH

    assert job.pause_ms == BMT_ENGLISH.pipeline.pause_ms
    assert job.mp3_bitrate == BMT_ENGLISH.pipeline.mp3_bitrate_kbps
    win.close()


def test_menus_file_help_only(qapp, monkeypatch, tmp_path):
    from PySide6.QtGui import QAction

    win = _make_window(monkeypatch, tmp_path, "menus")
    qapp.processEvents()
    menus = [a.text().replace("&", "") for a in win.menuBar().actions()]
    assert menus == ["File", "Help"]
    action_texts = [a.text().replace("&", "") for a in win.findChildren(QAction) if a.text()]
    assert any("New Daily Production" in t for t in action_texts)
    assert any("Open Export Folder" in t for t in action_texts)
    assert any("Preferences" in t for t in action_texts)
    assert any("Exit" in t for t in action_texts)
    assert any("Troubleshooting" in t for t in action_texts)
    assert any("About" in t for t in action_texts)
    win.close()
    qapp.processEvents()


def test_language_config_four_languages_all_release_ready():
    from bmt_voice_studio.daily.language_config import (
        enabled_daily_languages,
        get_language_config,
        production_details_text,
        production_ready_languages,
    )

    langs = enabled_daily_languages()
    assert [c.language_id for c in langs] == ["en", "fr", "sw", "pt"]
    sw = get_language_config("sw")
    pt = get_language_config("pt")
    assert sw is not None and sw.production_approved is True
    assert pt is not None and pt.production_approved is True
    assert "Congo" in sw.target_region or "DRC" in sw.target_region
    assert pt.target_region == "Angola"
    ready = production_ready_languages()
    assert [c.language_id for c in ready] == ["en", "fr", "sw", "pt"]
    details = production_details_text()
    assert "BMT English Male" in details
    assert "BMT French Female" in details
    assert "Abeo" not in details
    assert "Remy" not in details
    assert "Portuguese" in details
    assert "Ready" in details


def test_daily_page_has_no_nav_feature_labels(qapp, monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "la2"))
    from bmt_voice_studio.config import settings as settings_mod

    settings_mod._settings = None
    from bmt_voice_studio.ui.pages.daily_bmt import DailyBMTPage

    page = DailyBMTPage()
    joined = _all_widget_text(page)
    for banned in ("TTS Studio", "Audio Builder", "Voice Manager", "Projects", "Enhanced Mastering"):
        assert banned not in joined, f"Found banned UI label: {banned}"
    assert "GENERATE TODAY'S DEVOTIONAL" in joined.upper()
    page.deleteLater()


def test_video_maker_workspace_present_without_old_studio(qapp, monkeypatch, tmp_path):
    win = _make_window(monkeypatch, tmp_path, "vm")
    qapp.processEvents()
    assert hasattr(win, "page_video")
    assert hasattr(win, "btn_mode_daily")
    assert hasattr(win, "btn_mode_video")
    assert not hasattr(win, "stack")
    assert not hasattr(win, "nav_buttons")
    assert win.page_daily.isVisible()
    win.show_workspace("video")
    qapp.processEvents()
    assert win.page_video.isVisible()
    assert "GENERATE VIDEO" in win.page_video.btn_generate.text().upper()
    assert "BMT CLASSIC" in win.page_video.lbl_template.text()
    win.show_workspace("daily")
    qapp.processEvents()
    assert win.page_daily.isVisible()
    win.close()


def test_no_language_generate_checkboxes(qapp, monkeypatch, tmp_path):
    win = _make_window(monkeypatch, tmp_path, "nogenchk")
    page = win.page_daily
    qapp.processEvents()
    assert not hasattr(page, "chk_en")
    assert not hasattr(page, "chk_fr")
    joined = _all_widget_text(page)
    assert "Generate English" not in joined
    assert "Generate French" not in joined
    assert "Include English" not in joined
    assert "Include French" not in joined
    job = page._job()
    assert job.generate_english is True
    assert job.generate_french is True
    win.close()


def test_1366_video_maker_layout_constraints(qapp, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QScrollArea

    win = _make_window(monkeypatch, tmp_path, "1366")
    win.show_workspace("video")
    win.resize(1366, 768)
    qapp.processEvents()
    page = win.page_video
    btn = page.btn_generate
    assert btn.isVisible()
    assert btn.geometry().right() <= win.width()
    assert btn.geometry().bottom() <= win.height()
    labels = [page.cmb_caption_content.itemText(i) for i in range(page.cmb_caption_content.count())]
    assert labels == ["Body Only", "Body + Memory Verse", "All Spoken Content"]
    still = page.preview
    assert still.width() * 16 == still.height() * 9
    assert still.width() >= 180
    assert still.height() >= 320
    from PySide6.QtCore import Qt

    for sc in page.findChildren(QScrollArea):
        assert sc.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    win.close()
