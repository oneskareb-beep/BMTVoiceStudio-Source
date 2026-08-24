"""Regional audition / fallback approval tests — no auto-approve."""

from __future__ import annotations

from bmt_voice_studio.core.models import VoiceInfo
from bmt_voice_studio.daily.language_config import get_language_config
from bmt_voice_studio.daily.regional_approval import (
    approve_fallback_candidate,
    is_language_production_approved,
    load_regional_approvals,
    save_regional_approvals,
)
from bmt_voice_studio.daily.regional_audition import select_brazil_pair


def test_select_brazil_prefers_antonio_francisca():
    voices = [
        VoiceInfo(id="pt-BR-AntonioNeural", name="A", locale="pt-BR", gender="Male", provider="edge"),
        VoiceInfo(id="pt-BR-FranciscaNeural", name="F", locale="pt-BR", gender="Female", provider="edge"),
        VoiceInfo(
            id="pt-BR-ThalitaMultilingualNeural",
            name="T",
            locale="pt-BR",
            gender="Female",
            provider="edge",
        ),
    ]
    male, female = select_brazil_pair(voices)
    assert male == "pt-BR-AntonioNeural"
    assert female == "pt-BR-FranciscaNeural"


def test_fallback_approval_can_override_release_default(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "la"))
    assert is_language_production_approved("sw") is True
    assert get_language_config("sw").production_approved is True
    approve_fallback_candidate(
        "sw",
        fallback_locale="sw-KE",
        male_voice="sw-KE-RafikiNeural",
        female_voice="sw-KE-ZuriNeural",
        candidate_id="sw_kenya",
    )
    assert is_language_production_approved("sw") is True
    assert get_language_config("sw").production_approved is True
    assert get_language_config("sw").readiness_state() == "Ready"
    entry = load_regional_approvals()["languages"]["sw"]
    assert entry["approved_by_user"] is True
    assert entry["fallback_locale"] == "sw-KE"
    assert entry["male_voice"] == "sw-KE-RafikiNeural"
    assert entry["female_voice"] == "sw-KE-ZuriNeural"
    assert "Congo" in (entry["target_region"] or "")
    # Portuguese remains release-approved by default
    assert is_language_production_approved("pt") is True


def test_release_defaults_seed_without_user_file(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "la2"))
    data = load_regional_approvals()
    save_regional_approvals(data)
    assert is_language_production_approved("sw") is True
    assert is_language_production_approved("pt") is True
