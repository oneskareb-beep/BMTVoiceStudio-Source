"""9:16 composition geometry — cover/contain crop math (pure functions)."""

from __future__ import annotations

CANVAS_WIDTH = 1080
CANVAS_HEIGHT = 1920
CANVAS_ASPECT = CANVAS_WIDTH / CANVAS_HEIGHT  # 0.5625
CANVAS_FPS = 30
SCENE_PIXEL_FORMAT = "yuv420p"


def even_dim(value: int) -> int:
    """libx264 / yuv420p require even width and height."""
    v = max(2, int(value))
    return v - (v % 2)


def scene_normalize_filter(
    dst_w: int = CANVAS_WIDTH,
    dst_h: int = CANVAS_HEIGHT,
    fps: int = CANVAS_FPS,
) -> str:
    """Force identical concat/xfade geometry on every video stream.

    Fit/fill/crop/Ken Burns run first. This always finishes with square SAR,
    CFR, and limited-range yuv420p so JPEG/yuvj sources and odd-SAR crops
    cannot break FFmpeg concat or xfade.
    """
    dw = even_dim(dst_w)
    dh = even_dim(dst_h)
    rate = max(1, int(fps or CANVAS_FPS))
    return (
        f"scale={dw}:{dh}:in_range=auto:out_range=tv,"
        f"setsar=1,"
        f"fps={rate},"
        f"settb=1/{rate},"
        f"format={SCENE_PIXEL_FORMAT}"
    )


def cover_scale(src_w: int, src_h: int, dst_w: int = CANVAS_WIDTH, dst_h: int = CANVAS_HEIGHT) -> float:
    """Scale factor so the source covers the destination (no letterbox)."""
    if src_w <= 0 or src_h <= 0:
        return 1.0
    return max(dst_w / src_w, dst_h / src_h)


def contain_scale(src_w: int, src_h: int, dst_w: int = CANVAS_WIDTH, dst_h: int = CANVAS_HEIGHT) -> float:
    """Scale factor so the source fits inside the destination (may letterbox)."""
    if src_w <= 0 or src_h <= 0:
        return 1.0
    return min(dst_w / src_w, dst_h / src_h)


