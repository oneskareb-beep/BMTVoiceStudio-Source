"""Force Edge TTS SSML xml:lang to match the selected voice locale.

edge-tts hardcodes xml:lang='en-US' on every request. Changing the document
language to the voice locale (e.g. fr-FR, en-NG) keeps dedicated Neural voices
on the right G2P path.

Do NOT wrap <prosody> in a nested <lang> tag: Microsoft currently returns
NoAudioReceived for that SSML shape, which surfaces in the app as
"BMT VOICE SERVICE TEMPORARILY UNAVAILABLE".
"""

from __future__ import annotations

import re
from typing import Any

_PATCHED = False

_VOICE_LOCALE = re.compile(r"^([a-z]{2})-([A-Za-z]{2,})", re.IGNORECASE)
_LONG_VOICE_LOCALE = re.compile(
    r"\(\s*([a-z]{2,})-([A-Za-z]{2,})\s*,",
    re.IGNORECASE,
)


def voice_ssml_lang(voice: str) -> str:
    """Locale for SSML from an Edge ShortName or long Microsoft voice name.

    Short: fr-FR-HenriNeural -> fr-FR
    Long:  Microsoft Server Speech Text to Speech Voice (fr-FR, HenriNeural) -> fr-FR
    """
    raw = (voice or "").strip()
    match = _VOICE_LOCALE.match(raw)
    if match:
        return f"{match.group(1).lower()}-{match.group(2).upper()}"
    long_match = _LONG_VOICE_LOCALE.search(raw)
    if long_match:
        return f"{long_match.group(1).lower()}-{long_match.group(2).upper()}"
    return "en-US"


def rewrite_ssml_lang(ssml: str, lang: str) -> str:
    """Replace the hardcoded en-US document lang. Keep SSML otherwise unchanged."""
    if not ssml or not lang:
        return ssml
    out = ssml.replace("xml:lang='en-US'", f"xml:lang='{lang}'", 1)
    out = out.replace('xml:lang="en-US"', f'xml:lang="{lang}"', 1)
    return out


def patch_edge_tts_ssml_lang() -> None:
    """Monkeypatch edge_tts.communicate.mkssml so every request uses the voice locale."""
    global _PATCHED
    if _PATCHED:
        return
    import edge_tts.communicate as comm

    original = comm.mkssml
    if getattr(original, "_bmt_lang_patched", False):
        _PATCHED = True
        return

    def mkssml(tc: Any, escaped_text: Any) -> str:
        ssml = original(tc, escaped_text)
        lang = voice_ssml_lang(getattr(tc, "voice", "") or "")
        return rewrite_ssml_lang(ssml, lang)

    mkssml._bmt_lang_patched = True  # type: ignore[attr-defined]
    comm.mkssml = mkssml
    _PATCHED = True
