"""Typed Video Maker project and composition models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class MediaType(str, Enum):
    IMAGE = "image"
    VIDEO = "video"


class FitMode(str, Enum):
    AUTO = "auto"
    FIT = "fit"
    FILL = "fill"
    # Middle 50% band (1/4 top + 2/4 image + 1/4 bottom) — Sylvestre paysage layout.
    BAND = "band"


class AnimationMode(str, Enum):
    AUTO = "auto"
    ZOOM_IN = "zoom_in"
    ZOOM_OUT = "zoom_out"
    PAN_LR = "pan_lr"
    PAN_RL = "pan_rl"
    STATIC = "static"


class SceneKind(str, Enum):
    INTRO = "intro"
    PHOTO = "photo"
    VIDEO = "video"
    OUTRO = "outro"


TEMPLATE_BMT_CLASSIC = "bmt_classic"
TEMPLATE_BMT_NATURE = "bmt_nature"
TEMPLATE_BMT_MINIMAL = "bmt_minimal"
TEMPLATE_LABELS = {
    TEMPLATE_BMT_CLASSIC: "BMT CLASSIC",
    TEMPLATE_BMT_NATURE: "BMT NATURE",
    TEMPLATE_BMT_MINIMAL: "BMT MINIMAL",
}

PROFILE_STANDARD = "standard_1080p"
PROFILE_WHATSAPP = "whatsapp"
PROFILE_PREVIEW = "preview_540"

CANVAS_WIDTH = 1080
CANVAS_HEIGHT = 1920
CANVAS_FPS = 30
PREVIEW_WIDTH = 540
PREVIEW_HEIGHT = 960
PREVIEW_DURATION = 12.0

ZOOM_MIN = 0.15
ZOOM_MAX = 2.5
CROP_MIN = -1.0
CROP_MAX = 1.0

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".avi", ".mkv"}
AUDIO_EXTENSIONS = {".mp3", ".wav"}

LANGUAGE_FOLDERS = {
    "en": "ENGLISH",
    "fr": "FRENCH",
    "sw": "SWAHILI",
    "pt": "PORTUGUESE",
}

LANGUAGE_LABELS = {
    "en": "English",
    "fr": "French",
    "sw": "Swahili",
    "pt": "Portuguese",
}

# Sylvestre shorthand codes for meditation paysage stills and exports.
LANGUAGE_STILL_CODES = {
    "en": "eng",
    "fr": "fra",
    "pt": "port",
    "eng": "eng",
    "fra": "fra",
    "port": "port",
    "portuguese": "port",
    "french": "fra",
    "english": "eng",
}


def normalize_language_id(language: str | None) -> str:
    """Map eng/fra/port (and folder names) onto en/fr/pt/sw."""
    raw = (language or "en").strip().lower()
    aliases = {
        "eng": "en",
        "english": "en",
        "fra": "fr",
        "french": "fr",
        "port": "pt",
        "por": "pt",
        "portuguese": "pt",
        "swa": "sw",
        "swahili": "sw",
    }
    if raw in LANGUAGE_FOLDERS:
        return raw
    if raw in aliases:
        return aliases[raw]
    folder = language_folder(raw)
    return language_id_from_folder(folder)


def language_still_code(language: str | None) -> str:
    """eng / fra / port codes for paysage still filenames."""
    lid = normalize_language_id(language)
    return LANGUAGE_STILL_CODES.get(lid, lid)


def language_folder(language: str) -> str:
    key = (language or "en").strip().lower()
    if key in LANGUAGE_FOLDERS:
        return LANGUAGE_FOLDERS[key]
    raw = (language or "").strip().upper()
    if raw in LANGUAGE_FOLDERS.values():
        return raw
    return "ENGLISH"


def language_id_from_folder(folder: str) -> str:
    raw = (folder or "").strip().upper()
    for lid, name in LANGUAGE_FOLDERS.items():
        if name == raw:
            return lid
    return "en"


@dataclass
class BrandingToggles:
    logo: bool = True
    date: bool = True
    topic: bool = True
    week_focus: bool = True
    month_theme: bool = True
    lower_third_topic: bool = True
    lower_third_date: bool = True
    captions: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "BrandingToggles":
        data = data or {}
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: bool(v) for k, v in data.items() if k in known})


FONT_SIZE_MIN = 28
FONT_SIZE_MAX = 120
FONT_SIZE_DEFAULT = 64
STROKE_WIDTH_MIN = 0
STROKE_WIDTH_MAX = 16
STROKE_WIDTH_DEFAULT = 5
TEXT_COLOR_DEFAULT = "#E89430"
STROKE_COLOR_DEFAULT = "#0A204A"


def _clamp_int(value: Any, lo: int, hi: int, default: int) -> int:
    try:
        return max(lo, min(hi, int(value)))
    except (TypeError, ValueError):
        return default


def normalize_hex_color(value: str | None, default: str) -> str:
    raw = str(value or "").strip().lstrip("#")
    if len(raw) == 3 and all(c in "0123456789abcdefABCDEF" for c in raw):
        raw = "".join(c * 2 for c in raw)
    if len(raw) == 6 and all(c in "0123456789abcdefABCDEF" for c in raw):
        return f"#{raw.upper()}"
    return default


def hex_to_rgb(value: str | None, default: tuple[int, int, int] = (255, 255, 255)) -> tuple[int, int, int]:
    hex_color = normalize_hex_color(value, "")
    if not hex_color:
        return default
    raw = hex_color[1:]
    return int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)


@dataclass
class TextStyle:
    """On-screen caption and overlay type: color, stroke, size."""

    font_size: int = FONT_SIZE_DEFAULT
    text_color: str = TEXT_COLOR_DEFAULT
    stroke_color: str = STROKE_COLOR_DEFAULT
    stroke_width: int = STROKE_WIDTH_DEFAULT

    def normalized(self) -> "TextStyle":
        return TextStyle(
            font_size=_clamp_int(self.font_size, FONT_SIZE_MIN, FONT_SIZE_MAX, FONT_SIZE_DEFAULT),
            text_color=normalize_hex_color(self.text_color, TEXT_COLOR_DEFAULT),
            stroke_color=normalize_hex_color(self.stroke_color, STROKE_COLOR_DEFAULT),
            stroke_width=_clamp_int(self.stroke_width, STROKE_WIDTH_MIN, STROKE_WIDTH_MAX, STROKE_WIDTH_DEFAULT),
        )

    def migrate_legacy(self) -> "TextStyle":
        """Upgrade saved white/black thin-stroke presets to BMT orange fill + navy outline."""
        style = self.normalized()
        text = style.text_color.upper()
        stroke = style.stroke_color.upper()
        white_fill = text in {"#FFFFFF", "#FFF"}
        black_stroke = stroke in {"#000000", "#000"}
        thin_stroke = style.stroke_width <= 2
        if white_fill and black_stroke:
            return TextStyle(
                font_size=style.font_size,
                text_color=TEXT_COLOR_DEFAULT,
                stroke_color=STROKE_COLOR_DEFAULT,
                stroke_width=STROKE_WIDTH_DEFAULT,
            ).normalized()
        if white_fill and thin_stroke:
            return TextStyle(
                font_size=style.font_size,
                text_color=TEXT_COLOR_DEFAULT,
                stroke_color=style.stroke_color,
                stroke_width=STROKE_WIDTH_DEFAULT,
            ).normalized()
        if black_stroke:
            return TextStyle(
                font_size=style.font_size,
                text_color=style.text_color,
                stroke_color=STROKE_COLOR_DEFAULT,
                stroke_width=STROKE_WIDTH_DEFAULT if thin_stroke else style.stroke_width,
            ).normalized()
        if thin_stroke:
            return TextStyle(
                font_size=style.font_size,
                text_color=style.text_color,
                stroke_color=style.stroke_color,
                stroke_width=STROKE_WIDTH_DEFAULT,
            ).normalized()
        return style

    def to_dict(self) -> dict[str, Any]:
        return asdict(self.normalized())

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "TextStyle":
        data = data or {}
        return cls(
            font_size=data.get("font_size", FONT_SIZE_DEFAULT),
            text_color=str(data.get("text_color") or TEXT_COLOR_DEFAULT),
            stroke_color=str(data.get("stroke_color") or STROKE_COLOR_DEFAULT),
            stroke_width=data.get("stroke_width", STROKE_WIDTH_DEFAULT),
        ).normalized().migrate_legacy()


def output_profile_for(profile_id: str) -> "OutputProfile":
    pid = (profile_id or PROFILE_STANDARD).strip().lower()
    if pid in {"whatsapp", "whatsapp_optimized", PROFILE_WHATSAPP}:
        return OutputProfile(
            id=PROFILE_WHATSAPP,
            label="WhatsApp Optimized",
            width=CANVAS_WIDTH,
            height=CANVAS_HEIGHT,
            fps=CANVAS_FPS,
            video_crf=26,
            audio_bitrate_k=128,
            audio_sample_rate=48000,
        )
    if pid in {"preview", PROFILE_PREVIEW}:
        return OutputProfile(
            id=PROFILE_PREVIEW,
            label="12-second preview",
            width=PREVIEW_WIDTH,
            height=PREVIEW_HEIGHT,
            fps=CANVAS_FPS,
            video_crf=28,
            audio_bitrate_k=96,
            audio_sample_rate=44100,
        )
    return OutputProfile()


@dataclass
class OutputProfile:
    id: str = "standard_1080p"
    label: str = "Standard 1080p"
    width: int = CANVAS_WIDTH
    height: int = CANVAS_HEIGHT
    fps: int = CANVAS_FPS
    video_crf: int = 20
    audio_bitrate_k: int = 192
    audio_sample_rate: int = 48000
    pixel_format: str = "yuv420p"
    video_codec: str = "libx264"
    audio_codec: str = "aac"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "OutputProfile":
        data = data or {}
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)


@dataclass
class MediaItem:
    path: str = ""
    media_type: str = MediaType.IMAGE.value
    duration: float = 0.0
    order: int = 0
    fit_mode: str = FitMode.FILL.value
    animation_mode: str = AnimationMode.AUTO.value
    width: int = 0
    height: int = 0
    rotation: int = 0
    missing: bool = False
    error: str = ""
    crop_x: float = 0.0
    crop_y: float = 0.0
    zoom: float = 1.0
    trim_start: float = 0.0
    trim_end: float = 0.0
    has_alpha: bool = False
    overlay: bool = False

    def resolved_path(self) -> Path:
        return Path(self.path)

    def exists(self) -> bool:
        try:
            return bool(self.path) and Path(self.path).is_file()
        except Exception:
            return False

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("missing", None)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MediaItem":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        filtered = {k: v for k, v in (data or {}).items() if k in known}
        item = cls(**filtered)
        from bmt_voice_studio.video.geometry import clamp_crop, clamp_trim, clamp_zoom

        item.crop_x, item.crop_y = clamp_crop(item.crop_x, item.crop_y)
        item.zoom = clamp_zoom(item.zoom)
        item.trim_start, item.trim_end = clamp_trim(item.trim_start, item.trim_end, item.duration)
        try:
            item.rotation = int(item.rotation or 0) % 360
            if item.rotation not in {0, 90, 180, 270}:
                from bmt_voice_studio.video.rotation import normalize_rotation_degrees

                item.rotation = normalize_rotation_degrees(item.rotation)
        except (TypeError, ValueError):
            item.rotation = 0
        item.missing = not item.exists()
        if item.has_alpha and "overlay" not in (data or {}):
            item.overlay = True
        return item


@dataclass
class LanguageTrack:
    """Per-language audio + metadata bound to a shared visual project."""

    language: str = "en"
    audio_path: str = ""
    audio_duration: float = 0.0
    topic: str = ""
    week_focus: str = ""
    month_theme: str = ""
    title: str = ""
    memory_verse: str = ""
    selected: bool = False
    metadata_complete: bool = False
    ready: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "LanguageTrack":
        data = data or {}
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        filtered = {k: v for k, v in data.items() if k in known}
        track = cls(**filtered)
        track.language = (track.language or "en").strip().lower()
        track.metadata_complete = bool(track.topic.strip())
        try:
            track.ready = bool(track.audio_path) and Path(track.audio_path).is_file()
        except Exception:
            track.ready = False
        return track


QUEUE_WAITING = "Waiting"
QUEUE_PREPARING = "Preparing"
QUEUE_RENDERING = "Rendering"
QUEUE_FINALIZING = "Finalizing"
QUEUE_COMPLETE = "Complete"
QUEUE_FAILED = "Failed"
QUEUE_CANCELLED = "Cancelled"


@dataclass
class VideoProject:
    schema_version: int = 5
    template_id: str = TEMPLATE_BMT_CLASSIC
    devotional_date: str = ""  # YYYY-MM-DD
    language: str = "en"
    audio_path: str = ""
    audio_duration: float = 0.0
    topic: str = ""
    week_focus: str = ""
    month_theme: str = ""
    title: str = ""
    memory_verse: str = ""
    logo_path: str = ""
    media_items: list[MediaItem] = field(default_factory=list)
    branding: BrandingToggles = field(default_factory=BrandingToggles)
    output_profile: OutputProfile = field(default_factory=OutputProfile)
    intro_enabled: bool = True
    outro_enabled: bool = True
    intro_duration: float = 10.0
    outro_duration: float = 10.0
    music_path: str = ""
    music_intro_start: float = 0.0
    music_outro_start: float = -1.0
    crossfade_seconds: float = 0.75
    intro_audio_overlap: float = 0.0  # speech starts after branded intro
    languages: list[LanguageTrack] = field(default_factory=list)
    selected_languages: list[str] = field(default_factory=list)
    show_captions: bool = False
    skip_caption_header: bool = True
    caption_content: str = "body_verse"
    text_style: TextStyle = field(default_factory=TextStyle)
    render_speed: str = "standard"
    preview_start: float = 0.0
    preview_duration: float = PREVIEW_DURATION

    def ordered_media(self) -> list[MediaItem]:
        return sorted(self.media_items, key=lambda m: m.order)

    def available_media(self) -> list[MediaItem]:
        return [m for m in self.ordered_media() if m.exists()]

    def missing_media(self) -> list[MediaItem]:
        return [m for m in self.ordered_media() if not m.exists()]

    def track_for(self, language: str) -> LanguageTrack | None:
        key = (language or "en").strip().lower()
        for track in self.languages:
            if track.language == key:
                return track
        return None

    def ensure_tracks(self) -> None:
        if self.languages:
            return
        self.languages = [
            LanguageTrack(
                language=self.language or "en",
                audio_path=self.audio_path,
                audio_duration=self.audio_duration,
                topic=self.topic,
                week_focus=self.week_focus,
                month_theme=self.month_theme,
                title=self.title,
                memory_verse=self.memory_verse,
                selected=True,
                metadata_complete=bool((self.topic or "").strip()),
                ready=bool(self.audio_path),
            )
        ]
        if not self.selected_languages:
            self.selected_languages = [self.language or "en"]

    def apply_track(self, language: str) -> None:
        track = self.track_for(language)
        if track is None:
            return
        self.language = track.language
        self.audio_path = track.audio_path
        self.audio_duration = track.audio_duration
        self.topic = track.topic
        self.week_focus = track.week_focus
        self.month_theme = track.month_theme
        self.title = track.title
        self.memory_verse = track.memory_verse

    def bind_language(self, language: str) -> "VideoProject":
        """Clone shared visuals with one language's audio and metadata."""
        from copy import deepcopy

        clone = deepcopy(self)
        clone.apply_track(language)
        clone.selected_languages = [clone.language]
        return clone

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "template_id": self.template_id,
            "devotional_date": self.devotional_date,
            "language": self.language,
            "audio_path": self.audio_path,
            "audio_duration": self.audio_duration,
            "topic": self.topic,
            "week_focus": self.week_focus,
            "month_theme": self.month_theme,
            "title": self.title,
            "memory_verse": self.memory_verse,
            "logo_path": self.logo_path,
            "media_items": [m.to_dict() for m in self.media_items],
            "branding": self.branding.to_dict(),
            "output_profile": self.output_profile.to_dict(),
            "intro_enabled": bool(self.intro_enabled),
            "outro_enabled": bool(self.outro_enabled),
            "intro_duration": self.intro_duration,
            "outro_duration": self.outro_duration,
            "music_path": self.music_path,
            "music_intro_start": float(self.music_intro_start or 0.0),
            "music_outro_start": float(self.music_outro_start if self.music_outro_start is not None else -1.0),
            "crossfade_seconds": self.crossfade_seconds,
            "intro_audio_overlap": self.intro_audio_overlap,
            "languages": [t.to_dict() for t in self.languages],
            "selected_languages": list(self.selected_languages),
            "show_captions": bool(self.show_captions),
            "skip_caption_header": bool(self.skip_caption_header),
            "caption_content": self.caption_content or "body_verse",
            "text_style": (self.text_style or TextStyle()).normalized().to_dict(),
            "render_speed": self.render_speed or "standard",
            "preview_start": float(self.preview_start or 0.0),
            "preview_duration": float(self.preview_duration or PREVIEW_DURATION),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "VideoProject":
        data = data or {}
        items = [MediaItem.from_dict(x) for x in (data.get("media_items") or [])]
        for i, item in enumerate(items):
            item.order = i
        try:
            from bmt_voice_studio.video.media_probe import refresh_display_geometry

            for item in items:
                if item.media_type == MediaType.VIDEO.value:
                    refresh_display_geometry(item)
        except Exception:
            pass
        profile_data = data.get("output_profile")
        if isinstance(profile_data, dict) and profile_data.get("id"):
            profile = output_profile_for(str(profile_data.get("id")))
            profile = OutputProfile.from_dict({**profile.to_dict(), **profile_data})
        else:
            profile = output_profile_for(str(data.get("output_profile_id") or PROFILE_STANDARD))
        template = str(data.get("template_id") or TEMPLATE_BMT_CLASSIC)
        if template not in TEMPLATE_LABELS:
            template = TEMPLATE_BMT_CLASSIC
        from bmt_voice_studio.video.captions import CAPTION_ALL, normalize_caption_mode

        if data.get("caption_content"):
            caption_mode = normalize_caption_mode(str(data.get("caption_content")))
        elif data.get("skip_caption_header") is False:
            caption_mode = CAPTION_ALL
        else:
            caption_mode = normalize_caption_mode(None, skip_header=True)
        skip_caption_header = caption_mode != CAPTION_ALL
        project = cls(
            schema_version=int(data.get("schema_version") or 1),
            template_id=template,
            devotional_date=str(data.get("devotional_date") or ""),
            language=str(data.get("language") or "en"),
            audio_path=str(data.get("audio_path") or ""),
            audio_duration=float(data.get("audio_duration") or 0.0),
            topic=str(data.get("topic") or ""),
            week_focus=str(data.get("week_focus") or ""),
            month_theme=str(data.get("month_theme") or ""),
            title=str(data.get("title") or data.get("topic") or ""),
            memory_verse=str(data.get("memory_verse") or ""),
            logo_path=str(data.get("logo_path") or ""),
            media_items=items,
            branding=BrandingToggles.from_dict(data.get("branding")),
            output_profile=profile,
            intro_enabled=bool(data.get("intro_enabled", True)),
            outro_enabled=bool(data.get("outro_enabled", True)),
            intro_duration=float(data.get("intro_duration") or 10.0),
            outro_duration=float(data.get("outro_duration") or 10.0),
            music_path=str(data.get("music_path") or ""),
            music_intro_start=float(data.get("music_intro_start") or 0.0),
            music_outro_start=float(
                data["music_outro_start"] if data.get("music_outro_start") is not None else -1.0
            ),
            crossfade_seconds=float(data.get("crossfade_seconds") or 0.75),
            intro_audio_overlap=float(data.get("intro_audio_overlap") or 0.0),
            languages=[LanguageTrack.from_dict(x) for x in (data.get("languages") or [])],
            selected_languages=[str(x).lower() for x in (data.get("selected_languages") or []) if str(x).strip()],
            show_captions=bool(data.get("show_captions") or (data.get("branding") or {}).get("captions")),
            skip_caption_header=skip_caption_header,
            caption_content=caption_mode,
            text_style=TextStyle.from_dict(data.get("text_style") if isinstance(data.get("text_style"), dict) else {}),
            render_speed=str(data.get("render_speed") or "standard"),
            preview_start=float(data.get("preview_start") or 0.0),
            preview_duration=float(data.get("preview_duration") or PREVIEW_DURATION),
        )
        project.ensure_tracks()
        if project.branding.captions:
            project.show_captions = True
        return project


