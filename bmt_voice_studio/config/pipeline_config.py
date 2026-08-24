"""Canonical BMT reference pipeline configuration — single source of truth."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

ProcessingMode = Literal["original", "enhanced"]

_CONFIG_PATH = Path(__file__).with_name("source_pipeline_presets.json")
_cache: dict[str, Any] | None = None


@dataclass
class PipelineSettings:
    pause_ms: int = 500
    lowpass_hz: int | None = None
    wav_channels: int = 1
    wav_sample_rate: int = 44100
    mp3_bitrate_kbps: int | None = 192
    export_wav: bool = False
    export_mp3: bool = True
    strict_source_mode: bool = True
    default_processing_mode: ProcessingMode = "original"
    allow_piper_fallback: bool = False
    apply_bmt_mastering: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "PipelineSettings":
        if not data:
            return cls()
        return cls(
            pause_ms=int(data.get("pause_ms", 500)),
            lowpass_hz=data.get("lowpass_hz"),
            wav_channels=int(data.get("wav_channels", 1)),
            wav_sample_rate=int(data.get("wav_sample_rate", 44100)),
            mp3_bitrate_kbps=data.get("mp3_bitrate_kbps"),
            export_wav=bool(data.get("export_wav", False)),
            export_mp3=bool(data.get("export_mp3", True)),
            strict_source_mode=bool(data.get("strict_source_mode", True)),
            default_processing_mode=data.get("default_processing_mode", "original"),
            allow_piper_fallback=bool(data.get("allow_piper_fallback", False)),
            apply_bmt_mastering=bool(data.get("apply_bmt_mastering", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "pause_ms": self.pause_ms,
            "lowpass_hz": self.lowpass_hz,
            "wav_channels": self.wav_channels,
            "wav_sample_rate": self.wav_sample_rate,
            "mp3_bitrate_kbps": self.mp3_bitrate_kbps,
            "export_wav": self.export_wav,
            "export_mp3": self.export_mp3,
            "strict_source_mode": self.strict_source_mode,
            "default_processing_mode": self.default_processing_mode,
            "allow_piper_fallback": self.allow_piper_fallback,
            "apply_bmt_mastering": self.apply_bmt_mastering,
        }


def _load_raw() -> dict[str, Any]:
    global _cache
    if _cache is None:
        _cache = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    return _cache


def reload_pipeline_config() -> None:
    global _cache
    _cache = None
    _load_raw()


def config_path() -> Path:
    return _CONFIG_PATH


def get_preset_pipeline(preset_id: str) -> PipelineSettings:
    raw = _load_raw()
    entry = raw.get("presets", {}).get(preset_id, {})
    return PipelineSettings.from_dict(entry.get("pipeline"))


def get_canonical_preset(preset_id: str) -> dict[str, Any]:
    raw = _load_raw()
    entry = raw.get("presets", {}).get(preset_id)
    if not entry:
        raise KeyError(f"Unknown preset: {preset_id}")
    return entry


def list_canonical_preset_ids() -> list[str]:
    return list(_load_raw().get("presets", {}).keys())


@dataclass
class ConfigComparison:
    field: str
    desktop: str
    reference: str
    match: bool


def compare_runtime_to_reference(
    preset_id: str,
    *,
    pause_ms: int,
    mp3_bitrate: int | None,
    processing_mode: ProcessingMode,
    mastering: bool,
    lowpass_hz: int | None = None,
    volume: str | None = None,
    male_voice: str | None = None,
    female_voice: str | None = None,
    rate: str | None = None,
    pitch: str | None = None,
) -> list[ConfigComparison]:
    """Compare active desktop settings against canonical reference preset."""
    entry = get_canonical_preset(preset_id)
    pipe = PipelineSettings.from_dict(entry.get("pipeline"))
    rows: list[ConfigComparison] = []

    def add(field: str, desktop_val: Any, ref_val: Any) -> None:
        ds = str(desktop_val)
        rs = str(ref_val)
        rows.append(ConfigComparison(field=field, desktop=ds, reference=rs, match=ds == rs))

    add("Male voice", male_voice or entry.get("male_voice"), entry.get("male_voice"))
    add("Female voice", female_voice or entry.get("female_voice"), entry.get("female_voice"))
    add("Rate", rate or entry.get("rate"), entry.get("rate"))
    add("Pitch", pitch or entry.get("pitch"), entry.get("pitch"))
    add("Volume", volume or entry.get("volume"), entry.get("volume"))
    add("Pause (ms)", pause_ms, pipe.pause_ms)
    add("Low-pass (Hz)", lowpass_hz if lowpass_hz is not None else pipe.lowpass_hz, pipe.lowpass_hz)
    add("MP3 bitrate (kbps)", mp3_bitrate, pipe.mp3_bitrate_kbps)
    add("Processing mode", processing_mode, pipe.default_processing_mode)
    add("BMT mastering", mastering, pipe.apply_bmt_mastering)
    return rows


def all_settings_match(rows: list[ConfigComparison]) -> bool:
    return all(r.match for r in rows)


def pipeline_lock_summary(preset_id: str) -> str:
    """Human-readable locked pipeline parameters for UI (no person names)."""
    entry = get_canonical_preset(preset_id)
    pipe = PipelineSettings.from_dict(entry.get("pipeline"))
    lines = [
        "PIPELINE LOCKED TO BMT REFERENCE",
        f"Male: {entry.get('male_voice')}",
        f"Female: {entry.get('female_voice')}",
        f"Rate: {entry.get('rate')}",
        f"Pitch: {entry.get('pitch')}",
        f"Volume: {entry.get('volume')}",
        f"Pause: {pipe.pause_ms} ms",
    ]
    if pipe.lowpass_hz:
        lines.append(f"Low-pass: {pipe.lowpass_hz} Hz")
    else:
        lines.append("Low-pass: NONE")
    if pipe.export_wav:
        lines.append(f"WAV: mono {pipe.wav_sample_rate // 1000}.{pipe.wav_sample_rate % 1000} kHz")
    if pipe.mp3_bitrate_kbps:
        lines.append(f"MP3: {pipe.mp3_bitrate_kbps} kbps")
    else:
        lines.append("Export: Original pipeline (MP3, default bitrate)")
    mode = "Original Pipeline" if pipe.default_processing_mode == "original" else "Enhanced Mastering"
    lines.append(f"Processing: {mode}")
    return "\n".join(lines)
