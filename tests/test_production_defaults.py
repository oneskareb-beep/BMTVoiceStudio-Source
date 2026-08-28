"""Release production defaults — fresh machine four-language Ready."""

from __future__ import annotations

from itertools import combinations
from pathlib import Path

from bmt_voice_studio.config.paths import (
    default_exports_dir,
    local_appdata,
    user_data_root,
)
from bmt_voice_studio.config.production_defaults import (
    is_release_production_approved,
    language_defaults,
    load_production_defaults,
    release_voice_pair,
)
from bmt_voice_studio.config.presets import BMT_ENGLISH, BMT_FRENCH, BMT_PORTUGUESE, BMT_SWAHILI
from bmt_voice_studio.daily.language_config import (
    get_language_config,
    production_details_text,
    production_ready_languages,
    selectable_daily_languages,
)
from bmt_voice_studio.daily.pipeline import DailyJob, preflight
from bmt_voice_studio.daily.regional_approval import (
    is_language_production_approved,
    load_regional_approvals,
)
from datetime import date


LANGS = ["en", "fr", "sw", "pt"]
COMBOS = [list(c) for n in range(1, 5) for c in combinations(LANGS, n)]


def test_production_defaults_file_bundled():
    data = load_production_defaults()
    assert data["version"] == "1.2.0"
    assert set(data["languages"]) == {"en", "fr", "sw", "pt"}
    assert data["provider"] == "edge"
    assert data["piper_production_policy"] == "forbidden_for_approved_daily"


def test_fresh_profile_all_four_ready(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "fresh_la"))
    assert not (Path(tmp_path / "fresh_la") / "BMTVoiceStudio" / "regional_voice_approval.json").exists()
    for lid in LANGS:
        assert is_release_production_approved(lid) is True
        assert is_language_production_approved(lid) is True
        cfg = get_language_config(lid)
        assert cfg is not None
        assert cfg.production_approved is True
        assert cfg.readiness_state() == "Ready"
    ready = production_ready_languages()
    assert [c.language_id for c in ready] == LANGS


def test_swahili_portuguese_release_default_voices(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "voices_la"))
    sw = get_language_config("sw")
    pt = get_language_config("pt")
    assert sw is not None and pt is not None
    assert sw.male_voice == "sw-KE-RafikiNeural"
    assert sw.female_voice == "sw-KE-ZuriNeural"
    assert pt.male_voice == "pt-BR-AntonioNeural"
    assert pt.female_voice == "pt-BR-FranciscaNeural"
    assert sw.target_locale == "sw-CD"
    assert sw.fallback_locale == "sw-KE"
    assert pt.target_locale == "pt-AO"
    assert pt.fallback_locale == "pt-BR"
    assert sw.target_region.replace(" ", "") in {"Congo/DRC", "Congo/DRC"}
    assert "Congo" in sw.target_region or "DRC" in sw.target_region
    assert pt.target_region == "Angola"


def test_daily_ui_details_hide_fallback_tech():
    text = production_details_text()
    assert "Swahili" in text.upper() or "SWAHILI" in text
    assert "Ready" in text
    for banned in ("sw-TZ", "sw-KE", "pt-BR", "DaudiNeural", "RafikiNeural", "AntonioNeural", "fallback_locale", "Tanzania", "Kenya", "Brazil"):
        assert banned not in text


def test_preset_voices_match_release_defaults():
    assert BMT_ENGLISH.male_voice == "en-NG-AbeoNeural"
    assert BMT_ENGLISH.female_voice == "en-NG-EzinneNeural"
    assert BMT_FRENCH.male_voice == "fr-FR-HenriNeural"
    assert BMT_FRENCH.female_voice == "fr-FR-DeniseNeural"
    assert BMT_SWAHILI.male_voice == "sw-KE-RafikiNeural"
    assert BMT_SWAHILI.female_voice == "sw-KE-ZuriNeural"
    assert BMT_PORTUGUESE.male_voice == "pt-BR-AntonioNeural"
    assert BMT_PORTUGUESE.female_voice == "pt-BR-FranciscaNeural"
    assert BMT_FRENCH.pipeline.lowpass_hz is None


def test_all_fifteen_combos_preflight_approved(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "combo_la"))
    scripts = {
        "en": "Male line one. {Female line two.} Male close.",
        "fr": "Ligne homme. {Ligne femme.} Fin homme.",
        "sw": "Habari bwana. {Habari mama.} Mwisho.",
        "pt": "Ola senhor. {Ola senhora.} Fim.",
    }
    assert len(COMBOS) == 15
    for selected in COMBOS:
        job = DailyJob(
            date=date(2026, 8, 13),
            english_text=scripts["en"] if "en" in selected else "",
            french_text=scripts["fr"] if "fr" in selected else "",
            swahili_text=scripts["sw"] if "sw" in selected else "",
            portuguese_text=scripts["pt"] if "pt" in selected else "",
            generate_english="en" in selected,
            generate_french="fr" in selected,
            generate_swahili="sw" in selected,
            generate_portuguese="pt" in selected,
        )
        issues = preflight(job)
        setup = [i for i in issues if i.startswith("PRODUCTION_SETUP_REQUIRED")]
        assert setup == [], f"{selected} blocked: {setup}"


def test_no_hardcoded_developer_paths_in_runtime_modules():
    root = Path(__file__).resolve().parents[1] / "bmt_voice_studio"
    banned = ("C:\\Users\\aganz", "C:/Users/aganz", "Documents\\BMTVoiceStudio")
    offenders: list[str] = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in banned:
            if token in text:
                offenders.append(f"{path.name}:{token}")
    assert offenders == []


def test_user_data_paths_are_dynamic(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "cfg"))
    la = local_appdata()
    assert str(tmp_path / "cfg") in str(la)
    assert "aganz" not in str(la).lower() or "aganz" in str(tmp_path).lower()
    exports = default_exports_dir()
    assert exports.name == "Exports"
    assert user_data_root().name == "BMT Voice Studio"


def test_release_voice_pairs():
    assert release_voice_pair("en") == ("en-NG-AbeoNeural", "en-NG-EzinneNeural")
    assert release_voice_pair("fr") == (
        "fr-FR-HenriNeural",
        "fr-FR-DeniseNeural",
    )
    assert release_voice_pair("sw") == ("sw-KE-RafikiNeural", "sw-KE-ZuriNeural")
    assert release_voice_pair("pt") == ("pt-BR-AntonioNeural", "pt-BR-FranciscaNeural")


def test_fresh_regional_file_seeds_release_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "seed_la"))
    data = load_regional_approvals()
    sw = data["languages"]["sw"]
    pt = data["languages"]["pt"]
    assert sw["status"] == "approved"
    assert pt["status"] == "approved"
    assert sw["approved_by_user"] is True
    assert pt["approved_by_user"] is True
    assert sw["fallback_locale"] == "sw-KE"
    assert pt["fallback_locale"] == "pt-BR"
    assert language_defaults("sw")["approved_fallback"] is True
