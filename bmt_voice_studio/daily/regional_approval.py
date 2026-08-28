"""Persistent regional language voice approval (Swahili Congo / Portuguese Angola).

Release builds seed approvals from bundled production_defaults.json so a fresh
machine shows all four languages Ready without copying developer AppData.
"""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

from bmt_voice_studio.config.paths import local_appdata
from bmt_voice_studio.config.production_defaults import (
    default_regional_languages,
    is_release_production_approved,
    language_defaults,
    release_voice_pair,
)
from bmt_voice_studio.config.swahili_tts import (
    SWAHILI_FEMALE_VOICE,
    SWAHILI_LOCALE,
    SWAHILI_MALE_VOICE,
    is_tanzania_voice,
    remap_swahili_voice,
)

# Seeded from bundled production defaults (SW / PT approved fallbacks).
DEFAULT_REGIONAL: dict[str, dict[str, Any]] = default_regional_languages()


def regional_approval_file() -> Path:
    return local_appdata() / "regional_voice_approval.json"


def _merge_entry(default: dict[str, Any], loaded: dict[str, Any] | None) -> dict[str, Any]:
    merged = dict(default)
    if loaded:
        merged.update(loaded)
    return merged


def _upgrade_swahili_east_african(entry: dict[str, Any]) -> bool:
    """Move saved Tanzania voices to Kenya East African neural."""
    male = str(entry.get("approved_male") or entry.get("male_voice") or "")
    female = str(entry.get("approved_female") or entry.get("female_voice") or "")
    locale = str(entry.get("fallback_locale") or "")
    if not (is_tanzania_voice(male) or is_tanzania_voice(female) or locale == "sw-TZ"):
        return False
    entry["approved_male"] = SWAHILI_MALE_VOICE
    entry["approved_female"] = SWAHILI_FEMALE_VOICE
    entry["male_voice"] = SWAHILI_MALE_VOICE
    entry["female_voice"] = SWAHILI_FEMALE_VOICE
    entry["fallback_locale"] = SWAHILI_LOCALE
    entry["notes"] = "East African Kenya neural (Rafiki + Zuri)"
    return True


def load_regional_approvals() -> dict[str, Any]:
    """Load user regional file, or release defaults when absent (fresh machine)."""
    path = regional_approval_file()
    data = {"languages": deepcopy(DEFAULT_REGIONAL)}
    existed = path.exists()
    if existed:
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            langs = loaded.get("languages") or {}
            for key, default in DEFAULT_REGIONAL.items():
                data["languages"][key] = _merge_entry(default, langs.get(key))
        except Exception:
            pass
    sw = data["languages"].get("sw")
    if isinstance(sw, dict) and _upgrade_swahili_east_african(sw) and existed:
        try:
            save_regional_approvals(data)
        except Exception:
            pass
    return data


def save_regional_approvals(data: dict[str, Any]) -> None:
    path = regional_approval_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def get_regional_entry(language_id: str) -> dict[str, Any]:
    data = load_regional_approvals()
    entry = dict((data.get("languages") or {}).get(language_id) or {})
    if not entry and language_id in DEFAULT_REGIONAL:
        return dict(DEFAULT_REGIONAL[language_id])
    return entry


def is_language_production_approved(language_id: str) -> bool:
    if language_id in {"en", "fr"}:
        return True
    entry = get_regional_entry(language_id)
    if entry.get("status") == "revoked":
        return False
    male = entry.get("approved_male") or entry.get("male_voice") or ""
    female = entry.get("approved_female") or entry.get("female_voice") or ""
    if (
        entry.get("status") == "approved"
        and bool(entry.get("approved_by_user"))
        and bool(male)
        and bool(female)
    ):
        return True
    # Bundled release defaults unlock SW/PT on fresh profiles / without AppData.
    return is_release_production_approved(language_id)


def approved_voices_for(language_id: str) -> tuple[str, str]:
    """Return (male, female) voices for production — user approval or release defaults."""
    if language_id in {"en", "fr"}:
        return release_voice_pair(language_id)
    entry = get_regional_entry(language_id)
    male = (entry.get("approved_male") or entry.get("male_voice") or "").strip()
    female = (entry.get("approved_female") or entry.get("female_voice") or "").strip()
    if language_id == "sw":
        male = remap_swahili_voice(male)
        female = remap_swahili_voice(female)
    if male and female and entry.get("status") == "approved" and entry.get("approved_by_user"):
        return male, female
    return release_voice_pair(language_id)


