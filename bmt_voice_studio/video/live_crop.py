"""Lightweight still preview using the same crop model as FFmpeg."""

from __future__ import annotations

from pathlib import Path

from bmt_voice_studio.video.geometry import positioned_crop_rect
from bmt_voice_studio.video.image_io import DEFAULT_PAD_RGB, composite_media_frame
from bmt_voice_studio.video.models import FitMode, MediaItem


def crop_preview_rect(
    src_w: int,
    src_h: int,
    dst_w: int,
    dst_h: int,
    crop_x: float,
    crop_y: float,
    zoom: float,
    fit_mode: str = FitMode.FILL.value,
) -> tuple[int, int, int, int]:
    """Return source crop rect. FIT/BAND use the full frame (letterbox handled by compositor)."""
    mode = (fit_mode or "").lower()
    if mode in {FitMode.FIT.value, FitMode.BAND.value}:
        return 0, 0, max(1, src_w), max(1, src_h)
    return positioned_crop_rect(src_w, src_h, dst_w, dst_h, crop_x, crop_y, zoom)


def _frame_source_item(item: MediaItem) -> MediaItem | None:
    """Photos as-is; videos via a cached still so live preview can show them."""
    if item is None or not item.exists():
        return None
    if item.media_type == "image":
        return item
    if item.media_type == "video":
        try:
            from dataclasses import replace

            from bmt_voice_studio.video.thumbs import extract_thumbnail

            thumb = extract_thumbnail(
                item.path,
                media_type=item.media_type,
                rotation=int(getattr(item, "rotation", 0) or 0),
                square=False,
            )
            if thumb and Path(thumb).is_file():
                return replace(item, path=str(thumb), media_type="image", rotation=0)
        except Exception:
            return None
    return None


def render_live_crop_still(
    item: MediaItem,
    dest: Path,
    *,
    width: int = 270,
    height: int = 480,
    background: tuple[int, int, int] = DEFAULT_PAD_RGB,
    underlay: MediaItem | None = None,
) -> Path | None:
    source = _frame_source_item(item)
    if source is None:
        return None
    try:
        from PIL import Image

        keep = bool(getattr(item, "overlay", False)) and item.media_type == "image"
        frame = composite_media_frame(source, width, height, background, keep_alpha=keep)
        bed = _frame_source_item(underlay) if keep else None
        if keep and bed is not None:
            base = composite_media_frame(bed, width, height, background, keep_alpha=False)
            base.alpha_composite(frame)
            frame = base
        elif keep:
            canvas = Image.new("RGBA", frame.size, (*background, 255))
            canvas.alpha_composite(frame)
            frame = canvas
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest = Path(dest).with_suffix(".png")
        frame.convert("RGB").save(dest, "PNG")
        return dest
    except Exception:
        return None


def _still_underlay(item: MediaItem | None) -> MediaItem | None:
    return _frame_source_item(item)


def drag_delta_to_crop(dx: float, dy: float, widget_w: int, widget_h: int) -> tuple[float, float]:
    """Map pixel drag to normalized crop deltas (right/down positive)."""
    w = max(1.0, float(widget_w))
    h = max(1.0, float(widget_h))
    return max(-1.0, min(1.0, 2.0 * dx / w)), max(-1.0, min(1.0, 2.0 * dy / h))


def click_offset_to_crop(px: float, py: float, widget_w: int, widget_h: int) -> tuple[float, float]:
    """Normalized offset from preview center for click-to-center."""
    w = max(1.0, float(widget_w))
    h = max(1.0, float(widget_h))
    nx = max(-1.0, min(1.0, (2.0 * float(px) / w) - 1.0))
    ny = max(-1.0, min(1.0, (2.0 * float(py) / h) - 1.0))
    return nx, ny
