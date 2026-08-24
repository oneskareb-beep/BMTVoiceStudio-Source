"""Live Edge TTS regional voice discovery — no silent locale fallback."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from bmt_voice_studio.daily.regional_approval import update_regional_discovery
from bmt_voice_studio.providers.edge_tts import EdgeTTSProvider


@dataclass
class RegionalDiscoveryResult:
    language_id: str
    target_locale: str
    status: str
    all_prefix_voices: list[str] = field(default_factory=list)
    target_voices: list[str] = field(default_factory=list)
    male_voices: list[str] = field(default_factory=list)
    female_voices: list[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "language_id": self.language_id,
            "target_locale": self.target_locale,
            "status": self.status,
            "all_prefix_voices": self.all_prefix_voices,
            "target_voices": self.target_voices,
            "male_voices": self.male_voices,
            "female_voices": self.female_voices,
            "notes": self.notes,
        }


def _gender_bucket(gender: str) -> str:
    g = (gender or "").lower()
    if "female" in g:
        return "female"
    if "male" in g:
        return "male"
    return "unknown"


async def discover_regional_voices(
    *,
    language_id: str,
    target_locale: str,
    prefix: str,
) -> RegionalDiscoveryResult:
    """Query live Edge catalog. Never substitutes a different regional locale."""
    provider = EdgeTTSProvider()
    voices = await provider.list_voices()
    prefix_l = prefix.lower()
    target_l = target_locale.lower()

    all_prefix = [v.id for v in voices if (v.id or "").lower().startswith(prefix_l)]
    target = [v for v in voices if (v.locale or "").lower() == target_l or (v.id or "").lower().startswith(target_l)]
    target_ids = [v.id for v in target]
    males = [v.id for v in target if _gender_bucket(v.gender) == "male"]
    females = [v.id for v in target if _gender_bucket(v.gender) == "female"]

    if males and females:
        status = "approval_required"
        notes = f"Found {len(males)} male and {len(females)} female voices for {target_locale}."
    elif target_ids:
        status = "unavailable"
        notes = (
            f"{target_locale} voices exist but a complete male+female pair was not found. "
            "Do not silently use another region."
        )
    else:
        status = "unavailable"
        notes = (
            f"No {target_locale} voices found in live Edge catalog. "
            f"Other {prefix}* voices were NOT selected automatically."
        )

    update_regional_discovery(
        language_id,
        status=status,
        all_locale_voices=sorted(set(all_prefix)),
        target_male_voices=males,
        target_female_voices=females,
        notes=notes,
    )
    # Also store target voice list on entry via notes/all — all_prefix already saved.
    return RegionalDiscoveryResult(
        language_id=language_id,
        target_locale=target_locale,
        status=status,
        all_prefix_voices=sorted(set(all_prefix)),
        target_voices=target_ids,
        male_voices=males,
        female_voices=females,
        notes=notes,
    )


async def discover_swahili_congo() -> RegionalDiscoveryResult:
    return await discover_regional_voices(
        language_id="sw",
        target_locale="sw-CD",
        prefix="sw-",
    )


async def discover_portuguese_angola() -> RegionalDiscoveryResult:
    return await discover_regional_voices(
        language_id="pt",
        target_locale="pt-AO",
        prefix="pt-",
    )