def update_regional_discovery(
    language_id: str,
    *,
    status: str,
    all_locale_voices: list[str],
    target_male_voices: list[str],
    target_female_voices: list[str],
    notes: str = "",
) -> dict[str, Any]:
    data = load_regional_approvals()
    entry = dict((data.get("languages") or {}).get(language_id) or DEFAULT_REGIONAL.get(language_id, {}))
    preserve_user_approval = bool(entry.get("approved_by_user")) and entry.get("status") == "approved"
    preserve_release_default = is_release_production_approved(language_id) and (
        entry.get("approved_candidate_id", "").startswith("release_default")
        or entry.get("approval_timestamp") == "release-default"
        or (
            bool(entry.get("approved_by_user"))
            and bool(entry.get("approved_fallback"))
        )
    )
    entry.update(
        {
            "all_locale_voices": all_locale_voices,
            "target_male_voices": target_male_voices,
            "target_female_voices": target_female_voices,
            "last_checked_at": datetime.now().isoformat(timespec="seconds"),
            "notes": notes,
        }
    )
    if preserve_user_approval or preserve_release_default:
        # Explicit human / release fallback approval must survive rediscovery.
        entry["status"] = "approved"
        if preserve_release_default and not (entry.get("approved_male") and entry.get("approved_female")):
            male, female = release_voice_pair(language_id)
            entry["approved_male"] = male
            entry["approved_female"] = female
            entry["male_voice"] = male
            entry["female_voice"] = female
            entry["approved_by_user"] = True
            defaults = language_defaults(language_id)
            entry["fallback_locale"] = defaults.get("fallback_locale") or entry.get("fallback_locale") or ""
    else:
        entry["status"] = status
        # Clear only non-user / target-locale approvals that no longer match.
        if entry.get("status") == "approved" and not entry.get("fallback_locale"):
            if entry.get("approved_male") not in target_male_voices or entry.get(
                "approved_female"
            ) not in target_female_voices:
                entry["status"] = (
                    "approval_required" if target_male_voices and target_female_voices else status
                )
                entry["approved_male"] = ""
                entry["approved_female"] = ""
                entry["male_voice"] = ""
                entry["female_voice"] = ""
                entry["approved_at"] = ""
                entry["approval_timestamp"] = ""
                entry["approved_by_user"] = False
    data.setdefault("languages", {})[language_id] = entry
    save_regional_approvals(data)
    return entry


def approve_regional_pair(language_id: str, male_voice: str, female_voice: str) -> dict[str, Any]:
    """Approve a discovered *target-locale* pair (sw-CD / pt-AO)."""
    data = load_regional_approvals()
    entry = dict((data.get("languages") or {}).get(language_id) or {})
    males = entry.get("target_male_voices") or []
    females = entry.get("target_female_voices") or []
    if male_voice not in males or female_voice not in females:
        raise ValueError("Approved voices must come from discovered regional target voices.")
    stamp = datetime.now().isoformat(timespec="seconds")
    entry.update(
        {
            "approved_male": male_voice,
            "approved_female": female_voice,
            "male_voice": male_voice,
            "female_voice": female_voice,
            "fallback_locale": "",
            "approved_by_user": True,
            "approval_timestamp": stamp,
            "approved_at": stamp,
            "approved_candidate_id": "",
            "status": "approved",
            "production_approved": True,
        }
    )
    data.setdefault("languages", {})[language_id] = entry
    save_regional_approvals(data)
    return entry


def approve_fallback_candidate(
    language_id: str,
    *,
    fallback_locale: str,
    male_voice: str,
    female_voice: str,
    candidate_id: str,
) -> dict[str, Any]:
    """Persist an explicit human-approved fallback pair for production."""
    if not male_voice or not female_voice:
        raise ValueError("Male and female voices are required.")
    if not fallback_locale:
        raise ValueError("fallback_locale is required.")
    data = load_regional_approvals()
    default = DEFAULT_REGIONAL.get(language_id, {})
    entry = dict((data.get("languages") or {}).get(language_id) or default)
    stamp = datetime.now().isoformat(timespec="seconds")
    entry.update(
        {
            "target_region": default.get("target_region") or entry.get("target_region") or "",
            "target_locale": default.get("target_locale") or entry.get("target_locale") or "",
            "fallback_locale": fallback_locale,
            "male_voice": male_voice,
            "female_voice": female_voice,
            "approved_male": male_voice,
            "approved_female": female_voice,
            "approved_by_user": True,
            "approved_fallback": True,
            "approval_timestamp": stamp,
            "approved_at": stamp,
            "approved_candidate_id": candidate_id,
            "status": "approved",
            "production_approved": True,
            "notes": (
                f"Human-approved fallback locale {fallback_locale} "
                f"for target {entry.get('target_region')}."
            ),
        }
    )
    data.setdefault("languages", {})[language_id] = entry
    save_regional_approvals(data)
    return entry


