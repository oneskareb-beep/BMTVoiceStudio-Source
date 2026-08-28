"""East African Swahili production voices (Kenya), never Tanzanian fallback.

Ministry listeners asked for West/East African pronunciation. Edge has no
West African or Congo (sw-CD) neural voices. Kenya (sw-KE) is East African
and is the closest authentic African Swahili pair.

Legacy Tanzania voices (Daudi / Rehema) are remapped at load / synthesis so
old AppData approvals cannot keep shipping TZ pronunciation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bmt_voice_studio.config.presets import VoicePreset

SWAHILI_MALE_VOICE = "sw-KE-RafikiNeural"
SWAHILI_FEMALE_VOICE = "sw-KE-ZuriNeural"
SWAHILI_LOCALE = "sw-KE"

_TZ_TO_KE = {
    "sw-TZ-DaudiNeural": SWAHILI_MALE_VOICE,
    "sw-TZ-RehemaNeural": SWAHILI_FEMALE_VOICE,
}


def is_tanzania_voice(voice: str) -> bool:
    raw = (voice or "").strip()
    return raw in _TZ_TO_KE or raw.lower().startswith("sw-tz-")


def remap_swahili_voice(voice: str) -> str:
    """Replace Tanzanian Edge voices with East African Kenya Neural voices."""
    raw = (voice or "").strip()
    if not raw:
        return raw
    mapped = _TZ_TO_KE.get(raw)
    if mapped:
        return mapped
    if raw.lower().startswith("sw-tz-"):
        low = raw.lower()
        if "rehema" in low or "female" in low or "zuri" in low:
            return SWAHILI_FEMALE_VOICE
        return SWAHILI_MALE_VOICE
    return raw


def remap_swahili_preset(preset: VoicePreset) -> VoicePreset:
    language = (getattr(preset, "language", "") or "").lower()
    if not language.startswith("sw"):
        return preset
    male = remap_swahili_voice(preset.male_voice)
    female = remap_swahili_voice(preset.female_voice)
    locale = SWAHILI_LOCALE if language.startswith("sw-tz") else preset.language
    if male == preset.male_voice and female == preset.female_voice and locale == preset.language:
        return preset
    from dataclasses import replace

    return replace(preset, male_voice=male, female_voice=female, language=locale)
