"""Load photos for Video Maker — EXIF orientation and transparent PNG/GIF/WebP."""

from __future__ import annotations

from pathlib import Path

from bmt_voice_studio.video.geometry import (
    CANVAS_ASPECT,
    clamp_crop,
    clamp_zoom,
    contain_scale,
    cover_scale,
)
from bmt_voice_studio.video.models import FitMode, MediaItem

DEFAULT_PAD_RGB = (15, 20, 28)


def open_rgba(path: Path | str):
    """Open any supported still with orientation applied and an alpha channel."""
    from PIL import Image, ImageOps

    im = Image.open(path)
    try:
        im = ImageOps.exif_transpose(im) or im
    except Exception:
        pass
    if im.mode == "P":
        im = im.convert("RGBA")
    elif im.mode in {"LA", "PA", "RGBa"}:
        im = im.convert("RGBA")
    elif im.mode != "RGBA":
        im = im.convert("RGBA")
    im.load()
    return im


def image_has_transparency(image) -> bool:
    if image is None:
        return False
    if image.mode in {"RGBA", "LA", "PA", "RGBa"}:
        extrema = image.getchannel("A").getextrema() if "A" in image.getbands() else (255, 255)
        return bool(extrema and extrema[0] < 255)
    return "transparency" in getattr(image, "info", {})


def flatten_rgba(image, background: tuple[int, int, int] = DEFAULT_PAD_RGB):
    """Composite transparent pixels onto a solid video-canvas color (never black-fill)."""
    from PIL import Image

    rgba = image.convert("RGBA") if image.mode != "RGBA" else image
    bg = Image.new("RGBA", rgba.size, (*background, 255))
    bg.alpha_composite(rgba)
    return bg.convert("RGB")


def prepare_still_for_encode(
    src: Path | str,
    dest: Path,
    background: tuple[int, int, int] = DEFAULT_PAD_RGB,
) -> Path:
    """Write an opaque, orientation-corrected still when the source has alpha."""
    path = Path(src)
    image = open_rgba(path)
    if not image_has_transparency(image):
        return path
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    flatten_rgba(image, background).save(dest, "PNG")
    return dest


def _paste_offset(canvas: int, content: int, pan: float) -> int:
    slack = content - canvas
    if slack >= 0:
        return -int(round((slack / 2.0) * (1.0 + pan)))
    return int(round(((-slack) / 2.0) * (1.0 + pan)))


def composite_media_frame(
    item: MediaItem,
    width: int,
    height: int,
    background: tuple[int, int, int] = DEFAULT_PAD_RGB,
    *,
    keep_alpha: bool = False,
):
    """9:16 frame matching FFmpeg fit/fill/band + pan/zoom.

    keep_alpha leaves empty/transparent pixels punch-through (alpha 0) so overlays
    stay transparent after zoom, move, or fit.
    """
    from PIL import Image

    photo = open_rgba(item.resolved_path())
    z = clamp_zoom(item.zoom)
    mode = (item.fit_mode or FitMode.FILL.value).lower()
    alpha = 0 if keep_alpha else 255
    canvas = Image.new("RGBA", (width, height), (*background, alpha))

    if mode == FitMode.BAND.value:
        # Middle 2/4 band (1/4 top + 1/4 bottom empty), contain inside the band.
        band_h = max(1, height // 2)
        band_y = max(0, (height - band_h) // 2)
        scale = contain_scale(photo.width, photo.height, width, band_h)
        nw = max(1, int(round(photo.width * scale)))
        nh = max(1, int(round(photo.height * scale)))
        resized = photo.resize((nw, nh), Image.Resampling.LANCZOS)
        dst_x = max(0, (width - nw) // 2)
        dst_y = band_y + max(0, (band_h - nh) // 2)
        canvas.alpha_composite(resized, (dst_x, dst_y))
        return canvas

    fit = mode == FitMode.FIT.value
    scale = (contain_scale if fit else cover_scale)(photo.width, photo.height, width, height) * z
    nw = max(1, int(round(photo.width * scale)))
    nh = max(1, int(round(photo.height * scale)))
    resized = photo.resize((nw, nh), Image.Resampling.LANCZOS)
    ox, oy = clamp_crop(item.crop_x, item.crop_y)
    x = _paste_offset(width, nw, ox)
    y = _paste_offset(height, nh, oy)
    src_x = max(0, -x)
    src_y = max(0, -y)
    dst_x = max(0, x)
    dst_y = max(0, y)
    copy_w = min(nw - src_x, width - dst_x)
    copy_h = min(nh - src_y, height - dst_y)
    if copy_w > 0 and copy_h > 0:
        piece = resized.crop((src_x, src_y, src_x + copy_w, src_y + copy_h))
        canvas.alpha_composite(piece, (dst_x, dst_y))
    return canvas


def suggest_smart_frame(width: int, height: int) -> tuple[str, float, float, float]:
    """Fill 9:16 with a slight punch-in; bias tall photos toward the upper third."""
    if width <= 0 or height <= 0:
        return FitMode.FILL.value, 1.0, 0.0, 0.0
    aspect = width / float(height)
    if abs(aspect - CANVAS_ASPECT) < 0.04:
        return FitMode.FILL.value, 1.0, 0.0, 0.0
    if aspect > CANVAS_ASPECT:
        return FitMode.FILL.value, 1.12, 0.0, 0.0
    return FitMode.FILL.value, 1.08, 0.0, -0.18


def zoom_toward_point(
    crop_x: float,
    crop_y: float,
    zoom: float,
    new_zoom: float,
    nx: float,
    ny: float,
) -> tuple[float, float, float]:
    """Keep the preview point at normalized (-1..1) coords stable while zooming."""
    z0 = clamp_zoom(zoom)
    z1 = clamp_zoom(new_zoom)
    factor = (z1 - z0) / max(z1, 0.01)
    cx, cy = clamp_crop(crop_x + nx * factor, crop_y + ny * factor)
    return cx, cy, z1


def pad_rgb_for_template(template_id: str | None) -> tuple[int, int, int]:
    raw = str(template_id or "").lower()
    if raw == "bmt_nature":
        return (14, 28, 22)
    if raw == "bmt_minimal":
        return (8, 10, 14)
    return DEFAULT_PAD_RGB
