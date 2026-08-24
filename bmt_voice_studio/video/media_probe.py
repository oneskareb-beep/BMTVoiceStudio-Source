"""Probe images, videos, and audio without crashing on bad files."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from bmt_voice_studio.audio.ffmpeg_service import FFmpegError, FFmpegService
from bmt_voice_studio.video.errors import MediaValidationError
from bmt_voice_studio.video.models import (
    AUDIO_EXTENSIONS,
    IMAGE_EXTENSIONS,
    VIDEO_EXTENSIONS,
    MediaItem,
    MediaType,
)
from bmt_voice_studio.video.rotation import display_size, parse_ffmpeg_rotation

_DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")
_VIDEO_STREAM_RE = re.compile(
    r"Stream #.*Video:.*?\b(\d{2,5})x(\d{2,5})\b",
    re.IGNORECASE,
)
_AUDIO_STREAM_RE = re.compile(r"Stream #.*Audio:", re.IGNORECASE)


def parse_ffmpeg_duration(text: str) -> float:
    m = _DURATION_RE.search(text or "")
    if not m:
        return 0.0
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


def parse_ffmpeg_video_size(text: str) -> tuple[int, int]:
    m = _VIDEO_STREAM_RE.search(text or "")
    if not m:
        return 0, 0
    return int(m.group(1)), int(m.group(2))


def _ffmpeg_identify(path: Path, ffmpeg: FFmpegService | None = None) -> str:
    ff = ffmpeg or FFmpegService()
    result = ff.run(["-hide_banner", "-i", str(path)], check=False, timeout=30)
    return (result.stderr or "") + (result.stdout or "")


def probe_audio_duration(path: Path | str, ffmpeg: FFmpegService | None = None) -> float:
    p = Path(path)
    if not p.is_file():
        raise MediaValidationError("The selected audio file is missing.")
    if p.suffix.lower() not in AUDIO_EXTENSIONS:
        raise MediaValidationError("Audio must be an MP3 or WAV file.")
    try:
        from mutagen import File as mutagen_file

        meta = mutagen_file(str(p))
        if meta is not None and getattr(meta, "info", None) is not None:
            dur = float(getattr(meta.info, "length", 0.0) or 0.0)
            if dur > 0:
                return dur
    except Exception:
        pass
    try:
        blob = _ffmpeg_identify(p, ffmpeg)
    except FFmpegError as exc:
        raise MediaValidationError("The selected audio file could not be read.") from exc
    dur = parse_ffmpeg_duration(blob)
    if dur <= 0:
        raise MediaValidationError("The selected audio file could not be read.")
    return dur


def probe_image(path: Path | str) -> dict[str, Any]:
    p = Path(path)
    if not p.is_file():
        raise MediaValidationError("That photo is missing and cannot be added.")
    if p.suffix.lower() not in IMAGE_EXTENSIONS:
        raise MediaValidationError("That file is not a supported photo format.")
    try:
        from bmt_voice_studio.video.image_io import image_has_transparency, open_rgba

        im = open_rgba(p)
        width, height = im.size
        if width < 8 or height < 8:
            raise MediaValidationError("That image is too small to use in a video.")
        fmt = (getattr(im, "format", None) or p.suffix.lstrip(".")).lower()
        return {
            "path": str(p.resolve()),
            "media_type": MediaType.IMAGE.value,
            "width": int(width),
            "height": int(height),
            "duration": 0.0,
            "format": fmt,
            "has_alpha": image_has_transparency(im),
        }
    except MediaValidationError:
        raise
    except Exception as exc:
        raise MediaValidationError("That photo could not be opened. Choose another image.") from exc


def probe_video(path: Path | str, ffmpeg: FFmpegService | None = None) -> dict[str, Any]:
    p = Path(path)
    if not p.is_file():
        raise MediaValidationError("That video clip is missing and cannot be added.")
    if p.suffix.lower() not in VIDEO_EXTENSIONS:
        raise MediaValidationError("That file is not a supported video format.")
    try:
        blob = _ffmpeg_identify(p, ffmpeg)
    except FFmpegError as exc:
        raise MediaValidationError("That video clip could not be read.") from exc
    if "Invalid data" in blob or "Error opening" in blob:
        raise MediaValidationError("That video clip could not be read.")
    width, height = parse_ffmpeg_video_size(blob)
    rotation = parse_ffmpeg_rotation(blob)
    width, height = display_size(width, height, rotation)
    duration = parse_ffmpeg_duration(blob)
    if width <= 0 or height <= 0:
        raise MediaValidationError("That video clip could not be read.")
    if duration <= 0.05:
        raise MediaValidationError("That video clip is too short to use.")
    return {
        "path": str(p.resolve()),
        "media_type": MediaType.VIDEO.value,
        "width": width,
        "height": height,
        "duration": duration,
        "rotation": rotation,
        "has_audio": bool(_AUDIO_STREAM_RE.search(blob)),
    }


def probe_media(path: Path | str, ffmpeg: FFmpegService | None = None) -> MediaItem:
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix in IMAGE_EXTENSIONS:
        info = probe_image(p)
    elif suffix in VIDEO_EXTENSIONS:
        info = probe_video(p, ffmpeg)
    else:
        raise MediaValidationError("That file is not a supported photo or video format.")
    return MediaItem(
        path=info["path"],
        media_type=info["media_type"],
        duration=float(info.get("duration") or 0.0),
        width=int(info.get("width") or 0),
        height=int(info.get("height") or 0),
        rotation=int(info.get("rotation") or 0),
        missing=False,
        error="",
        has_alpha=bool(info.get("has_alpha")),
        overlay=bool(info.get("has_alpha")),
    )


def refresh_display_geometry(item: MediaItem, ffmpeg: FFmpegService | None = None) -> MediaItem:
    """Re-read display size/rotation for video clips (upgrades older saved projects)."""
    if item is None or item.media_type != MediaType.VIDEO.value or not item.exists():
        return item
    try:
        info = probe_video(item.path, ffmpeg)
        item.width = int(info.get("width") or item.width or 0)
        item.height = int(info.get("height") or item.height or 0)
        item.rotation = int(info.get("rotation") or 0)
        dur = float(info.get("duration") or 0.0)
        if dur > 0.05:
            item.duration = dur
    except Exception:
        pass
    return item


def classify_media_path(path: Path | str) -> str | None:
    suffix = Path(path).suffix.lower()
    if suffix in IMAGE_EXTENSIONS:
        return MediaType.IMAGE.value
    if suffix in VIDEO_EXTENSIONS:
        return MediaType.VIDEO.value
    return None
