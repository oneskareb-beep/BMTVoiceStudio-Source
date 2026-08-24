"""Bundled release production defaults — independent of developer AppData."""

from __future__ import annotations

import json
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any

_CONFIG_PATH = Path(__file__).with_name("production_defaults.json")


@lru_cache(maxsize=1)
def load_production_defaults() -> dict[str, Any]:
    return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))


def production_defaults_path() -> Path:
    return _CONFIG_PATH


def language_defaults(language_id: str) -> dict[str, Any]:
    data = load_production_defaults()
    langs = data.get("languages") or {}
    return dict(langs.get(language_id) or {})


def all_language_defaults() -> dict[str, dict[str, Any]]:
    data = load_production_defaults()
    return {k: dict(v) for k, v in (data.get("languages") or {}).items()}


def is_release_production_approved(language_id: str) -> bool:
    entry = language_defaults(language_id)
    if not entry:
        return language_id in {"en", "fr"}
    return bool(entry.get("production_approved"))


def release_voice_pair(language_id: str) -> tuple[str, str]:
    entry = language_defaults(language_id)
    return (
        str(entry.get("male_voice") or "").strip(),
        str(entry.get("female_voice") or "").strip(),
    )


def regional_seed_from_defaults(language_id: str) -> dict[str, Any]:
    """Build a regional_approval entry seeded from release defaults."""
    entry = language_defaults(language_id)
    if not entry:
        return {}
    approved = bool(entry.get("production_approved"))
    male = str(entry.get("male_voice") or "").strip()
    female = str(entry.get("female_voice") or "").strip()
    return {
        "language_id": language_id,
        "target_locale": entry.get("target_locale") or entry.get("locale") or "",
        "target_region": entry.get("target_region") or "",
        "fallback_locale": entry.get("fallback_locale") or "",
        "status": "approved" if approved and male and female else "not_checked",
        "all_locale_voices": [],
        "target_male_voices": [],
        "target_female_voices": [],
        "approved_male": male if approved else "",
        "approved_female": female if approved else "",
        "male_voice": male if approved else "",
        "female_voice": female if approved else "",
        "approved_by_user": bool(entry.get("approved_by_user")) if approved else False,
        "approved_fallback": bool(entry.get("approved_fallback")),
        "approval_timestamp": "release-default",
        "approved_at": "release-default",
        "approved_candidate_id": f"release_default_{language_id}",
        "last_checked_at": "",
        "notes": "Seeded from bundled production_defaults.json",
        "production_approved": approved,
    }


def default_regional_languages() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for lang_id in ("sw", "pt"):
        seeded = regional_seed_from_defaults(lang_id)
        if seeded:
            out[lang_id] = seeded
    return deepcopy(out)
