"""Edge TTS (Microsoft neural voices) provider."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from bmt_voice_studio.config.french_tts import remap_french_voice
from bmt_voice_studio.core.models import SynthRequest, SynthResult, VoiceInfo
from bmt_voice_studio.net import prefer_ipv4
from bmt_voice_studio.providers.base import (
    BaseTTSProvider,
    CancelCheck,
    ProgressCallback,
    TTSProviderError,
)
from bmt_voice_studio.providers.edge_ssml import patch_edge_tts_ssml_lang
from bmt_voice_studio.providers.voice_verify import load_edge_catalog

logger = logging.getLogger(__name__)


class EdgeTTSProvider(BaseTTSProvider):
    id = "edge"
    display_name = "Edge TTS (Online Neural)"
    requires_network = True

    def __init__(
        self,
        *,
        timeout: float = 60.0,
        retry_count: int = 3,
        base_backoff: float = 1.0,
    ) -> None:
        self.timeout = timeout
        self.retry_count = max(1, retry_count)
        self.base_backoff = base_backoff

    async def list_voices(self) -> list[VoiceInfo]:
        try:
            raw = await load_edge_catalog()
        except Exception as exc:
            raise TTSProviderError(
                "Could not refresh online voices. Check your internet connection.",
                technical=str(exc),
            ) from exc

        voices: list[VoiceInfo] = []
        for item in raw:
            short = item.get("ShortName") or item.get("Name") or ""
            locale = item.get("Locale") or ""
            gender = (item.get("Gender") or "Unknown").lower()
            lang = locale.split("-")[0] if locale else ""
            voices.append(
                VoiceInfo(
                    id=short,
                    name=short,
                    locale=locale,
                    gender=gender,
                    provider=self.id,
                    language=lang,
                )
            )
        voices.sort(key=lambda v: (v.locale, v.gender, v.name))
        return voices

    async def health_check(self) -> tuple[bool, str]:
        """Lightweight check — list voices only; never send user content."""
        try:
            voices = await load_edge_catalog()
            if voices:
                return True, "AVAILABLE"
            return False, "UNAVAILABLE (empty catalog)"
        except Exception as exc:
            return False, f"UNAVAILABLE ({exc})"

    async def synthesize(
        self,
        request: SynthRequest,
        *,
        cancel_check: CancelCheck | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> SynthResult:
        try:
            import edge_tts
        except ImportError as exc:
            return SynthResult(
                success=False,
                error="Edge TTS library is not installed.",
                provider=self.id,
            )

        try:
            patch_edge_tts_ssml_lang()
        except Exception:
            logger.warning("Could not patch Edge TTS SSML language; using library default.")

        text = (request.text or "").strip()
        if not text:
            return SynthResult(success=False, error="Segment text is empty.", provider=self.id)
        voice = remap_french_voice(request.voice)
        if not voice:
            return SynthResult(success=False, error="No voice selected.", provider=self.id)
        if not request.output_path:
            return SynthResult(success=False, error="No output path provided.", provider=self.id)

        out = Path(request.output_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        last_error = ""
        for attempt in range(1, self.retry_count + 1):
            if cancel_check and cancel_check():
                return SynthResult(success=False, cancelled=True, provider=self.id, error="Cancelled.")

            try:
                if on_progress:
                    on_progress(f"Edge TTS attempt {attempt}/{self.retry_count}…")

                communicate = edge_tts.Communicate(
                    text,
                    voice,
                    rate=request.rate or "+0%",
                    pitch=request.pitch or "+0Hz",
                    volume=request.volume or "+0%",
                    boundary="WordBoundary",
                )

                word_timings: list[dict] = []

                async def _save() -> None:
                    with prefer_ipv4():
                        with open(out, "wb") as audio_f:
                            async for chunk in communicate.stream():
                                kind = chunk.get("type")
                                if kind == "audio":
                                    audio_f.write(chunk["data"])
                                elif kind == "WordBoundary":
                                    # Edge offset/duration are 100-ns ticks.
                                    offset = float(chunk.get("offset") or 0)
                                    duration = float(chunk.get("duration") or 0)
                                    start = offset / 10_000_000.0
                                    end = (offset + duration) / 10_000_000.0
                                    word_timings.append(
                                        {
                                            "text": str(chunk.get("text") or "").strip(),
                                            "start": round(start, 4),
                                            "end": round(max(start + 0.02, end), 4),
                                        }
                                    )

                await asyncio.wait_for(_save(), timeout=self.timeout)

                if not out.exists() or out.stat().st_size < 64:
                    raise TTSProviderError("Edge TTS returned an empty audio file.")

                # Sidecar so cached Daily segments can still drive voice-matched captions.
                try:
                    side = out.with_suffix(".words.json")
                    side.write_text(
                        json.dumps(word_timings, ensure_ascii=False),
                        encoding="utf-8",
                    )
                except Exception:
                    logger.debug("Could not write word-timing sidecar for %s", out, exc_info=True)

                return SynthResult(
                    success=True,
                    output_path=str(out),
                    provider=self.id,
                    timings=word_timings,
                )

            except asyncio.TimeoutError:
                last_error = (
                    "Edge TTS timed out. The speech service may be slow or unreachable."
                )
            except asyncio.CancelledError:
                return SynthResult(success=False, cancelled=True, provider=self.id, error="Cancelled.")
            except Exception as exc:
                detail = str(exc).strip() or type(exc).__name__
                last_error = (
                    f"Could not connect to Edge TTS ({detail}). "
                    "Your internet connection may be unavailable or the speech service "
                    "may be temporarily refusing requests."
                )
                logger.warning("Edge TTS failure attempt %s: %s", attempt, exc)

            if attempt < self.retry_count:
                delay = self.base_backoff * (2 ** (attempt - 1))
                await asyncio.sleep(delay)

        return SynthResult(success=False, error=last_error or "Edge TTS failed.", provider=self.id)
