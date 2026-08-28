"""Built-in BMT voice presets — loaded from canonical source_pipeline_presets.json."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from bmt_voice_studio.config.french_tts import remap_french_preset
from bmt_voice_studio.config.swahili_tts import remap_swahili_preset
from bmt_voice_studio.config.pipeline_config import PipelineSettings

_CONFIG_PATH = Path(__file__).with_name("source_pipeline_presets.json")


@dataclass
class VoicePreset:
    id: str
    name: str
    language: str
    male_voice: str
    female_voice: str
    rate: str = "+0%"
    pitch: str = "+0Hz"
    volume: str = "+0%"
    provider: str = "edge"
    ui_hint: str = ""
    pipeline: PipelineSettings = field(default_factory=PipelineSettings)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["pipeline"] = self.pipeline.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VoicePreset":
        return cls(
            id=data["id"],
            name=data["name"],
            language=data.get("language", "en"),
            male_voice=data["male_voice"],
            female_voice=data["female_voice"],
            rate=data.get("rate", "+0%"),
            pitch=data.get("pitch", "+0Hz"),
            volume=data.get("volume", "+0%"),
            provider=data.get("provider", "edge"),
            ui_hint=data.get("ui_hint", ""),
            pipeline=PipelineSettings.from_dict(data.get("pipeline")),
        )

    @property
    def is_reference_locked(self) -> bool:
        """BMT English/French use locked reference pipeline settings."""
        return self.id in ("bmt_english", "bmt_french")


def _load_presets() -> dict[str, VoicePreset]:
    raw = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    out: dict[str, VoicePreset] = {}
    for preset_id, entry in raw.get("presets", {}).items():
        out[preset_id] = remap_swahili_preset(remap_french_preset(VoicePreset.from_dict(entry)))
    return out


BUILTIN_PRESETS: dict[str, VoicePreset] = _load_presets()

BMT_ENGLISH = BUILTIN_PRESETS["bmt_english"]
BMT_FRENCH = BUILTIN_PRESETS["bmt_french"]
BMT_SWAHILI = BUILTIN_PRESETS["bmt_swahili"]
BMT_PORTUGUESE = BUILTIN_PRESETS["bmt_portuguese"]


def list_presets() -> list[VoicePreset]:
    return list(BUILTIN_PRESETS.values())


def get_preset(preset_id: str) -> VoicePreset | None:
    return BUILTIN_PRESETS.get(preset_id)


def reload_presets() -> None:
    global BUILTIN_PRESETS, BMT_ENGLISH, BMT_FRENCH, BMT_SWAHILI, BMT_PORTUGUESE
    BUILTIN_PRESETS = _load_presets()
    BMT_ENGLISH = BUILTIN_PRESETS["bmt_english"]
    BMT_FRENCH = BUILTIN_PRESETS["bmt_french"]
    BMT_SWAHILI = BUILTIN_PRESETS["bmt_swahili"]
    BMT_PORTUGUESE = BUILTIN_PRESETS["bmt_portuguese"]
