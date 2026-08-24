"""User-facing render speed → FFmpeg x264 settings. No jargon in the UI."""

from __future__ import annotations

RENDER_SPEED_STANDARD = "standard"
RENDER_SPEED_FASTER = "faster"

SPEED_LABELS = {
    RENDER_SPEED_STANDARD: "Standard",
    RENDER_SPEED_FASTER: "Faster",
}


def normalize_render_speed(value: str | None) -> str:
    raw = (value or RENDER_SPEED_STANDARD).strip().lower()
    if raw in {"faster", "fast"}:
        return RENDER_SPEED_FASTER
    return RENDER_SPEED_STANDARD


def ffmpeg_x264_preset(speed: str | None, *, preview: bool = False, width: int = 1080) -> str:
    """Map Standard/Faster to an x264 preset. Preview always prefers speed."""
    if preview or width < 800:
        return "veryfast"
    if normalize_render_speed(speed) == RENDER_SPEED_FASTER:
        return "veryfast"
    return "medium"


def ffmpeg_crf_for(base_crf: int, speed: str | None) -> int:
    crf = int(base_crf or 20)
    if normalize_render_speed(speed) == RENDER_SPEED_FASTER:
        return min(28, crf + 2)
    return crf
