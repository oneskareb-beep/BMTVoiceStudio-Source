"""French production TTS voices — dedicated Neural, never Multilingual.

Microsoft *MultilingualNeural voices (Remy / Vivienne) code-switch into English
even when SOURCE is entirely French. Dedicated fr-FR Neural voices do not.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bmt_voice_studio.config.presets import VoicePreset

FRENCH_MALE_VOICE = "fr-FR-HenriNeural"
FRENCH_FEMALE_VOICE = "fr-FR-DeniseNeural"

# Old production pair. Remap at load / synthesis so cached settings cannot leak English.
_FRENCH_MULTILINGUAL_REMAP = {
    "fr-FR-RemyMultilingualNeural": FRENCH_MALE_VOICE,
    "fr-FR-VivienneMultilingualNeural": FRENCH_FEMALE_VOICE,
}


def is_multilingual_voice(voice: str) -> bool:
    return "Multilingual" in (voice or "")


def remap_french_voice(voice: str) -> str:
    """Replace known French Multilingual voices with dedicated Neural voices."""
    raw = (voice or "").strip()
    if not raw:
        return raw
    mapped = _FRENCH_MULTILINGUAL_REMAP.get(raw)
    if mapped:
        return mapped
    if is_multilingual_voice(raw) and raw.lower().startswith("fr-"):
        low = raw.lower()
        if "female" in low or "vivienne" in low:
            return FRENCH_FEMALE_VOICE
        return FRENCH_MALE_VOICE
    return raw


def remap_french_preset(preset: VoicePreset) -> VoicePreset:
    """Return a preset whose French voices are dedicated Neural (same object if unchanged)."""
    language = (getattr(preset, "language", "") or "").lower()
    if not language.startswith("fr"):
        return preset
    male = remap_french_voice(preset.male_voice)
    female = remap_french_voice(preset.female_voice)
    if male == preset.male_voice and female == preset.female_voice:
        return preset
    from dataclasses import replace

    return replace(preset, male_voice=male, female_voice=female)
