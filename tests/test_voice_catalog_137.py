"""Regression: Edge voice catalog DNS flakes must not mark French as unavailable."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from bmt_voice_studio.providers.voice_verify import (
    VoiceCheckResult,
    clear_edge_catalog_cache,
    load_edge_catalog,
    verify_required_voices,
)


@pytest.fixture(autouse=True)
def _reset_catalog():
    clear_edge_catalog_cache()
    yield
    clear_edge_catalog_cache()


def _voice(name: str) -> dict:
    return {"ShortName": name, "Name": name, "Locale": name[:5], "Gender": "Male"}


@pytest.mark.asyncio
async def test_verify_retries_dns_then_uses_cached_catalog(monkeypatch):
    hits = {"n": 0}

    async def flaky_list():
        hits["n"] += 1
        if hits["n"] < 3:
            raise OSError("[Errno 11001] getaddrinfo failed")
        return [
            _voice("fr-FR-HenriNeural"),
            _voice("fr-FR-DeniseNeural"),
        ]

    monkeypatch.setattr("bmt_voice_studio.providers.voice_verify.edge_tts.list_voices", flaky_list)
    monkeypatch.setattr(
        "bmt_voice_studio.providers.voice_verify.asyncio.sleep",
        AsyncMock(),
    )
    first = await load_edge_catalog()
    again = await load_edge_catalog()
    assert hits["n"] == 3
    assert first == again
    checks = await verify_required_voices(["fr-FR-HenriNeural", "fr-FR-DeniseNeural"])
    assert all(c.available for c in checks)
    assert hits["n"] == 3


@pytest.mark.asyncio
async def test_catalog_failure_does_not_mark_french_unavailable(monkeypatch):
    async def always_fail():
        raise OSError("[Errno 11001] getaddrinfo failed")

    monkeypatch.setattr("bmt_voice_studio.providers.voice_verify.edge_tts.list_voices", always_fail)
    monkeypatch.setattr(
        "bmt_voice_studio.providers.voice_verify.asyncio.sleep",
        AsyncMock(),
    )
    checks = await verify_required_voices(["fr-FR-HenriNeural", "fr-FR-DeniseNeural"])
    assert [c.configured for c in checks] == ["fr-FR-HenriNeural", "fr-FR-DeniseNeural"]
    assert all(c.available for c in checks)
    assert all(c.catalog_error for c in checks)
    missing = [c.configured for c in checks if not c.available and not c.catalog_error]
    assert missing == []


@pytest.mark.asyncio
async def test_genuine_missing_voice_still_unavailable(monkeypatch):
    async def catalog():
        return [_voice("en-NG-AbeoNeural")]

    monkeypatch.setattr("bmt_voice_studio.providers.voice_verify.edge_tts.list_voices", catalog)
    checks = await verify_required_voices(["fr-FR-HenriNeural"])
    assert checks[0].available is False
    assert checks[0].catalog_error == ""


def test_pipeline_skips_unavailable_when_catalog_error():
    checks = [
        VoiceCheckResult(
            voice="fr-FR-HenriNeural",
            configured="fr-FR-HenriNeural",
            available=True,
            actual="fr-FR-HenriNeural",
            catalog_error="getaddrinfo failed",
        )
    ]
    missing = [c.configured for c in checks if not c.available and not c.catalog_error]
    assert missing == []
