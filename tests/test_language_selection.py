"""Language selection combinations for Daily BMT (all 15 non-empty 4-language sets)."""

from __future__ import annotations

import os
from itertools import combinations

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from datetime import date

from bmt_voice_studio.daily.language_config import get_language_config
from bmt_voice_studio.daily.pipeline import DailyJob, preflight
from bmt_voice_studio.daily.validate import overall_status_selected


LANGS = ["en", "fr", "sw", "pt"]
COMBOS = [
    list(combo)
    for n in range(1, 5)
    for combo in combinations(LANGS, n)
]


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _page(monkeypatch, tmp_path, suffix=""):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / f"sel{suffix}"))
    from bmt_voice_studio.config import settings as settings_mod

    settings_mod._settings = None
    s = settings_mod.get_settings()
    s.first_run_complete = True
    s.daily_v11_welcome_seen = True
    s.daily_selected_languages = ["en", "fr"]
    settings_mod.save_settings(s)
    from bmt_voice_studio.ui.pages.daily_bmt import DailyBMTPage

    return DailyBMTPage()


def test_all_fifteen_combinations_count():
    assert len(COMBOS) == 15


@pytest.mark.parametrize("selected", COMBOS, ids=["-".join(c) for c in COMBOS])
def test_panels_visibility_for_combination(qapp, monkeypatch, tmp_path, selected):
    page = _page(monkeypatch, tmp_path, "-".join(selected))
    page.language_selector.set_selected_ids(selected)
    page._relayout_panels()
    qapp.processEvents()
    assert page.language_selector.selected_ids() == selected
    for lid, panel in page.lang_panels.items():
        assert panel.isHidden() == (lid not in selected)
    page.deleteLater()


@pytest.mark.parametrize("selected", COMBOS, ids=["job-" + "-".join(c) for c in COMBOS])
def test_job_flags_match_selection(qapp, monkeypatch, tmp_path, selected):
    page = _page(monkeypatch, tmp_path, "job-" + "-".join(selected))
    page.language_selector.set_selected_ids(selected)
    page.en_edit.setPlainText("Hello {world}")
    page.fr_edit.setPlainText("Bonjour {monde}")
    page.sw_edit.setPlainText("Habari {rafiki}")
    page.pt_edit.setPlainText("Ola {mundo}")
    job = page._job()
    assert job.generate_english == ("en" in selected)
    assert job.generate_french == ("fr" in selected)
    assert job.generate_swahili == ("sw" in selected)
    assert job.generate_portuguese == ("pt" in selected)
    assert job.selected_language_ids() == selected
    page.deleteLater()


def test_unselected_empty_does_not_block_preflight():
    job = DailyJob(
        date=date(2026, 8, 13),
        english_text="Male only script here.",
        french_text="",
        swahili_text="",
        portuguese_text="",
        generate_english=True,
        generate_french=False,
        generate_swahili=False,
        generate_portuguese=False,
    )
    issues = preflight(job)
    assert not any("FRENCH" in i.upper() for i in issues)
    assert not any("SWAHILI" in i.upper() for i in issues)
    assert not any("PORTUGUESE" in i.upper() for i in issues)


def test_selected_empty_blocks_with_required_message():
    job = DailyJob(
        date=date(2026, 8, 13),
        english_text="",
        french_text="Bonjour {monde}",
        generate_english=True,
        generate_french=True,
        generate_swahili=False,
        generate_portuguese=False,
    )
    issues = preflight(job)
    assert any("ENGLISH SCRIPT REQUIRED" in i for i in issues)


def test_swahili_production_approved_allows_generate(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "sw_ok"))
    assert get_language_config("sw").production_approved is True
    job = DailyJob(
        date=date(2026, 8, 13),
        english_text="",
        french_text="",
        swahili_text="Habari {rafiki} more text.",
        generate_english=False,
        generate_french=False,
        generate_swahili=True,
        generate_portuguese=False,
    )
    issues = preflight(job)
    assert not any("PRODUCTION_SETUP_REQUIRED:sw:" in i for i in issues)


def test_portuguese_production_approved_allows_generate(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "pt_ok"))
    assert get_language_config("pt").production_approved is True
    job = DailyJob(
        date=date(2026, 8, 13),
        portuguese_text="Ola {mundo} texto longo.",
        generate_english=False,
        generate_french=False,
        generate_swahili=False,
        generate_portuguese=True,
    )
    issues = preflight(job)
    assert not any("PRODUCTION_SETUP_REQUIRED:pt:" in i for i in issues)


def test_overall_status_selected_languages_only():
    assert (
        overall_status_selected({"en": True, "fr": None, "sw": None, "pt": None}, selected=["en"])
        == "COMPLETE"
    )
    assert (
        overall_status_selected({"en": True, "fr": False}, selected=["en", "fr"])
        == "WARNING"
    )


def test_history_marks_include_portuguese(qapp, monkeypatch, tmp_path):
    page = _page(monkeypatch, tmp_path, "hist")
    page.language_selector.set_selected_ids(["en"])
    page._relayout_panels()
    assert page.hist_table.columnCount() == 8
    headers = [page.hist_table.horizontalHeaderItem(i).text() for i in range(8)]
    assert headers == ["Date", "EN", "FR", "SW", "PT", "Status", "Duration", "Folder"]
    page.deleteLater()


def test_language_selector_requires_at_least_one(qapp, monkeypatch, tmp_path):
    page = _page(monkeypatch, tmp_path, "one")
    page.language_selector.set_selected_ids(["en"])
    for lid, card in page.language_selector._cards.items():
        card.setChecked(False)
    assert len(page.language_selector.selected_ids()) >= 1
    page.deleteLater()


def test_selector_has_four_cards(qapp, monkeypatch, tmp_path):
    page = _page(monkeypatch, tmp_path, "four")
    assert set(page.language_selector._cards) == {"en", "fr", "sw", "pt"}
    page.deleteLater()
