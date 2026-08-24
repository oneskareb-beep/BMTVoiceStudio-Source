"""Segment cache hashing for smart regeneration."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from bmt_voice_studio.core.models import Segment


def stable_dumps(data: dict[str, Any]) -> str:
    return json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def hash_payload(payload: dict[str, Any]) -> str:
    raw = stable_dumps(payload).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def segment_cache_hash(
    segment: Segment,
    *,
    provider: str | None = None,
    voice: str | None = None,
    rate: str | None = None,
    pitch: str | None = None,
    volume: str | None = None,
    spoken_text: str | None = None,
    spoken_norm_tag: str | None = None,
) -> str:
    """Hash text + voice settings that affect synthesized audio."""
    payload = {
        "text": (spoken_text if spoken_text is not None else segment.text).strip(),
        "speaker": segment.speaker.value,
        "provider": provider or segment.provider,
        "voice": voice if voice is not None else segment.voice,
        "rate": rate if rate is not None else segment.rate,
        "pitch": pitch if pitch is not None else segment.pitch,
        "volume": volume if volume is not None else segment.volume,
    }
    if spoken_norm_tag:
        payload["spoken_norm_tag"] = spoken_norm_tag
    return hash_payload(payload)


def needs_regeneration(segment: Segment, new_hash: str) -> bool:
    if not segment.enabled:
        return False
    if not segment.audio_path:
        return True
    if not segment.cache_hash:
        return True
    return segment.cache_hash != new_hash
