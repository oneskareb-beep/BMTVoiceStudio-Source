"""TTS provider abstraction."""

from __future__ import annotations

import abc
from typing import Callable

from bmt_voice_studio.core.models import SynthRequest, SynthResult, VoiceInfo

ProgressCallback = Callable[[str], None]
CancelCheck = Callable[[], bool]


class TTSProviderError(Exception):
    """Human-readable provider failure."""

    def __init__(self, message: str, *, technical: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.technical = technical or message


class BaseTTSProvider(abc.ABC):
    id: str = "base"
    display_name: str = "Base Provider"
    requires_network: bool = False

    @abc.abstractmethod
    async def synthesize(
        self,
        request: SynthRequest,
        *,
        cancel_check: CancelCheck | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> SynthResult:
        raise NotImplementedError

    @abc.abstractmethod
    async def list_voices(self) -> list[VoiceInfo]:
        raise NotImplementedError

    @abc.abstractmethod
    async def health_check(self) -> tuple[bool, str]:
        """Return (ok, message). Must not send user content."""
        raise NotImplementedError

    async def preview(
        self,
        voice: str,
        text: str = "This is a short voice preview.",
        *,
        rate: str = "+0%",
        pitch: str = "+0Hz",
        volume: str = "+0%",
        output_path: str = "",
    ) -> SynthResult:
        return await self.synthesize(
            SynthRequest(
                text=text,
                voice=voice,
                rate=rate,
                pitch=pitch,
                volume=volume,
                output_path=output_path,
            )
        )
