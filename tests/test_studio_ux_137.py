"""1.3.7 studio chrome: stages, hidden idle progress, preview-first video, one Generate."""

from __future__ import annotations

from pathlib import Path

import pytest

from bmt_voice_studio import __version__
from bmt_voice_studio.config.settings import AppSettings, remember_recent_path
from bmt_voice_studio.ui.theme import apply_theme


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    apply_theme(app, "dark")
    return app


def _window(monkeypatch, tmp_path):
    monkeypatch.setenv("BMT_SKIP_LIBRARY_DIALOG", "1")
    monkeypatch.setenv("BMT_DOCUMENTS_DIR", str(tmp_path / "docs"))
    monkeypatch.setenv("BMT_PHYSICAL_DOCUMENTS_DIR", str(tmp_path / "phys"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "la"))
    from bmt_voice_studio.ui.main_window import MainWindow

    return MainWindow()


def test_identity_137():
    root = Path(__file__).resolve().parents[1]
    assert __version__ == "1.3.35"
    assert (root / "VERSION").read_text(encoding="utf-8").strip() == "1.3.35"
    assert (root / "BMTVoiceStudio-1.3.6.spec").is_file()
    assert (root / "BMTVoiceStudio-1.3.7.spec").is_file()
    assert (root / "BMTVoiceStudio-1.3.8.spec").is_file()
    assert (root / "BMTVoiceStudio-1.3.9.spec").is_file()
    assert (root / "BMTVoiceStudio-1.3.10.spec").is_file()
    assert (root / "BMTVoiceStudio-1.3.11.spec").is_file()
    assert (root / "BMTVoiceStudio-1.3.12.spec").is_file()
    assert (root / "BMTVoiceStudio-1.3.13.spec").is_file()
    assert (root / "BMTVoiceStudio-1.3.14.spec").is_file()
    assert (root / "BMTVoiceStudio-1.3.15.spec").is_file()
    assert (root / "BMTVoiceStudio-1.3.16.spec").is_file()
    assert (root / "BMTVoiceStudio-1.3.17.spec").is_file()
    assert (root / "BMTVoiceStudio-1.3.33.spec").is_file()
    assert (root / "BMTVoiceStudio-1.3.35.spec").is_file()


def test_header_audio_video_and_hidden_idle_progress(qapp, tmp_path, monkeypatch):
    win = _window(monkeypatch, tmp_path)
    qapp.processEvents()
    assert win.btn_mode_daily.text() == "Audio"
    assert win.btn_mode_video.text() == "Video"
    assert win.lbl_header_date.text()
    assert win.job_progress.isHidden()
    win.job_progress.set_progress(40, "Rendering English")
    assert not win.job_progress.isHidden()
    assert win.job_progress.bar.value() == 40
    win.job_progress.set_idle()
    assert win.job_progress.isHidden()
    win.close()


def test_daily_one_generate_history_drawer_make_video(qapp, tmp_path, monkeypatch):
    win = _window(monkeypatch, tmp_path)
    page = win.page_daily
    qapp.processEvents()
    assert page.btn_generate_main is page.btn_generate
    assert "GENERATE TODAY'S DEVOTIONAL" in page.btn_generate.text().upper()
    assert hasattr(page, "btn_make_video")
    assert not page.btn_make_video.isEnabled()
    assert hasattr(page, "btn_hist_toggle")
    assert page._hist_body.isHidden()
    page._toggle_history()
    assert not page._hist_body.isHidden()
    win.close()


def test_video_preview_first_timeline_recents(qapp, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QScrollArea

    monkeypatch.setenv("BMT_SKIP_LIBRARY_DIALOG", "1")
    monkeypatch.setenv("BMT_DOCUMENTS_DIR", str(tmp_path / "docs"))
    monkeypatch.setenv("BMT_PHYSICAL_DOCUMENTS_DIR", str(tmp_path / "phys"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "la"))
    from bmt_voice_studio.ui.pages.video_maker import VideoMakerPage

    page = VideoMakerPage()
    qapp.processEvents()
    page._ensure_default_media()
    assert len(page.media.items()) == 5
    assert page.media._locked_defaults is True
    assert page.timeline.objectName() == "studioTimeline"
    assert page.timeline.height() >= 50
    assert page.preview.width() * 16 == page.preview.height() * 9
    assert hasattr(page, "cmb_recent_logos")
    assert hasattr(page, "cmb_recent_music")
    max_widths = [sc.maximumWidth() for sc in page.findChildren(QScrollArea)]
    assert any(w >= 10000 or w == 16777215 for w in max_widths), max_widths
    icons = (
        page.preview_player.btn_play,
        page.preview_player.btn_pause,
        page.preview_player.btn_restart,
        page.preview_player.btn_crop,
        page.preview_player.btn_system,
        page.btn_fill,
        page.btn_fit,
        page.btn_smart,
        page.btn_up,
        page.btn_down,
        page.btn_nudge_left,
        page.btn_nudge_right,
        page.btn_reset_crop,
        page.media.btn_left,
        page.media.btn_right,
        page.btn_external,
    )
    for btn in icons:
        assert btn.objectName() == "iconButton"
        assert btn.text() == ""
        assert btn.toolTip()
        assert btn.icon().isNull() is False
    assert page.media.btn_add.isVisible() is False
    assert page.media.btn_remove.isVisible() is False
    assert page.media.btn_replace.isVisible() is False
    assert page.media.list.iconSize().height() >= 140
    assert page.media.list.maximumHeight() >= 300
    assert page.media._placeholder.wordWrap()
    for widgets in page._audio_rows.values():
        use = widgets["use"]
        assert use.objectName() == "iconButton"
        assert use.text() == ""
        assert use.icon().isNull() is False
        assert widgets["frame"].objectName() == "audioRow"
    for chip in (page.btn_classic, page.btn_nature, page.btn_minimal):
        assert chip.objectName() == "templateChip"
        assert chip.icon().isNull() is False
        assert chip.height() <= 120
    assert page.sld_zoom.minimum() == 15
    assert page.sld_zoom.maximum() == 250
    assert hasattr(page, "caption_style")
    assert page.caption_style.sp_size.value() >= 28
    page.close()


def test_video_inspector_controls_not_clipped(qapp, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QScrollArea, QVBoxLayout

    win = _window(monkeypatch, tmp_path)
    win.show_workspace("video")
    win.resize(1366, 768)
    qapp.processEvents()
    page = win.page_video
    page._ensure_default_media()
    assert isinstance(page.logo_picker.layout(), QVBoxLayout)
    assert isinstance(page.music_picker.layout(), QVBoxLayout)
    max_widths = [sc.maximumWidth() for sc in page.findChildren(QScrollArea)]
    assert all(w >= 1000 or w == 16777215 for w in max_widths), max_widths
    assert page.media._placeholder.wordWrap()
    assert page.media.btn_add.isVisible() is False
    assert len(page.media.items()) == 5
    win.close()


def test_remember_recent_path_front(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "bmt_voice_studio.config.settings.settings_file",
        lambda: tmp_path / "settings.json",
    )
    from bmt_voice_studio.config import settings as settings_mod

    previous = settings_mod._settings
    settings_mod._settings = AppSettings()
    try:
        first = str(tmp_path / "a.png")
        second = str(tmp_path / "b.png")
        remember_recent_path("video_recent_logos", first)
        remember_recent_path("video_recent_logos", second)
        remember_recent_path("video_recent_logos", first)
        items = settings_mod.get_settings().video_recent_logos
        assert items[0] == first
        assert items[1] == second
    finally:
        settings_mod._settings = previous
