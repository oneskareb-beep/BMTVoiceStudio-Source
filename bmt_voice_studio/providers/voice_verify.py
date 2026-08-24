"""Verify required Edge TTS voices are available before reference production.

A failed catalog download (Windows DNS 11001) must not be reported as
"voice unavailable" — that is what made French abort after English succeeded.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import edge_tts

from bmt_voice_studio.net import prefer_ipv4

logger = logging.getLogger(__name__)

_catalog_cache: list[dict] | None = None


@dataclass
class VoiceCheckResult:
    voice: str
    configured: str
    available: bool
    actual: str
    catalog_error: str = ""


def clear_edge_catalog_cache() -> None:
    global _catalog_cache
    _catalog_cache = None


def _short_names(catalog: list[dict]) -> set[str]:
    names: set[str] = set()
    for item in catalog:
        short = str(item.get("ShortName") or item.get("Name") or "").strip()
        if short:
            names.add(short)
    return names


def _voice_in_catalog(voice: str, names: set[str]) -> bool:
    raw = (voice or "").strip()
    if not raw:
        return False
    if raw in names:
        return True
    lower = {n.lower() for n in names}
    return raw.lower() in lower


async def load_edge_catalog(*, force: bool = False, attempts: int = 4) -> list[dict]:
    """Microsoft voice list, cached for the process. Retries DNS / empty catalog."""
    global _catalog_cache
    if _catalog_cache is not None and not force:
        return list(_catalog_cache)

    last: Exception | None = None
    tries = max(1, attempts)
    for i in range(tries):
        try:
            with prefer_ipv4():
                raw = await asyncio.wait_for(edge_tts.list_voices(), timeout=25.0)
            if raw:
                _catalog_cache = list(raw)
                return list(_catalog_cache)
            last = RuntimeError("Edge TTS returned an empty voice catalog")
        except Exception as exc:
            last = exc
            logger.warning("Edge voice catalog attempt %s/%s failed: %s", i + 1, tries, exc)
        if i + 1 < tries:
            await asyncio.sleep(0.6 * (i + 1))
    assert last is not None
    raise last


async def verify_required_voices(voices: list[str]) -> list[VoiceCheckResult]:
    wanted = [str(v or "").strip() for v in voices]
    try:
        catalog = await load_edge_catalog()
    except Exception as exc:
        # Catalog could not be listed. Do not claim the production voices are gone.
        logger.warning("Edge voice catalog unavailable; skipping pre-check: %s", exc)
        return [
            VoiceCheckResult(
                voice=voice,
                configured=voice,
                available=True,
                actual=voice,
                catalog_error=str(exc),
            )
            for voice in wanted
        ]

    names = _short_names(catalog)
    results: list[VoiceCheckResult] = []
    for voice in wanted:
        ok = _voice_in_catalog(voice, names)
        results.append(
            VoiceCheckResult(
                voice=voice,
                configured=voice,
                available=ok,
                actual=voice if ok else "",
            )
        )
    return results


def verify_required_voices_sync(voices: list[str]) -> list[VoiceCheckResult]:
    return asyncio.run(verify_required_voices(voices))