@dataclass
class ScenePlan:
    kind: str
    duration: float
    media_path: str = ""
    media_type: str = ""
    fit_mode: str = FitMode.FILL.value
    animation_mode: str = AnimationMode.ZOOM_IN.value
    title_card_path: str = ""
    order: int = 0
    crop_x: float = 0.0
    crop_y: float = 0.0
    zoom: float = 1.0
    trim_start: float = 0.0
    trim_end: float = 0.0
    overlay_path: str = ""
    overlay_zoom: float = 1.0
    overlay_crop_x: float = 0.0
    overlay_crop_y: float = 0.0
    overlay_fit_mode: str = FitMode.FILL.value
    rotation: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CompositionPlan:
    width: int = CANVAS_WIDTH
    height: int = CANVAS_HEIGHT
    fps: int = CANVAS_FPS
    intro_duration: float = 10.0
    outro_duration: float = 10.0
    crossfade_seconds: float = 0.75
    scenes: list[ScenePlan] = field(default_factory=list)
    audio_path: str = ""
    audio_duration: float = 0.0
    total_duration: float = 0.0
    output_path: str = ""
    overlay_path: str = ""
    logo_path: str = ""
    template_id: str = TEMPLATE_BMT_CLASSIC
    job_id: str = ""
    temp_dir: str = ""
    audio_start: float = 0.0
    caption_path: str = ""
    music_path: str = ""
    mixed_audio_path: str = ""

    def total_visual_duration(self) -> float:
        from bmt_voice_studio.video.composition import xfade_output_duration

        return xfade_output_duration([s.duration for s in self.scenes], self.crossfade_seconds)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["scenes"] = [s.to_dict() for s in self.scenes]
        return data
