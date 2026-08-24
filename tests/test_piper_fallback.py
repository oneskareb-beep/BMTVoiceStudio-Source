"""Regression: automatic Piper fallback when Edge fails."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from bmt_voice_studio.core.models import SynthRequest, SynthResult
from bmt_voice_studio.providers import get_provider, register_provider, reset_registry
from bmt_voice_studio.providers.edge_tts import EdgeTTSProvider
from bmt_voice_studio.providers.piper import PiperProvider, find_piper_executable, PiperVoiceManager


@pytest.mark.asyncio
async def test_automatic_piper_fallback_when_edge_fails(tmp_path: Path):
    if not find_piper_executable():
        pytest.skip("Piper binary not installed")
    installed = PiperVoiceManager().installed_voices()
    if not installed:
        pytest.skip("No Piper voice model installed")

    voice_id = installed[0].id

    class BoomEdge(EdgeTTSProvider):
        async def synthesize(self, request, *, cancel_check=None, on_progress=None):
            return SynthResult(
                success=False,
                error="Could not connect to Edge TTS.",
                provider="edge",
            )

    reset_registry()
    register_provider(BoomEdge())
    register_provider(PiperProvider())

    edge = get_provider("edge")
    out = tmp_path / "fallback.mp3"
    failed = await edge.synthesize(
        SynthRequest(text="Fallback test.", voice="en-US-JennyNeural", output_path=str(out))
    )
    assert not failed.success

    piper = get_provider("piper")
    ok = await piper.synthesize(
        SynthRequest(text="Fallback test with Piper offline.", voice=voice_id, output_path=str(out))
    )
    assert ok.success
    assert ok.provider == "piper"
    assert out.exists() and out.stat().st_size > 500
