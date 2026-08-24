"""Video display rotation (WhatsApp / phone clips often store landscape + rotate tag)."""

from __future__ import annotations

import re

_ROTATE_TAG_RE = re.compile(r"^\s*rotate\s*:\s*(-?\d+(?:\.\d+)?)", re.IGNORECASE | re.MULTILINE)
_DISPLAYMATRIX_RE = re.compile(
    r"displaymatrix:\s*rotation of\s*(-?\d+(?:\.\d+)?)\s*degrees",
    re.IGNORECASE,
)


def normalize_rotation_degrees(value: float | int | None) -> int:
    """Map any degree value to 0 / 90 / 180 / 270 (clockwise display correction)."""
    try:
        deg = float(value or 0.0)
    except (TypeError, ValueError):
        return 0
    # Round to nearest quarter-turn.
    turns = int(round(deg / 90.0)) % 4
    return (turns * 90) % 360


def parse_ffmpeg_rotation(text: str) -> int:
    """Return clockwise degrees to apply so the clip displays upright.

    Prefer the classic ``rotate`` tag. Fall back to Side Data displaymatrix, whose
    negative angle means the same upright correction as a positive rotate tag.
    """
    blob = text or ""
    tag = _ROTATE_TAG_RE.search(blob)
    if tag:
        return normalize_rotation_degrees(tag.group(1))
    matrix = _DISPLAYMATRIX_RE.search(blob)
    if matrix:
        # displaymatrix "-90" ≈ rotate tag "90" (both mean upright is 90° CW from coded).
        return normalize_rotation_degrees(-float(matrix.group(1)))
    return 0


def display_size(width: int, height: int, rotation: int = 0) -> tuple[int, int]:
    """Width/height after applying display rotation."""
    w, h = max(0, int(width or 0)), max(0, int(height or 0))
    if normalize_rotation_degrees(rotation) % 180 == 90:
        return h, w
    return w, h


def ffmpeg_autorotate_filter(rotation: int = 0) -> str:
    """Filter fragment that uprights coded frames (empty when already upright)."""
    rot = normalize_rotation_degrees(rotation)
    if rot == 90:
        return "transpose=1"
    if rot == 180:
        return "hflip,vflip"
    if rot == 270:
        return "transpose=2"
    return ""


def prepend_autorotate(vf: str, rotation: int = 0) -> str:
    prefix = ffmpeg_autorotate_filter(rotation)
    if not prefix:
        return vf
    if not vf:
        return prefix
    return f"{prefix},{vf}"