def center_crop_rect(
    src_w: int,
    src_h: int,
    dst_w: int = CANVAS_WIDTH,
    dst_h: int = CANVAS_HEIGHT,
) -> tuple[int, int, int, int]:
    """Center crop in source pixels after a cover-scale to dst.

    Returns (x, y, width, height) in source image coordinates.
    """
    if src_w <= 0 or src_h <= 0:
        return 0, 0, max(1, src_w), max(1, src_h)
    scale = cover_scale(src_w, src_h, dst_w, dst_h)
    crop_w = min(src_w, max(1, int(round(dst_w / scale))))
    crop_h = min(src_h, max(1, int(round(dst_h / scale))))
    x = max(0, (src_w - crop_w) // 2)
    y = max(0, (src_h - crop_h) // 2)
    if x + crop_w > src_w:
        x = src_w - crop_w
    if y + crop_h > src_h:
        y = src_h - crop_h
    return x, y, crop_w, crop_h


def landscape_center_crop(src_w: int, src_h: int) -> tuple[int, int, int, int]:
    """Center cover-crop a landscape (or any) frame onto 9:16."""
    return center_crop_rect(src_w, src_h, CANVAS_WIDTH, CANVAS_HEIGHT)


def portrait_center_crop(src_w: int, src_h: int) -> tuple[int, int, int, int]:
    """Center cover-crop a portrait frame onto 9:16 (same math, explicit name for tests)."""
    return center_crop_rect(src_w, src_h, CANVAS_WIDTH, CANVAS_HEIGHT)


def contain_dest_rect(
    src_w: int,
    src_h: int,
    dst_w: int = CANVAS_WIDTH,
    dst_h: int = CANVAS_HEIGHT,
) -> tuple[int, int, int, int]:
    """Destination rectangle for letterboxed fit (x, y, w, h) on the canvas."""
    if src_w <= 0 or src_h <= 0:
        return 0, 0, dst_w, dst_h
    scale = contain_scale(src_w, src_h, dst_w, dst_h)
    w = max(1, int(round(src_w * scale)))
    h = max(1, int(round(src_h * scale)))
    x = (dst_w - w) // 2
    y = (dst_h - h) // 2
    return x, y, w, h


def is_landscape(src_w: int, src_h: int) -> bool:
    return src_w > src_h


def is_portrait(src_w: int, src_h: int) -> bool:
    return src_h >= src_w


def ffmpeg_cover_filter(dst_w: int = CANVAS_WIDTH, dst_h: int = CANVAS_HEIGHT) -> str:
    """Scale-to-cover then center-crop. Does not stretch."""
    return (
        f"scale={dst_w}:{dst_h}:force_original_aspect_ratio=increase,"
        f"crop={dst_w}:{dst_h}"
    )


def ffmpeg_contain_filter(
    dst_w: int = CANVAS_WIDTH,
    dst_h: int = CANVAS_HEIGHT,
    pad_color: str = "0x0F141C",
) -> str:
    """Scale-to-fit then pad (letterbox/pillarbox). Does not stretch."""
    return (
        f"scale={dst_w}:{dst_h}:force_original_aspect_ratio=decrease,"
        f"pad={dst_w}:{dst_h}:(ow-iw)/2:(oh-ih)/2:color={pad_color}"
    )


def ffmpeg_mid_band_filter(
    dst_w: int = CANVAS_WIDTH,
    dst_h: int = CANVAS_HEIGHT,
    pad_color: str = "0x0F141C",
) -> str:
    """Place media in the middle 2/4 of the frame (1/4 empty top + 1/4 empty bottom).

    Landscape meditation / paysage posters stay fully visible inside the mid band.
    """
    dw = even_dim(dst_w)
    dh = even_dim(dst_h)
    band_h = even_dim(max(2, dh // 2))
    band_y = even_dim(max(0, (dh - band_h) // 2))
    color = pad_color or _PAD_COLOR
    return (
        f"scale={dw}:{band_h}:force_original_aspect_ratio=decrease,"
        f"pad={dw}:{band_h}:(ow-iw)/2:(oh-ih)/2:color={color},"
        f"pad={dw}:{dh}:0:{band_y}:color={color}"
    )


def safe_margin(dst_w: int = CANVAS_WIDTH, dst_h: int = CANVAS_HEIGHT) -> int:
    """Inset for WhatsApp/social UI chrome — do not place critical text at edges."""
    return max(64, int(round(min(dst_w, dst_h) * 0.07)))


# Explicit 9:16 safe zones (pixels on the 1080x1920 canvas).
SAFE_TOP = 96
SAFE_BOTTOM = 140
SAFE_SIDE = 72
CROP_MIN = -1.0
CROP_MAX = 1.0
# Low enough that 16:9 (and typical wider) media can sit fully visible in 9:16.
ZOOM_MIN = 0.15
ZOOM_MAX = 2.50
_PAD_COLOR = "0x0F141C"


def safe_rect(dst_w: int = CANVAS_WIDTH, dst_h: int = CANVAS_HEIGHT) -> tuple[int, int, int, int]:
    """Return (x, y, w, h) of the inner safe rectangle."""
    top = max(SAFE_TOP, int(round(dst_h * 0.05)))
    bottom = max(SAFE_BOTTOM, int(round(dst_h * 0.07)))
    side = max(SAFE_SIDE, int(round(dst_w * 0.067)))
    return side, top, max(1, dst_w - 2 * side), max(1, dst_h - top - bottom)


def contain_relative_zoom(
    src_w: int,
    src_h: int,
    dst_w: int = CANVAS_WIDTH,
    dst_h: int = CANVAS_HEIGHT,
) -> float:
    """Fill-mode zoom where the whole source is visible (cover becomes contain).

    16:9 in 9:16 is about 0.32. Zoom 1.0 is still a cropped cover fill.
    """
    cov = cover_scale(src_w, src_h, dst_w, dst_h)
    con = contain_scale(src_w, src_h, dst_w, dst_h)
    if cov <= 1e-9:
        return 1.0
    return max(ZOOM_MIN, min(1.0, con / cov))


def clamp_unit(value: float) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(CROP_MIN, min(CROP_MAX, v))


def clamp_crop(crop_x: float, crop_y: float) -> tuple[float, float]:
    return clamp_unit(crop_x), clamp_unit(crop_y)


def clamp_zoom(zoom: float) -> float:
    try:
        z = float(zoom)
    except (TypeError, ValueError):
        return 1.0
    if z <= 0:
        return 1.0
    return max(ZOOM_MIN, min(ZOOM_MAX, z))


def clamp_trim(start: float, end: float, source_duration: float = 0.0) -> tuple[float, float]:
    try:
        start_v = max(0.0, float(start or 0.0))
    except (TypeError, ValueError):
        start_v = 0.0
    try:
        end_v = float(end or 0.0)
    except (TypeError, ValueError):
        end_v = 0.0
    source = max(0.0, float(source_duration or 0.0))
    if end_v < 0:
        end_v = 0.0
    if source > 0:
        start_v = min(start_v, max(0.0, source - 0.05))
        if end_v > 0:
            end_v = min(end_v, source)
    if end_v > 0 and end_v <= start_v:
        end_v = 0.0
    return start_v, end_v


def visual_trim_span(start: float, end: float, source_duration: float = 0.0) -> tuple[float, float, float]:
    """Return (start, end_display, used_duration) clamped to the source."""
    start_v, end_v = clamp_trim(start, end, source_duration)
    source = max(0.0, float(source_duration or 0.0))
    end_t = end_v if end_v > 0 else source
    if source > 0:
        end_t = min(end_t, source)
    if end_t < start_v:
        end_t = start_v
    return start_v, end_t, max(0.0, end_t - start_v)


def positioned_crop_rect(
    src_w: int,
    src_h: int,
    dst_w: int = CANVAS_WIDTH,
    dst_h: int = CANVAS_HEIGHT,
    crop_x: float = 0.0,
    crop_y: float = 0.0,
    zoom: float = 1.0,
) -> tuple[int, int, int, int]:
    """Center-cover crop shifted by normalized crop_x/crop_y and zoomed.

    crop_x/crop_y are -1..+1 (left/top to right/bottom). zoom is ZOOM_MIN–ZOOM_MAX.
    Returns (x, y, w, h) in source pixels. Never negative dimensions.
    """
    src_w = max(1, int(src_w))
    src_h = max(1, int(src_h))
    dst_w = max(2, int(dst_w))
    dst_h = max(2, int(dst_h))
    cx, cy, cw, ch = center_crop_rect(src_w, src_h, dst_w, dst_h)
    z = clamp_zoom(zoom)
    crop_w = max(1, min(src_w, int(round(cw / z))))
    crop_h = max(1, min(src_h, int(round(ch / z))))
    ox, oy = clamp_crop(crop_x, crop_y)
    slack_x = max(0, src_w - crop_w)
    slack_y = max(0, src_h - crop_h)
    x = int(round((slack_x / 2.0) * (1.0 + ox)))
    y = int(round((slack_y / 2.0) * (1.0 + oy)))
    x = max(0, min(x, src_w - crop_w))
    y = max(0, min(y, src_h - crop_h))
    return x, y, crop_w, crop_h


def ffmpeg_positioned_cover_filter(
    dst_w: int = CANVAS_WIDTH,
    dst_h: int = CANVAS_HEIGHT,
    crop_x: float = 0.0,
    crop_y: float = 0.0,
    zoom: float = 1.0,
    pad_color: str = "0x0F141C",
) -> str:
    """Scale-to-cover, apply zoom, then crop (or pad when zoomed out). No stretch."""
    ox, oy = clamp_crop(crop_x, crop_y)
    z = clamp_zoom(zoom)
    dw = max(2, int(dst_w) - int(dst_w) % 2)
    dh = max(2, int(dst_h) - int(dst_h) % 2)
    color = pad_color or _PAD_COLOR
    if z < 0.999:
        # Scale the original cover, then shrink — do not 9:16-crop first,
        # or landscape media can never become a full landscape rectangle.
        return (
            f"scale={dw}:{dh}:force_original_aspect_ratio=increase,"
            f"scale=trunc(iw*{z:.4f}/2)*2:trunc(ih*{z:.4f}/2)*2,"
            f"crop='min(iw\\,{dw})':'min(ih\\,{dh})':"
            f"if(gte(iw\\,{dw})\\,(iw-{dw})/2*(1+{ox:.3f})\\,0):"
            f"if(gte(ih\\,{dh})\\,(ih-{dh})/2*(1+{oy:.3f})\\,0),"
            f"pad={dw}:{dh}:(ow-iw)/2*(1+{ox:.3f}):(oh-ih)/2*(1+{oy:.3f}):color={color}"
        )
    return (
        f"scale={dw}:{dh}:force_original_aspect_ratio=increase,"
        f"scale=iw*{z:.4f}:ih*{z:.4f},"
        f"crop={dw}:{dh}:(in_w-{dw})/2*(1+{ox:.3f}):(in_h-{dh})/2*(1+{oy:.3f})"
    )


def ffmpeg_positioned_contain_filter(
    dst_w: int = CANVAS_WIDTH,
    dst_h: int = CANVAS_HEIGHT,
    crop_x: float = 0.0,
    crop_y: float = 0.0,
    zoom: float = 1.0,
    pad_color: str = "0x0F141C",
) -> str:
    """Letterbox, then zoom/pan inside the 9:16 frame. Transparent edges use pad_color."""
    ox, oy = clamp_crop(crop_x, crop_y)
    z = clamp_zoom(zoom)
    dw = max(2, int(dst_w) - int(dst_w) % 2)
    dh = max(2, int(dst_h) - int(dst_h) % 2)
    color = pad_color or _PAD_COLOR
    if abs(z - 1.0) < 0.001 and abs(ox) < 0.001 and abs(oy) < 0.001:
        return ffmpeg_contain_filter(dw, dh, color)
    if z < 0.999:
        return (
            f"scale={dw}:{dh}:force_original_aspect_ratio=decrease,"
            f"pad={dw}:{dh}:(ow-iw)/2:(oh-ih)/2:color={color},"
            f"scale=trunc(iw*{z:.4f}/2)*2:trunc(ih*{z:.4f}/2)*2,"
            f"pad={dw}:{dh}:(ow-iw)/2*(1+{ox:.3f}):(oh-ih)/2*(1+{oy:.3f}):color={color}"
        )
    return (
        f"scale={dw}:{dh}:force_original_aspect_ratio=decrease,"
        f"pad={dw}:{dh}:(ow-iw)/2:(oh-ih)/2:color={color},"
        f"scale=iw*{z:.4f}:ih*{z:.4f},"
        f"crop={dw}:{dh}:(in_w-{dw})/2*(1+{ox:.3f}):(in_h-{dh})/2*(1+{oy:.3f})"
    )
