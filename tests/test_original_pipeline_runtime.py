"""Regression: Daily BMT Original Pipeline must use Edge TTS, never Piper."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bmt_voice_studio.config.presets import BMT_ENGLISH, BMT_FRENCH
from bmt_voice_studio.core.models import SynthResult
from bmt_voice_studio.daily.pipeline import (
    DailyJob,
    effective_job_config,
    resolve_daily_provider,
    run_daily_job,
)
from bmt_voice_studio.providers.base import TTSProviderError
from bmt_voice_studio.providers.provider_guard import (
    assert_provider_voice_compatible,
    is_edge_neural_voice,
)


def _original_job(**kwargs) -> DailyJob:
    defaults = dict(
        date=date(2026, 8, 13),
        english_text="Male open\n{Female middle}\nMale close",
        french_text="Homme\n{Femme}\nHomme fin",
        generate_english=True,
        generate_french=True,
        processing_mode="original",
        strict_source_mode=True,
        mastering=False,
        use_piper_fallback=False,
        provider="piper",  # intentionally wrong — must be ignored
        pause_ms=450,
        mp3_bitrate=128,
    )
    defaults.update(kwargs)
    return DailyJob(**defaults)


def test_resolve_daily_provider_forces_edge_for_original():
    job = _original_job(provider="piper")
    assert resolve_daily_provider(job, BMT_ENGLISH) == "edge"
    assert resolve_daily_provider(job, BMT_FRENCH) == "edge"


def test_effective_config_english_original_pipeline():
    job = _original_job(provider="piper", pause_ms=450, mp3_bitrate=128, mastering=True)
    cfg = effective_job_config(job, BMT_ENGLISH)
    assert cfg["provider"] == "edge"
    assert cfg["pause_ms"] == 500
    assert cfg["mp3_bitrate"] == 192
    assert cfg["mastering"] is False
    assert cfg["lowpass_hz"] == 7000
    assert cfg["allow_piper_fallback"] is False
    assert cfg["male_voice"] == "en-NG-AbeoNeural"
    assert cfg["female_voice"] == "en-NG-EzinneNeural"
    assert cfg["rate"] == "-10%"
    assert cfg["pitch"] == "-3Hz"
    assert cfg["volume"] == "+0%"


def test_effective_config_french_original_pipeline():
    job = _original_job(provider="piper", pause_ms=450, mp3_bitrate=128, mastering=True)
    cfg = effective_job_config(job, BMT_FRENCH)
    assert cfg["provider"] == "edge"
    assert cfg["pause_ms"] == 500
    assert cfg["mastering"] is False
    assert cfg["lowpass_hz"] is None
    assert cfg["mp3_bitrate"] is None
    assert cfg["allow_piper_fallback"] is False
    assert cfg["male_voice"] == "fr-FR-HenriNeural"
    assert cfg["female_voice"] == "fr-FR-DeniseNeural"
    assert cfg["volume"] == "+5%"


def test_provider_guard_blocks_edge_voice_on_piper():
    assert is_edge_neural_voice("en-NG-AbeoNeural")
    assert is_edge_neural_voice("fr-FR-HenriNeural")
    with pytest.raises(TTSProviderError) as exc:
        assert_provider_voice_compatible("piper", "en-NG-AbeoNeural")
    assert "PROVIDER CONFIGURATION ERROR" in str(exc.value)
    assert_provider_voice_compatible("edge", "en-NG-AbeoNeural")


@pytest.mark.asyncio
async def test_daily_original_pipeline_never_invokes_piper(tmp_path: Path):
    """Real Daily BMT path: even if job.provider=piper, synthesis must use Edge."""
    job = _original_job(base_exports=tmp_path)
    edge_calls: list[str] = []
    piper_calls: list[str] = []

    class FakeEdge:
        id = "edge"

        async def health_check(self):
            return True, "READY"

        async def synthesize(self, request, **kwargs):
            edge_calls.append(request.voice)
            path = Path(request.output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            # Minimal valid-ish MPEG frame header bytes for magic check may fail —
            # write enough bytes and patch magic validation instead.
            path.write_bytes(b"ID3" + b"\x00" * 128)
            return SynthResult(success=True, output_path=str(path), provider="edge")

    class FakePiper:
        id = "piper"

        async def health_check(self):
            return True, "READY"

        async def synthesize(self, request, **kwargs):
            piper_calls.append(request.voice)
            return SynthResult(success=False, error="should not be called", provider="piper")

    def fake_get_provider(pid: str):
        if pid == "edge":
            return FakeEdge()
        if pid == "piper":
            return FakePiper()
        raise AssertionError(pid)

    async def fake_verify(voices):
        from bmt_voice_studio.providers.voice_verify import VoiceCheckResult

        return [
            VoiceCheckResult(voice=v, configured=v, available=True, actual=v) for v in voices
        ]

    with (
        patch("bmt_voice_studio.daily.pipeline.get_provider", side_effect=fake_get_provider),
        patch("bmt_voice_studio.daily.pipeline.verify_required_voices", side_effect=fake_verify),
        patch("bmt_voice_studio.daily.pipeline.validate_audio_magic", return_value=(True, "mp3")),
        patch("bmt_voice_studio.daily.pipeline.join_segments"),
        patch("bmt_voice_studio.daily.pipeline.export_original_pipeline") as exp,
        patch("bmt_voice_studio.daily.pipeline._probe", return_value={"duration_sec": 1.0, "bitrate_kbps": 192, "sample_rate": 44100, "channels": "mono", "codec": "mp3"}),
        patch("bmt_voice_studio.daily.pipeline._loudness", return_value={}),
        patch("bmt_voice_studio.daily.pipeline.FFmpegService") as ff_cls,
    ):
        ff = MagicMock()
        ff.health_check.return_value = (True, "ok")
        ff_cls.return_value = ff
        exp.side_effect = lambda *a, **k: {}
        result = await run_daily_job(job)

    assert piper_calls == []
    assert result.english is not None
    assert result.french is not None
    # All Edge voices used
    assert "en-NG-AbeoNeural" in edge_calls
    assert "en-NG-EzinneNeural" in edge_calls
    assert "fr-FR-HenriNeural" in edge_calls
    assert "fr-FR-DeniseNeural" in edge_calls
    assert result.english.get("piper_invocations", 0) == 0
    assert result.french.get("piper_invocations", 0) == 0
    assert result.english.get("actual_provider") == "edge"
    assert result.french.get("actual_provider") == "edge"
    assert all(s.get("actual_provider") == "edge" for s in result.english["segments"])
    assert all(s.get("actual_provider") == "edge" for s in result.french["segments"])
    # Effective configs on language blocks
    assert result.english["pause_ms"] == 500
    assert result.english["mp3_bitrate"] == 192
    assert result.english["mastering"] is False
    assert result.english["lowpass_hz"] == 7000
    assert result.french["pause_ms"] == 500
    assert result.french["mastering"] is False
    assert result.french["lowpass_hz"] is None


@pytest.mark.asyncio
async def test_daily_french_proceeds_when_voice_catalog_lookup_fails(tmp_path: Path):
    """DNS/catalog failure must not abort French as UNAVAILABLE."""
    job = _original_job(base_exports=tmp_path)
    edge_calls: list[str] = []

    class FakeEdge:
        id = "edge"

        async def health_check(self):
            return False, "UNAVAILABLE (getaddrinfo failed)"

        async def synthesize(self, request, **kwargs):
            edge_calls.append(request.voice)
            path = Path(request.output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"ID3" + b"\x00" * 128)
            return SynthResult(success=True, output_path=str(path), provider="edge")

    class FakePiper:
        id = "piper"

        async def health_check(self):
            return True, "READY"

        async def synthesize(self, request, **kwargs):
            raise AssertionError("piper must not be called")

    def fake_get_provider(pid: str):
        if pid == "edge":
            return FakeEdge()
        if pid == "piper":
            return FakePiper()
        raise AssertionError(pid)

    async def fake_verify(voices):
        from bmt_voice_studio.providers.voice_verify import VoiceCheckResult

        return [
            VoiceCheckResult(
                voice=v,
                configured=v,
                available=True,
                actual=v,
                catalog_error="[Errno 11001] getaddrinfo failed",
            )
            for v in voices
        ]

    with (
        patch("bmt_voice_studio.daily.pipeline.get_provider", side_effect=fake_get_provider),
        patch("bmt_voice_studio.daily.pipeline.verify_required_voices", side_effect=fake_verify),
        patch("bmt_voice_studio.daily.pipeline.validate_audio_magic", return_value=(True, "mp3")),
        patch("bmt_voice_studio.daily.pipeline.join_segments"),
        patch("bmt_voice_studio.daily.pipeline.export_original_pipeline") as exp,
        patch("bmt_voice_studio.daily.pipeline._probe", return_value={"duration_sec": 1.0, "bitrate_kbps": 192, "sample_rate": 44100, "channels": "mono", "codec": "mp3"}),
        patch("bmt_voice_studio.daily.pipeline._loudness", return_value={}),
        patch("bmt_voice_studio.daily.pipeline.FFmpegService") as ff_cls,
    ):
        ff = MagicMock()
        ff.health_check.return_value = (True, "ok")
        ff_cls.return_value = ff
        exp.side_effect = lambda *a, **k: {}
        result = await run_daily_job(job)

    assert "fr-FR-HenriNeural" in edge_calls
    assert "fr-FR-DeniseNeural" in edge_calls
    assert result.french is not None
    assert result.french.get("ok") is True
    assert not any("UNAVAILABLE" in err for err in (result.errors or []))
