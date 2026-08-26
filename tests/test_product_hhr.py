"""HHR / Ruhuka Umutima product mode — branding, Swahili-first, dual captions."""

from __future__ import annotations

from pathlib import Path

from bmt_voice_studio.config.product import (
    HHR_LOGO_FILE,
    PRODUCT_HHR,
    get_product,
    is_hhr,
    normalize_product,
)
from bmt_voice_studio.resources import logo_path
from bmt_voice_studio.video.brand_strings import brand_strings
from bmt_voice_studio.video.captions import CaptionCue, align_text_to_cues, write_ass
from bmt_voice_studio.video.locked_card import render_locked_intro_card
from bmt_voice_studio.video.models import TEMPLATE_HHR_GREEN, VideoProject
from bmt_voice_studio.daily.pipeline import DailyJob, preflight


def test_product_aliases_and_profile():
    assert normalize_product("HHA") == PRODUCT_HHR
    assert normalize_product("Ruhuka") == PRODUCT_HHR
    assert is_hhr("hhr")
    assert not is_hhr("bmt")
    profile = get_product("hhr")
    assert profile.spoken_language == "sw"
    assert profile.default_languages == ("sw",)
    assert profile.caption_primary == "rw"
    assert profile.template_id == TEMPLATE_HHR_GREEN
    assert profile.logo_file == HHR_LOGO_FILE


def test_hhr_logo_is_packaged():
    path = logo_path("hhr")
    assert path is not None and path.is_file()
    assert path.name == HHR_LOGO_FILE


def test_hhr_brand_strings_not_bmt():
    hhr = brand_strings("sw", "hhr")
    bmt = brand_strings("sw", "bmt")
    assert "HEALING" in hhr["title_line1"]
    assert hhr["daily_devotional"] == "RUHUKA UMUTIMA"
    assert hhr["written_by"].lower().startswith("chaplain")
    assert bmt["title_line1"] == "MANNA YA"
    assert bmt["series_title"] == "MANNA YA WAAMINIO"


def test_hhr_intro_card_renders(tmp_path: Path):
    project = VideoProject(
        product_mode="hhr",
        language="sw",
        topic="Hope That Refuses to Die",
        week_focus="HOPE IN THE MIDST OF CRISIS",
        devotional_date="2026-08-28",
        template_id=TEMPLATE_HHR_GREEN,
    )
    dest = tmp_path / "hhr_intro.png"
    render_locked_intro_card(project, dest, width=540, height=960)
    assert dest.is_file()
    assert dest.stat().st_size > 5_000


def test_hhr_preflight_requires_kinyarwanda():
    job = DailyJob(
        date=__import__("datetime").date(2026, 8, 28),
        swahili_text="Habari {ndugu}.",
        generate_english=False,
        generate_french=False,
        generate_swahili=True,
        generate_portuguese=False,
        product_mode="hhr",
        kinyarwanda_text="",
    )
    issues = preflight(job)
    assert any("KINYARWANDA" in i for i in issues)


def test_dual_captions_kinyarwanda_large_english_medium(tmp_path: Path):
    timing = [
        CaptionCue(start=0.0, end=2.5, text="Habari ndugu.", language="sw"),
        CaptionCue(start=2.5, end=5.0, text="Mungu yu mwema.", language="sw"),
    ]
    rw = align_text_to_cues("Muraho. Imana ni nziza.", timing, "rw")
    en = align_text_to_cues("Hello. God is good.", timing, "en")
    assert [c.language for c in rw] == ["rw", "rw"]
    dest = tmp_path / "hhr.ass"
    write_ass(rw + en, dest, width=1080, height=1920)
    blob = dest.read_text(encoding="utf-8")
    assert "Style: Kinyarwanda" in blob
    assert "Style: English" in blob
    rw_line = [ln for ln in blob.splitlines() if ln.startswith("Style: Kinyarwanda")][0]
    en_line = [ln for ln in blob.splitlines() if ln.startswith("Style: English")][0]
    rw_size = int(rw_line.split(",")[2])
    en_size = int(en_line.split(",")[2])
    assert rw_size > en_size
    assert "Dialogue:" in blob and "Kinyarwanda" in blob
    assert ",English,," in blob


def test_hhr_mode_switch_updates_branding(monkeypatch, tmp_path):
    from PySide6.QtWidgets import QApplication

    from bmt_voice_studio.ui.theme import apply_theme

    app = QApplication.instance() or QApplication([])
    apply_theme(app, "dark")
    monkeypatch.setenv("BMT_SKIP_LIBRARY_DIALOG", "1")
    monkeypatch.setenv("BMT_DOCUMENTS_DIR", str(tmp_path / "docs"))
    monkeypatch.setenv("BMT_PHYSICAL_DOCUMENTS_DIR", str(tmp_path / "phys"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "la"))
    from bmt_voice_studio.ui.main_window import MainWindow

    win = MainWindow()
    win.set_product_mode("bmt")
    assert win.lbl_app_title.text() == "BMT Voice Studio"
    assert win.page_daily.hhr_transcript_host.isHidden()
    assert win.page_video.btn_classic.isEnabled()
    win.set_product_mode("hhr")
    assert "Healing" in win.lbl_app_title.text()
    assert "RUHUKA" in win.lbl_app_tagline.text()
    assert not win.page_daily.hhr_transcript_host.isHidden()
    assert win.page_daily._selected_ids() == ["sw"]
    assert not win.page_video.btn_classic.isEnabled()
    assert win.page_video._template_id == TEMPLATE_HHR_GREEN
    win.set_product_mode("bmt")
    assert win.page_daily.hhr_transcript_host.isHidden()
    assert win.page_video.btn_classic.isEnabled()
    win.close()
