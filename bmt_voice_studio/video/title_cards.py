"""Pillow title cards and overlay PNGs for BMT CLASSIC and BMT NATURE."""

from __future__ import annotations

from pathlib import Path

from bmt_voice_studio.resources import logo_path as packaged_logo_path
from bmt_voice_studio.video.geometry import (
    CANVAS_HEIGHT,
    CANVAS_WIDTH,
    positioned_crop_rect,
    safe_rect,
)
from bmt_voice_studio.video.models import TEMPLATE_BMT_MINIMAL, TEMPLATE_BMT_NATURE, TEMPLATE_HHR_GREEN, TextStyle, VideoProject, hex_to_rgb

CLASSIC = {
    "bg": (15, 20, 28, 255),
    "gold": (212, 160, 23, 255),
    "white": (244, 247, 251, 255),
    "muted": (143, 160, 182, 255),
    "soft": (197, 210, 227, 255),
    "scrim": (15, 20, 28),
}
NATURE = {
    "bg": (14, 28, 22, 255),
    "gold": (214, 186, 122, 255),
    "white": (244, 247, 242, 255),
    "muted": (164, 186, 170, 255),
    "soft": (214, 226, 216, 255),
    "scrim": (10, 22, 16),
}

# Back-compat color aliases used by older helpers/tests.
BG = CLASSIC["bg"]
GOLD = CLASSIC["gold"]
WHITE = CLASSIC["white"]
MUTED = CLASSIC["muted"]
SOFT = CLASSIC["soft"]

MINIMAL = {
    "bg": (8, 10, 14, 255),
    "gold": (232, 232, 228, 255),
    "white": (250, 250, 248, 255),
    "muted": (168, 172, 178, 255),
    "soft": (220, 222, 224, 255),
    "scrim": (8, 10, 14),
}

HHR = {
    "bg": (10, 46, 34, 255),
    "gold": (214, 186, 122, 255),
    "white": (244, 247, 242, 255),
    "muted": (168, 196, 180, 255),
    "soft": (214, 226, 216, 255),
    "scrim": (8, 36, 26),
}


def palette_for(project: VideoProject | str | None) -> dict:
    tid = project if isinstance(project, str) else getattr(project, "template_id", "")
    raw = str(tid or "").lower()
    if raw == TEMPLATE_BMT_NATURE:
        return NATURE
    if raw == TEMPLATE_BMT_MINIMAL:
        return MINIMAL
    if raw == TEMPLATE_HHR_GREEN:
        return HHR
    return CLASSIC


