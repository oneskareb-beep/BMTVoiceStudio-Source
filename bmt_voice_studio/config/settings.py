"""Persistent application settings."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from bmt_voice_studio.config.paths import default_exports_dir, settings_file
from bmt_voice_studio.config.presets import BMT_ENGLISH


@dataclass
class AppSettings:
    default_language: str = "en-NG"
    default_preset: str = BMT_ENGLISH.id
    default_male_voice: str = BMT_ENGLISH.male_voice
    default_female_voice: str = BMT_ENGLISH.female_voice
    default_provider: str = "edge"
    auto_piper_fallback: bool = True
    rate: str = "-10%"
    pitch: str = "-3Hz"
    volume: str = "+0%"
    pause_ms: int = 450
    mp3_bitrate: int = 128
    output_directory: str = ""
    theme: str = "dark"
    network_timeout: float = 60.0
    retry_count: int = 3
    normalize_loudness: bool = True
    target_lufs: float = -16.0
    remove_silence: bool = False
    fade_in_ms: int = 0
    fade_out_ms: int = 120
    peak_limiter: bool = True
    confirm_overwrite: bool = True
    recent_projects: list[str] = field(default_factory=list)
    piper_male_model: str = ""
    piper_female_model: str = ""
    first_run_complete: bool = False
    start_page: str = "daily"  # daily | tts | last
    last_page: str = "daily"
    daily_pause_ms: int = 500
    daily_mastering: bool = False
    daily_export_mp3: bool = True
    daily_export_wav: bool = False
    daily_bitrate: int = 192
    daily_v11_welcome_seen: bool = False
    daily_selected_languages: list[str] = field(default_factory=lambda: ["en", "fr"])
    video_logo_path: str = ""
    video_recent_logos: list[str] = field(default_factory=list)
    video_recent_music: list[str] = field(default_factory=list)
    video_media_overrides: dict[str, list[str]] = field(default_factory=dict)
    caption_font_size: int = 64
    caption_text_color: str = "#E89430"
    caption_stroke_color: str = "#0A204A"
    caption_stroke_width: int = 5
    data_folder_mode: str = "default"  # default | custom
    custom_data_folder: str = ""
    data_library_choice_complete: bool = False
    update_feed_url: str = ""
    product_mode: str = "bmt"

    def __post_init__(self) -> None:
        if not self.output_directory:
            self.output_directory = str(default_exports_dir())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AppSettings":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        filtered = {k: v for k, v in data.items() if k in known}
        if "video_media_overrides" in filtered and not isinstance(filtered.get("video_media_overrides"), dict):
            filtered["video_media_overrides"] = {}
        settings = cls(**filtered)
        text = str(settings.caption_text_color or "").strip().upper()
        stroke = str(settings.caption_stroke_color or "").strip().upper()
        if text in {"#FFFFFF", "#FFF"} and stroke in {"#000000", "#000"}:
            settings.caption_text_color = "#E89430"
            settings.caption_stroke_color = "#0A204A"
            settings.caption_stroke_width = max(int(settings.caption_stroke_width or 0), 5)
        elif text in {"#FFFFFF", "#FFF"} and int(settings.caption_stroke_width or 0) <= 2:
            settings.caption_text_color = "#E89430"
            settings.caption_stroke_width = 5
        elif stroke in {"#000000", "#000"}:
            settings.caption_stroke_color = "#0A204A"
            if int(settings.caption_stroke_width or 0) <= 2:
                settings.caption_stroke_width = 5
        return settings

    def save(self, path: Path | None = None) -> None:
        target = path or settings_file()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path | None = None) -> "AppSettings":
        target = path or settings_file()
        if not target.exists():
            settings = cls()
            settings.save(target)
            return settings
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
            return cls.from_dict(data)
        except Exception:
            return cls()


_settings: AppSettings | None = None


def get_settings() -> AppSettings:
    global _settings
    if _settings is None:
        _settings = AppSettings.load()
    return _settings


def save_settings(settings: AppSettings | None = None) -> None:
    global _settings
    if settings is not None:
        _settings = settings
    get_settings().save()


def reload_settings() -> AppSettings:
    global _settings
    _settings = AppSettings.load()
    return _settings


def remember_recent_path(attr: str, path: str, limit: int = 8) -> list[str]:
    """Move path to the front of a recents list on AppSettings and persist."""
    settings = get_settings()
    cleaned = str(path or "").strip()
    if not cleaned:
        return list(getattr(settings, attr) or [])
    items = [item for item in (getattr(settings, attr) or []) if item and item != cleaned]
    items.insert(0, cleaned)
    items = items[: max(1, int(limit))]
    setattr(settings, attr, items)
    save_settings(settings)
    return items
