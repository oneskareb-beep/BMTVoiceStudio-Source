"""Provider/voice compatibility guards."""

from __future__ import annotations

from bmt_voice_studio.providers.base import TTSProviderError


def is_edge_neural_voice(voice: str) -> bool:
    """Heuristic: Microsoft Edge TTS ShortNames end with Neural / MultilingualNeural."""
    v = (voice or "").strip()
    if not v:
        return False
    return v.endswith("Neural") or "MultilingualNeural" in v or "-Neural" in v


def assert_provider_voice_compatible(provider_id: str, voice: str) -> None:
    """Raise before synthesis if an Edge Neural voice is routed to Piper."""
    pid = (provider_id or "").strip().lower()
    if pid == "piper" and is_edge_neural_voice(voice):
        raise TTSProviderError(
            "PROVIDER CONFIGURATION ERROR: "
            f"Edge TTS voice '{voice}' was incorrectly assigned to PiperProvider. "
            "BMT Original Pipeline requires Edge TTS for Neural voices."
        )
    if pid not in ("edge", "piper", ""):
        return