def render_template_chip(template_id: str, width: int = 44, height: int = 78):
    """Tiny 9:16 still of a template look — for compact picker chips, not render output."""
    from PIL import Image, ImageDraw

    pal = palette_for(template_id)
    img = Image.new("RGBA", (width, height), pal["bg"])
    d = ImageDraw.Draw(img)
    gold = pal["gold"]
    white = pal["white"]
    muted = pal["muted"]
    raw = str(template_id or "").lower()
    d.rectangle([5, 7, width - 5, 9], fill=gold)
    d.rectangle([8, 14, width - 8, 20], fill=white)
    d.rectangle([10, 24, width - 14, 28], fill=muted)
    if raw == TEMPLATE_BMT_NATURE:
        d.ellipse([width // 2 - 16, height - 30, width // 2 + 18, height + 10], fill=(22, 78, 46, 255))
        d.ellipse([2, height - 24, 26, height + 6], fill=(34, 96, 54, 255))
        d.ellipse([width - 28, height - 20, width - 2, height + 8], fill=(18, 64, 38, 255))
    elif raw == TEMPLATE_BMT_MINIMAL:
        d.rectangle([width // 2 - 8, height - 16, width // 2 + 8, height - 15], fill=gold)
    elif raw == TEMPLATE_HHR_GREEN:
        d.ellipse([8, height - 28, width - 8, height + 8], fill=(18, 92, 62, 255))
        d.rectangle([10, 34, width - 10, 36], fill=gold)
    else:
        d.rectangle([10, 34, width - 10, 36], fill=gold)
        d.rectangle([6, height - 20, width - 6, height - 7], fill=(22, 30, 42, 255))
    d.rectangle([0, 0, width - 1, height - 1], outline=gold)
    return img


def system_font_candidates(bold: bool = False) -> list[Path]:
    """Legal system fonts only — never package unauthorized typefaces."""
    windir = Path(r"C:\Windows\Fonts")
    if bold:
        names = ["segoeuib.ttf", "arialbd.ttf", "calibrib.ttf", "tahomabd.ttf"]
    else:
        names = ["segoeui.ttf", "arial.ttf", "calibri.ttf", "tahoma.ttf"]
    found: list[Path] = []
    for name in names:
        path = windir / name
        if path.is_file():
            found.append(path)
    linux = [
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
    ]
    for path in linux:
        if path.is_file():
            found.append(path)
    return found


def load_font(size: int, bold: bool = False):
    from PIL import ImageFont

    for path in system_font_candidates(bold=bold):
        try:
            return ImageFont.truetype(str(path), size=max(10, int(size)))
        except Exception:
            continue
    return ImageFont.load_default()


def wrap_text(draw, text: str, font, max_width: int, max_lines: int = 4) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    max_width = max(24, int(max_width))
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        trial = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), trial, font=font)
        if bbox[2] - bbox[0] <= max_width or not current:
            current = trial
        else:
            lines.append(current)
            current = word
            if len(lines) >= max_lines:
                break
    if current and len(lines) < max_lines:
        lines.append(current)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
    if lines:
        last = lines[-1]
        bbox = draw.textbbox((0, 0), last, font=font)
        if bbox[2] - bbox[0] > max_width and len(last) > 8:
            while last and draw.textbbox((0, 0), last + "…", font=font)[2] > max_width:
                last = last[:-1]
            lines[-1] = last.rstrip() + "…"
    return lines


def wrap_and_shrink(
    draw,
    text: str,
    max_width: int,
    *,
    start_size: int = 48,
    min_size: int = 18,
    max_lines: int = 4,
    bold: bool = True,
) -> tuple[list[str], object]:
    """Wrap then shrink font until the block stays inside max_width."""
    font = load_font(start_size, bold)
    lines: list[str] = []
    for size in range(int(start_size), int(min_size) - 1, -2):
        font = load_font(size, bold)
        lines = wrap_text(draw, text, font, max_width, max_lines)
        if not lines:
            return [], font
        widest = max(draw.textbbox((0, 0), line, font=font)[2] - draw.textbbox((0, 0), line, font=font)[0] for line in lines)
        if widest <= max_width:
            return lines, font
    return wrap_text(draw, text, load_font(min_size, bold), max_width, max_lines), load_font(min_size, bold)


def project_text_style(project: VideoProject | None) -> TextStyle:
    style = getattr(project, "text_style", None) if project is not None else None
    if isinstance(style, TextStyle):
        return style.normalized()
    return TextStyle().normalized()


def type_scale(project: VideoProject | None, width: int = CANVAS_WIDTH) -> float:
    style = project_text_style(project)
    return (style.font_size / 64.0) * (max(1, int(width)) / float(CANVAS_WIDTH))


def draw_styled_text(draw, xy, text: str, font, project: VideoProject | None, fill, *, stroke: bool = True) -> None:
    style = project_text_style(project)
    stroke_fill = (*hex_to_rgb(style.stroke_color, (0, 0, 0)), 255) if len(fill) == 4 else hex_to_rgb(style.stroke_color, (0, 0, 0))
    width = int(style.stroke_width) if stroke else 0
    draw.text(xy, text, font=font, fill=fill, stroke_width=width, stroke_fill=stroke_fill)


def body_fill(project: VideoProject | None, fallback=(244, 247, 251, 255)):
    style = project_text_style(project)
    rgb = hex_to_rgb(style.text_color, fallback[:3])
    return (*rgb, 255)


def resolve_logo_path(project: VideoProject) -> Path | None:
    from bmt_voice_studio.config.product import is_hhr

    product = getattr(project, "product_mode", None)
    packaged = packaged_logo_path(product)
    for candidate in (project.logo_path, str(packaged or "")):
        if candidate:
            path = Path(candidate)
            if path.is_file():
                return path
    if is_hhr(product):
        fallback = packaged_logo_path("hhr")
        if fallback and fallback.is_file():
            return fallback
    return None


def _pretty_date(project: VideoProject) -> str:
    if not project.devotional_date:
        return ""
    from bmt_voice_studio.daily.naming import display_date, freeze_devotional_date

    try:
        return display_date(freeze_devotional_date(project.devotional_date))
    except Exception:
        return project.devotional_date


def knockout_black_background(image):
    """Turn near-black fields transparent so the logo never sits in a black box."""
    from PIL import Image

    im = image.convert("RGBA")
    w, h = im.size
    px = im.load()
    reflect_y = int(h * 0.92)
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            mx = max(r, g, b)
            mn = min(r, g, b)
            lum = (r + g + b) / 3.0
            sat = 0.0 if mx == 0 else (mx - mn) / mx
            if y >= reflect_y and lum < 110:
                px[x, y] = (r, g, b, 0)
                continue
            if sat >= 0.12 and mx >= 22:
                continue
            if lum <= 18:
                px[x, y] = (r, g, b, 0)
            elif lum <= 48 and sat < 0.18:
                alpha = int(round(255 * ((lum - 18) / 30.0)))
                px[x, y] = (r, g, b, min(a, max(0, alpha)))
    bbox = im.getbbox()
    if bbox:
        pad = 6
        left, top, right, bottom = bbox
        im = im.crop(
            (max(0, left - pad), max(0, top - pad), min(w, right + pad), min(h, bottom + pad))
        )
    px = im.load()
    w, h = im.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a == 0:
                continue
            mx = max(r, g, b)
            mn = min(r, g, b)
            lum = (r + g + b) / 3.0
            sat = 0.0 if mx == 0 else (mx - mn) / mx
            if lum < 22 and sat < 0.2:
                px[x, y] = (r, g, b, 0)
            elif lum < 40 and sat < 0.15:
                px[x, y] = (r, g, b, int(a * 0.35))
    bbox = im.getbbox()
    if bbox:
        im = im.crop(bbox)
    return im


def defringe_dark_matte(image):
    """Clear leftover black-matte fringe on partial-alpha edges; keep gold/blue detail."""
    im = image.convert("RGBA")
    px = im.load()
    w, h = im.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a == 0 or a >= 245:
                continue
            mx = max(r, g, b)
            mn = min(r, g, b)
            lum = (r + g + b) / 3.0
            sat = 0.0 if mx == 0 else (mx - mn) / mx
            if sat >= 0.22 and mx >= 40:
                continue
            if lum <= 22:
                px[x, y] = (r, g, b, 0)
            elif lum <= 34 and a < 160:
                px[x, y] = (r, g, b, int(a * 0.45))
    return im


def _has_solid_black_field(image) -> bool:
    px = image.load()
    w, h = image.size
    samples = [
        px[0, 0],
        px[w - 1, 0],
        px[0, h - 1],
        px[w - 1, h - 1],
    ]
    opaque_black = 0
    for r, g, b, a in samples:
        if a > 200 and r < 12 and g < 12 and b < 12:
            opaque_black += 1
    return opaque_black >= 3


def _prepare_logo(logo_file: Path, *, max_w: int, max_h: int):
    from PIL import Image

    logo = Image.open(logo_file).convert("RGBA")
    if _has_solid_black_field(logo):
        logo = knockout_black_background(logo)
    logo = defringe_dark_matte(logo)
    logo.thumbnail((max(1, int(max_w)), max(1, int(max_h))), Image.Resampling.LANCZOS)
    return logo


def _paste_logo(canvas, logo_file: Path, *, max_w: int, max_h: int, x: int, y: int) -> int:
    try:
        logo = _prepare_logo(logo_file, max_w=max_w, max_h=max_h)
    except Exception:
        return y
    canvas.alpha_composite(logo, (max(0, int(x)), max(0, int(y))))
    return y + logo.height


def _paste_logo_centered(canvas, logo_file: Path, *, max_w: int, max_h: int, center_x: int, y: int) -> int:
    try:
        logo = _prepare_logo(logo_file, max_w=max_w, max_h=max_h)
    except Exception:
        return y
    x = int(center_x - logo.width / 2)
    canvas.alpha_composite(logo, (max(0, x), max(0, int(y))))
    return y + logo.height


def _text_size(draw, text: str, font) -> tuple[int, int]:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def _center_text(draw, text: str, font, fill, *, cx: int, y: int, gap: int = 12, project: VideoProject | None = None) -> int:
    tw, th = _text_size(draw, text, font)
    draw_styled_text(draw, (int(cx - tw / 2), y), text, font, project, fill)
    return y + th + gap


def _cover_media_background(project: VideoProject, width: int, height: int):
    from bmt_voice_studio.video.image_io import composite_media_frame, pad_rgb_for_template

    bg = pad_rgb_for_template(project.template_id)
    for item in project.ordered_media():
        if not item.exists() or item.media_type != "image":
            continue
        try:
            return composite_media_frame(item, width, height, bg)
        except Exception:
            continue
    return None


def render_intro_card(
    project: VideoProject,
    dest: Path,
    *,
    width: int = CANVAS_WIDTH,
    height: int = CANVAS_HEIGHT,
    reveal: str = "full",
) -> Path:
    """10-second intro uses the locked 9:16 brand card, never a photo thumbnail."""
    from bmt_voice_studio.video.locked_card import render_locked_intro_card

    return render_locked_intro_card(project, dest, width=width, height=height)


def render_outro_card(
    project: VideoProject,
    dest: Path,
    *,
    width: int = CANVAS_WIDTH,
    height: int = CANVAS_HEIGHT,
) -> Path:
    from PIL import Image, ImageDraw

    pal = palette_for(project)
    img = Image.new("RGBA", (width, height), pal["bg"])
    draw = ImageDraw.Draw(img)
    sx, sy, sw, sh = safe_rect(width, height)
    scale = width / CANVAS_WIDTH
    cx = width // 2
    logo = resolve_logo_path(project) if project.branding.logo else None
    font_series = load_font(max(28, int(42 * scale)), bold=True)
    font_kicker = load_font(max(16, int(22 * scale)), bold=True)
    block_h = 0
    if logo:
        try:
            prepared = _prepare_logo(logo, max_w=min(int(580 * scale), sw), max_h=int(300 * scale))
            block_h += prepared.height + int(36 * scale)
        except Exception:
            pass
    from bmt_voice_studio.video.brand_strings import brand_strings

    labels = brand_strings(project.language, getattr(project, "product_mode", None))
    block_h += _text_size(draw, labels["series_title"], font_series)[1] + int(12 * scale)
    block_h += _text_size(draw, labels["daily_devotional"], font_kicker)[1]
    y = sy + max(0, (sh - block_h) // 2)
    if logo:
        y = _paste_logo_centered(
            img, logo, max_w=min(int(580 * scale), sw), max_h=int(300 * scale), center_x=cx, y=y
        )
        y += int(36 * scale)
    y = _center_text(draw, labels["series_title"], font_series, pal["white"], cx=cx, y=y, gap=int(12 * scale))
    y = _center_text(draw, labels["daily_devotional"], font_kicker, pal["gold"], cx=cx, y=y, gap=int(18 * scale))
    y = _center_text(draw, labels["remain_blessed"], font_kicker, pal["soft"], cx=cx, y=y, gap=8)
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(dest, "PNG")
    return dest


def render_overlay_png(
    project: VideoProject,
    dest: Path,
    *,
    width: int = CANVAS_WIDTH,
    height: int = CANVAS_HEIGHT,
) -> Path:
    """Compact persistent overlay: small logo + optional topic (post-intro)."""
    from PIL import Image, ImageDraw

    pal = palette_for(project)
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    sx, sy, sw, _sh = safe_rect(width, height)
    nature = project.template_id == TEMPLATE_BMT_NATURE
    top_h = 220 if nature else 280
    for i in range(top_h):
        alpha = int((90 if nature else 130) * (1.0 - i / top_h))
        draw.line([(0, i), (width, i)], fill=(*pal["scrim"], alpha))
    y = sy
    logo = resolve_logo_path(project) if project.branding.logo else None
    scale = type_scale(project, width)
    if logo:
        y = _paste_logo(img, logo, max_w=min(200, sw // 2), max_h=86, x=sx, y=y) + 10
    if project.branding.topic and project.topic:
        lines, font = wrap_and_shrink(
            draw, project.topic, sw, start_size=max(22, int(36 * scale)), min_size=max(16, int(20 * scale)), max_lines=2
        )
        fill = body_fill(project)
        for line in lines:
            draw_styled_text(draw, (sx, y), line, font, project, fill)
            bbox = draw.textbbox((0, 0), line, font=font)
            y += (bbox[3] - bbox[1]) + 4
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest, "PNG")
    return dest


def render_header_overlay(
    project: VideoProject,
    dest: Path,
    *,
    width: int = CANVAS_WIDTH,
    height: int = CANVAS_HEIGHT,
) -> Path:
    """First 8–12s of main video: date + topic, then this overlay fades out."""
    from PIL import Image, ImageDraw

    pal = palette_for(project)
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    sx, sy, sw, _sh = safe_rect(width, height)
    for i in range(360):
        alpha = int(140 * (1.0 - i / 360.0))
        draw.line([(0, i), (width, i)], fill=(*pal["scrim"], alpha))
    y = sy
    logo = resolve_logo_path(project) if project.branding.logo else None
    if logo:
        y = _paste_logo(img, logo, max_w=220, max_h=92, x=sx, y=y) + 12
    if project.branding.date and project.devotional_date:
        font_date = load_font(max(22, int(32 * type_scale(project, width))), bold=True)
        draw_styled_text(draw, (sx, y), _pretty_date(project).upper(), font_date, project, pal["gold"])
        y += 36
    if project.branding.topic and project.topic:
        lines, font = wrap_and_shrink(
            draw, project.topic, sw, start_size=max(28, int(56 * type_scale(project, width))), min_size=max(18, int(26 * type_scale(project, width))), max_lines=3
        )
        fill = body_fill(project)
        for line in lines:
            draw_styled_text(draw, (sx, y), line, font, project, fill)
            bbox = draw.textbbox((0, 0), line, font=font)
            y += (bbox[3] - bbox[1]) + 6
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest, "PNG")
    return dest


def render_lower_third(
    project: VideoProject,
    dest: Path,
    *,
    width: int = CANVAS_WIDTH,
    height: int = CANVAS_HEIGHT,
) -> Path:
    """BMT CLEAN LOWER THIRD — topic and/or date in the bottom safe zone."""
    from PIL import Image, ImageDraw

    pal = palette_for(project)
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    sx, _sy, sw, _sh = safe_rect(width, height)
    bar_h = 168
    y0 = height - bar_h - 48
    for i in range(bar_h + 80):
        yy = y0 - 40 + i
        if 0 <= yy < height:
            alpha = min(170, int(160 * (i / (bar_h + 40))))
            draw.line([(0, yy), (width, yy)], fill=(*pal["scrim"], alpha))
    draw.rectangle([sx, y0 + 18, sx + 6, y0 + bar_h - 28], fill=pal["gold"])
    y = y0 + 28
    font_kicker = load_font(max(16, int(20 * type_scale(project, width))), bold=True)
    from bmt_voice_studio.video.brand_strings import brand_strings

    series = brand_strings(project.language, getattr(project, "product_mode", None))["series_title"]
    draw_styled_text(draw, (sx + 22, y), series, font_kicker, project, pal["gold"])
    y += 28
    if project.branding.lower_third_date and project.devotional_date:
        font_date = load_font(max(18, int(26 * type_scale(project, width))), bold=False)
        draw_styled_text(draw, (sx + 22, y), _pretty_date(project), font_date, project, pal["muted"])
        y += 30
    if project.branding.lower_third_topic and project.topic:
        lines, font = wrap_and_shrink(
            draw, project.topic, sw - 40, start_size=max(24, int(44 * type_scale(project, width))), min_size=max(16, int(22 * type_scale(project, width))), max_lines=2
        )
        fill = body_fill(project)
        for line in lines:
            draw_styled_text(draw, (sx + 22, y), line, font, project, fill)
            bbox = draw.textbbox((0, 0), line, font=font)
            y += (bbox[3] - bbox[1]) + 4
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest, "PNG")
    return dest


def render_week_card(
    project: VideoProject,
    dest: Path,
    *,
    width: int = CANVAS_WIDTH,
    height: int = CANVAS_HEIGHT,
) -> Path:
    from PIL import Image, ImageDraw

    pal = palette_for(project)
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    verse = (project.memory_verse or "").strip()
    week = (project.week_focus or "").strip() if project.branding.week_focus else ""
    if not verse and not week:
        dest.parent.mkdir(parents=True, exist_ok=True)
        img.save(dest, "PNG")
        return dest
    draw = ImageDraw.Draw(img)
    sx, sy, sw, sh = safe_rect(width, height)
    scale = type_scale(project, width)
    cx = width // 2
    pad = int(36 * scale)
    inner_w = sw - pad * 2
    font_label = load_font(max(16, int(22 * scale)), bold=True)
    font_tag = load_font(max(15, int(20 * scale)), bold=True)
    verse_lines: list[str] = []
    font_verse = load_font(max(28, int(56 * scale)), bold=True)
    if verse:
        verse_lines, font_verse = wrap_and_shrink(
            draw, verse, inner_w, start_size=int(64 * scale), min_size=28, max_lines=7, bold=True
        )
    week_lines: list[str] = []
    font_week = load_font(max(18, int(28 * scale)), bold=False)
    if week:
        week_lines, font_week = wrap_and_shrink(
            draw, week, inner_w, start_size=int(32 * scale), min_size=18, max_lines=3, bold=False
        )
    content_h = int(40 * scale)
    if verse_lines:
        content_h += _text_size(draw, "MEMORY VERSE", font_label)[1] + int(16 * scale)
        for line in verse_lines:
            content_h += _text_size(draw, line, font_verse)[1] + int(10 * scale)
        content_h += int(18 * scale)
    if week_lines:
        content_h += _text_size(draw, "WEEK FOCUS", font_tag)[1] + int(10 * scale)
        for line in week_lines:
            content_h += _text_size(draw, line, font_week)[1] + int(6 * scale)
    card_h = min(int(sh * 0.58), content_h + int(56 * scale))
    y0 = sy + max(0, (sh - card_h) // 2)
    band = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    bdraw = ImageDraw.Draw(band)
    band_top = max(0, y0 - int(72 * scale))
    band_bot = min(height, y0 + card_h + int(72 * scale))
    band_h = max(1, band_bot - band_top)
    for i in range(band_h):
        t = i / max(1, band_h - 1)
        falloff = 1.0 - abs(2.0 * t - 1.0)
        bdraw.line([(0, band_top + i), (width, band_top + i)], fill=(*pal["scrim"], int(96 * falloff)))
    img.alpha_composite(band)
    panel = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    pdraw = ImageDraw.Draw(panel)
    pdraw.rounded_rectangle(
        [sx, y0, sx + sw, y0 + card_h],
        radius=int(22 * scale),
        fill=(*pal["scrim"], 196),
    )
    img.alpha_composite(panel)
    y = y0 + int(28 * scale)
    if verse_lines:
        y = _center_text(draw, "MEMORY VERSE", font_label, pal["gold"], cx=cx, y=y, gap=int(16 * scale), project=project)
        for line in verse_lines:
            y = _center_text(draw, line, font_verse, body_fill(project), cx=cx, y=y, gap=int(10 * scale), project=project)
        y += int(10 * scale)
        rule_w = int(90 * scale)
        draw.rectangle([cx - rule_w, y, cx + rule_w, y + 2], fill=pal["gold"])
        y += int(20 * scale)
    if week_lines:
        y = _center_text(draw, "WEEK FOCUS", font_tag, pal["gold"], cx=cx, y=y, gap=int(10 * scale), project=project)
        for line in week_lines:
            y = _center_text(draw, line, font_week, pal["soft"], cx=cx, y=y, gap=int(6 * scale), project=project)
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest, "PNG")
    return dest


def render_verse_card(
    project: VideoProject,
    dest: Path,
    *,
    width: int = CANVAS_WIDTH,
    height: int = CANVAS_HEIGHT,
) -> Path:
    """Second-screen memory verse / transcript presentation."""
    return render_week_card(project, dest, width=width, height=height)


def render_preview_still(
    project: VideoProject,
    dest: Path,
    *,
    media_path: str = "",
) -> Path:
    """Composite a representative 9:16 preview frame (no real-time timeline)."""
    from PIL import Image

    pal = palette_for(project)
    canvas = Image.new("RGBA", (CANVAS_WIDTH, CANVAS_HEIGHT), pal["bg"])
    source = Path(media_path) if media_path else None
    item = None
    if source is None or not source.is_file():
        for candidate in project.ordered_media():
            if not candidate.exists():
                continue
            if candidate.media_type == "image":
                source = candidate.resolved_path()
                item = candidate
                break
            if candidate.media_type == "video":
                try:
                    from bmt_voice_studio.video.thumbs import extract_thumbnail

                    thumb = extract_thumbnail(
                        candidate.path,
                        media_type=candidate.media_type,
                        rotation=int(getattr(candidate, "rotation", 0) or 0),
                        square=False,
                    )
                    if thumb and Path(thumb).is_file():
                        source = Path(thumb)
                        item = candidate
                        break
                except Exception:
                    continue
    if source and source.is_file():
        try:
            from bmt_voice_studio.video.image_io import composite_media_frame, pad_rgb_for_template

            if item is None:
                item = next(
                    (c for c in project.ordered_media() if c.exists() and str(c.resolved_path()) == str(source)),
                    None,
                )
            if item is not None:
                from dataclasses import replace

                frame_item = item
                if item.media_type == "video":
                    frame_item = replace(item, path=str(source), media_type="image", rotation=0)
                canvas = composite_media_frame(
                    frame_item, CANVAS_WIDTH, CANVAS_HEIGHT, pad_rgb_for_template(project.template_id)
                )
            else:
                from bmt_voice_studio.video.image_io import flatten_rgba, open_rgba

                photo = flatten_rgba(open_rgba(source), pal["bg"][:3]).convert("RGBA")
                x, y, w, h = positioned_crop_rect(photo.width, photo.height, CANVAS_WIDTH, CANVAS_HEIGHT, 0.0, 0.0, 1.0)
                canvas = photo.crop((x, y, x + w, y + h)).resize(
                    (CANVAS_WIDTH, CANVAS_HEIGHT), Image.Resampling.LANCZOS
                )
        except Exception:
            pass

    overlay_tmp = dest.with_name(dest.stem + "_overlay.png")
    render_header_overlay(project, overlay_tmp)
    overlay = Image.open(overlay_tmp).convert("RGBA")
    canvas.alpha_composite(overlay)
    if project.show_captions or project.branding.captions:
        from bmt_voice_studio.video.captions import render_caption_preview

        sample = (project.memory_verse or project.topic or "Seek first the kingdom of God").strip()
        cap = render_caption_preview(
            getattr(project, "text_style", None),
            sample,
            width=CANVAS_WIDTH,
            height=CANVAS_HEIGHT,
            background=None,
        )
        canvas.alpha_composite(cap)
    dest.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(dest, "PNG", quality=92)
    try:
        overlay_tmp.unlink(missing_ok=True)
    except Exception:
        pass
    return dest