def set_swahili_trial_pair(
    *,
    male_voice: str = "sw-TZ-DaudiNeural",
    female_voice: str = "sw-TZ-RehemaNeural",
    trial_locale: str = "sw-TZ",
    trial_pair: str = "Daudi + Rehema",
) -> dict[str, Any]:
    """Record Tanzania trial pair for listening.

    Release defaults already approve Daudi+Rehema for production. Trial recording
    must not wipe a release-default or explicit user approval of the same pair.
    """
    data = load_regional_approvals()
    entry = dict((data.get("languages") or {}).get("sw") or DEFAULT_REGIONAL.get("sw", {}))
    stamp = datetime.now().isoformat(timespec="seconds")
    already_approved_same = (
        is_language_production_approved("sw")
        and (entry.get("approved_male") or entry.get("male_voice") or male_voice) == male_voice
        and (entry.get("approved_female") or entry.get("female_voice") or female_voice) == female_voice
    )
    entry.update(
        {
            "trial_locale": trial_locale,
            "trial_pair": trial_pair,
            "trial_male_voice": male_voice,
            "trial_female_voice": female_voice,
            "trial_set_at": stamp,
            "fallback_locale": trial_locale,
            "notes": (
                f"Trial listening pair: {trial_pair} ({male_voice} / {female_voice}). "
                f"trial_locale={trial_locale}. Target remains Congo/DRC."
            ),
        }
    )
    if already_approved_same or is_release_production_approved("sw"):
        entry["production_approved"] = True
        entry["approved_by_user"] = True
        entry["approved_male"] = male_voice
        entry["approved_female"] = female_voice
        entry["male_voice"] = male_voice
        entry["female_voice"] = female_voice
        entry["status"] = "approved"
        entry["approved_fallback"] = True
        if not entry.get("approval_timestamp"):
            entry["approval_timestamp"] = "release-default"
            entry["approved_at"] = "release-default"
            entry["approved_candidate_id"] = "release_default_sw"
    else:
        entry["production_approved"] = False
        entry["approved_by_user"] = False
        entry["approved_male"] = ""
        entry["approved_female"] = ""
        entry["male_voice"] = ""
        entry["female_voice"] = ""
        entry["approval_timestamp"] = ""
        entry["approved_at"] = ""
        entry["approved_candidate_id"] = ""
        entry["status"] = "trial"
    data.setdefault("languages", {})["sw"] = entry
    save_regional_approvals(data)
    return entry


def get_swahili_trial_pair() -> dict[str, Any]:
    entry = get_regional_entry("sw")
    return {
        "trial_locale": entry.get("trial_locale") or "",
        "trial_pair": entry.get("trial_pair") or "",
        "male_voice": entry.get("trial_male_voice") or "",
        "female_voice": entry.get("trial_female_voice") or "",
        "trial_set_at": entry.get("trial_set_at") or "",
        "production_approved": is_language_production_approved("sw"),
        "is_production_approved": is_language_production_approved("sw"),
        "status_label": (
            "Ready (release default)"
            if is_language_production_approved("sw")
            else "TRIAL — NOT APPROVED"
        ),
        "target_region": entry.get("target_region") or "Congo/DRC",
        "notes": entry.get("notes") or "",
    }


def select_swahili_male_candidate(candidate_id: str, male_voice: str) -> dict[str, Any]:
    """Record human male preference only — does NOT clear release-default approval."""
    data = load_regional_approvals()
    entry = dict((data.get("languages") or {}).get("sw") or DEFAULT_REGIONAL.get("sw", {}))
    release_locked = is_release_production_approved("sw") and is_language_production_approved("sw")
    entry.update(
        {
            "selected_male_candidate_id": candidate_id,
            "selected_male_voice": male_voice,
            "selected_male_at": datetime.now().isoformat(timespec="seconds"),
            "notes": (
                f"Male candidate selected for review: {male_voice}. "
                + (
                    "Release default production approval retained."
                    if release_locked
                    else "Not production-approved."
                )
            ),
        }
    )
    if not release_locked:
        status = entry.get("status") or "unavailable"
        if status == "approved" and not entry.get("approved_by_user"):
            status = "unavailable"
        entry["approved_by_user"] = False
        entry["approved_male"] = ""
        entry["approved_female"] = ""
        entry["male_voice"] = ""
        entry["female_voice"] = ""
        entry["approval_timestamp"] = ""
        entry["approved_at"] = ""
        entry["approved_candidate_id"] = ""
        entry["status"] = status if status != "approved" else "unavailable"
        if entry.get("status") == "approved":
            entry["status"] = "unavailable"
    data.setdefault("languages", {})["sw"] = entry
    save_regional_approvals(data)
    return entry


def readiness_label(language_id: str) -> str:
    if language_id in {"en", "fr"}:
        return "Ready"
    if is_language_production_approved(language_id):
        return "Ready"
    entry = get_regional_entry(language_id)
    status = entry.get("status") or "not_checked"
    mapping = {
        "not_checked": "Regional voice pending",
        "available": "Approval required",
        "approval_required": "Approval required",
        "trial": "Trial pair — not approved",
        "approved": "Ready",
        "unavailable": "Regional voice unavailable",
        "revoked": "Approval required",
    }
    return mapping.get(status, "Regional voice pending")
