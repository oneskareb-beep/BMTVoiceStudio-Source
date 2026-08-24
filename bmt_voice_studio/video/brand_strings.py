"""Localized labels for locked intro card, MP3 cover art, and brand overlays.

Full cover chrome follows the production language (title + kicker + author + topic).
"""

from __future__ import annotations

_BRAND = {
    "en": {
        "title_line1": "BELIEVERS",
        "title_line2": "MANNA TODAY",
        "series_title": "BELIEVERS MANNA TODAY",
        "daily_devotional": "DAILY DEVOTIONAL",
        "written_by": "Written by:",
        "topic": "TOPIC :",
        "remain_blessed": "Remain Blessed",
        "default_topic": "Daily Devotional",
    },
    "fr": {
        "title_line1": "LA MANNE",
        "title_line2": "QUOTIDIENNE",
        "series_title": "LA MANNE QUOTIDIENNE",
        "daily_devotional": "DÉVOTION QUOTIDIENNE",
        "written_by": "Écrit par :",
        "topic": "THÈME :",
        "remain_blessed": "Restez bénis",
        "default_topic": "Dévotion quotidienne",
    },
    "sw": {
        "title_line1": "MANNA YA",
        "title_line2": "WAAMINIO",
        "series_title": "MANNA YA WAAMINIO",
        "daily_devotional": "IBADA YA KILA SIKU",
        "written_by": "Imeandikwa na:",
        "topic": "MADA :",
        "remain_blessed": "Mubarikiwe",
        "default_topic": "Ibada ya kila siku",
    },
    "pt": {
        "title_line1": "A MANÁ DOS",
        "title_line2": "CRENTES HOJE",
        "series_title": "A MANÁ DOS CRENTES HOJE",
        "daily_devotional": "DEVOCIONAL DIÁRIO",
        "written_by": "Escrito por:",
        "topic": "TEMA :",
        "remain_blessed": "Permaneça abençoado",
        "default_topic": "Devocional diário",
    },
}


def normalize_language(language: str | None) -> str:
    key = (language or "en").strip().lower()
    aliases = {
        "english": "en",
        "french": "fr",
        "swahili": "sw",
        "portuguese": "pt",
        "en-us": "en",
        "en-gb": "en",
        "fr-fr": "fr",
        "pt-pt": "pt",
        "pt-br": "pt",
        "sw-ke": "sw",
        "sw-tz": "sw",
    }
    key = aliases.get(key, key)
    if key in _BRAND:
        return key
    return "en"


def brand_strings(language: str | None) -> dict[str, str]:
    """Return full cover/outro strings for this language."""
    return dict(_BRAND[normalize_language(language)])
