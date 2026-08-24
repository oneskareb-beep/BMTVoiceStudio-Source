"""Domain models for segments, voices, and generation results."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class Speaker(str, Enum):
    MALE = "male"
    FEMALE = "female"


class ProviderId(str, Enum):
    EDGE = "edge"
    PIPER = "piper"


@dataclass
class Segment:
    index: int
    speaker: Speaker
    text: str
    enabled: bool = True
    voice: str = ""
    rate: str = ""
    pitch: str = ""
    volume: str = ""
    provider: str = "edge"
    audio_path: str = ""
    cache_hash: str = ""
    error: str = ""

    @property
    def label(self) -> str:
        return f"{self.index:02d} {self.speaker.value.upper()}"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["speaker"] = self.speaker.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Segment":
        return cls(
            index=int(data["index"]),
            speaker=Speaker(data["speaker"]),
            text=data.get("text", ""),
            enabled=bool(data.get("enabled", True)),
            voice=data.get("voice", ""),
            rate=data.get("rate", ""),
            pitch=data.get("pitch", ""),
            volume=data.get("volume", ""),
            provider=data.get("provider", "edge"),
            audio_path=data.get("audio_path", ""),
            cache_hash=data.get("cache_hash", ""),
            error=data.get("error", ""),
        )


@dataclass
class ParseError:
    message: str
    line: int | None = None
    column: int | None = None
    severity: str = "error"


@dataclass
class ParseResult:
    segments: list[Segment] = field(default_factory=list)
    errors: list[ParseError] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(e.severity == "error" for e in self.errors)


@dataclass
class VoiceInfo:
    id: str
    name: str
    locale: str
    gender: str
    provider: str
    language: str = ""
    sample_rate: int | None = None
    quality: str = ""
    size_bytes: int | None = None
    license: str = ""
    model_path: str = ""
    installed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SynthRequest:
    text: str
    voice: str
    rate: str = "+0%"
    pitch: str = "+0Hz"
    volume: str = "+0%"
    output_path: str = ""


@dataclass
class SynthResult:
    success: bool
    output_path: str = ""
    error: str = ""
    provider: str = ""
    cancelled: bool = False
    # Edge WordBoundary clocks (seconds) — used to sync video captions to the spoken voice.
    timings: list = field(default_factory=list)


@dataclass
class PlaylistItem:
    index: int
    source: str
    title: str = ""
    duration: float | None = None
    local_path: str = ""
    enabled: bool = True
    is_hls: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PlaylistItem":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})  # type: ignore[attr-defined]
