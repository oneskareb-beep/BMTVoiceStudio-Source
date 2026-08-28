"""Locked 9:16 Believers Manna Today card — used for 10-second intro and MP3 artwork."""

from __future__ import annotations

from pathlib import Path

from bmt_voice_studio.resources import logo_path as packaged_logo_path
from bmt_voice_studio.video.geometry import CANVAS_HEIGHT, CANVAS_WIDTH, even_dim, safe_rect
from bmt_voice_studio.video.models import VideoProject

NAVY = (11, 32, 74, 255)
NAVY_DEEP = (8, 18, 42, 255)
GOLD = (196, 118, 32, 255)
RED = (196, 32, 36, 255)
WHITE = (255, 255, 255, 255)
INK = (18, 22, 30, 255)
TOPIC_BLUE = (16, 48, 110, 255)
WARM = (214, 132, 58, 255)
AUTHOR = "Apostle (Dr.) David A. Aderibigbe"


def locked_card_path() -> Path | None:
    from bmt_voice_studio.resources import _first_existing

    return _first_existing("locked_intro_9x16.png")


def _rounded_rect(draw, box, radius: int, fill) -> None:
    draw.rounded_rectangle(box, radius=max(8, int(radius)), fill=fill)


def _draw_lock(draw, cx: int, cy: int, size: int, fill=NAVY) -> None:
    w = max(18, int(size))
    body_h = int(w * 0.62)
    body_w = int(w * 0.72)
    x0 = cx - body_w // 2
    y0 = cy - body_h // 8
    draw.rounded_rectangle((x0, y0, x0 + body_w, y0 + body_h), radius=body_w // 6, fill=fill)
    shackle_r = body_w // 2 - 2
    draw.arc(
        (cx - shackle_r, y0 - shackle_r - 2, cx + shackle_r, y0 + shackle_r - 2),
        start=200,
        end=340,
        fill=fill,
        width=max(3, w // 8),
    )
    draw.ellipse((cx - 4, y0 + body_h // 3, cx + 4, y0 + body_h // 3 + 8), fill=WHITE)


def _draw_target(draw, cx: int, cy: int, size: int, fill=INK) -> None:
    r = max(10, int(size) // 2)
    for rad, width in ((r, 3), (int(r * 0.62), 3), (int(r * 0.28), 0)):
        box = (cx - rad, cy - rad, cx + rad, cy + rad)
        if width:
            draw.ellipse(box, outline=fill, width=width)
        else:
            draw.ellipse(box, fill=fill)
    draw.line((cx - r - 4, cy, cx + r + 10, cy - r // 2), fill=fill, width=3)
    draw.polygon(
        [(cx + r + 10, cy - r // 2), (cx + r + 2, cy - r // 2 + 6), (cx + r + 4, cy - r // 2 - 2)],
        fill=fill,
    )


def _draw_flag_badge(img, cx: int, cy: int, radius: int) -> None:
    from PIL import Image, ImageDraw

    badge = Image.new("RGBA", (radius * 2 + 8, radius * 2 + 8), (0, 0, 0, 0))
    d = ImageDraw.Draw(badge)
    ox = oy = 4
    d.ellipse((ox, oy, ox + radius * 2, oy + radius * 2), fill=(244, 236, 214, 255), outline=GOLD, width=4)
    inner = radius - 8
    ix = ox + radius - inner
    iy = oy + radius - inner
    d.ellipse((ix, iy, ix + inner * 2, iy + inner * 2), fill=WHITE)
    # St George's Cross
    d.rectangle((ix + inner - 5, iy + 6, ix + inner + 5, iy + inner * 2 - 6), fill=RED)
    d.rectangle((ix + 6, iy + inner - 5, ix + inner * 2 - 6, iy + inner + 5), fill=RED)
    img.alpha_composite(badge, (cx - badge.width // 2, cy - badge.height // 2))


CREAM = (247, 244, 238, 255)
MAROON = (110, 24, 28, 255)
NAVY_TEXT = (10, 32, 74, 255)
GOLD_AUTHOR = (232, 148, 48, 255)
PAPER = (252, 250, 246, 255)


def _warm_glow(img, width: int, height: int) -> None:
    """Soft right-side warmth — crisp stand-in for the landscape wash, never an upscaled screenshot."""
    from PIL import Image, ImageDraw, ImageFilter

    glow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    g = ImageDraw.Draw(glow)
    g.ellipse(
        (int(width * 0.42), -int(height * 0.08), int(width * 1.18), int(height * 0.38)),
        fill=(214, 132, 58, 70),
    )
    g.ellipse(
        (int(width * 0.58), int(height * 0.02), int(width * 1.12), int(height * 0.28)),
        fill=(196, 80, 36, 50),
    )
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(radius=max(8, width // 40))))


def _render_hhr_intro_card(
    project: VideoProject | None,
    dest: Path,
    *,
    width: int = CANVAS_WIDTH,
    height: int = CANVAS_HEIGHT,
) -> Path:
    """Hope & Healing Africa / Ruhuka Umutima 9:16 intro — soft green brand field."""
    from PIL import Image, ImageDraw

    from bmt_voice_studio.config.product import HHR_PRODUCT
    from bmt_voice_studio.resources import logo_path as packaged_hhr_logo
    from bmt_voice_studio.video.brand_strings import brand_strings
    from bmt_voice_studio.video.title_cards import _prepare_logo, load_font, wrap_and_shrink

    labels = brand_strings("sw", "hhr")
    width = even_dim(width)
    height = even_dim(height)
    img = Image.new("RGBA", (width, height), (10, 46, 34, 255))
    draw = ImageDraw.Draw(img)
    scale = width / CANVAS_WIDTH
    sx, sy, sw, sh = safe_rect(width, height)
    cx = width // 2
    y = sy + int(36 * scale)
    cream = (244, 247, 242, 255)
    gold = (214, 186, 122, 255)
    muted = (168, 196, 180, 255)

    logo = packaged_hhr_logo("hhr")
    if logo and Path(logo).is_file():
        try:
            mark = _prepare_logo(Path(logo), max_w=min(int(920 * scale), sw), max_h=int(220 * scale))
            img.alpha_composite(mark, (cx - mark.width // 2, y))
            y += mark.height + int(28 * scale)
        except Exception:
            pass

    font_title = load_font(max(28, int(52 * scale)), bold=True)
    draw.text((cx, y), labels["title_line1"], font=font_title, fill=cream, anchor="mt")
    y += int(62 * scale)
    draw.text((cx, y), labels["title_line2"], font=font_title, fill=cream, anchor="mt")
    y += int(70 * scale)
    font_tag = load_font(max(18, int(28 * scale)), bold=True)
    draw.text((cx, y), labels["daily_devotional"], font=font_tag, fill=muted, anchor="mt")
    y += int(56 * scale)

    bar_w = min(sw, int(960 * scale))
    bar_x = (width - bar_w) // 2
    bar_h = int(72 * scale)
    _rounded_rect(draw, (bar_x, y, bar_x + bar_w, y + bar_h), int(18 * scale), (8, 36, 26, 255))
    font_kicker = load_font(max(14, int(22 * scale)), bold=True)
    kicker = labels.get("kicker") or HHR_PRODUCT.kicker
    draw.text((cx, y + bar_h // 2), kicker, font=font_kicker, fill=cream, anchor="mm")
    y += bar_h + int(28 * scale)

    font_meta = load_font(max(14, int(20 * scale)), bold=False)
    draw.text((cx, y), f"{labels['written_by']} {HHR_PRODUCT.author}", font=font_meta, fill=gold, anchor="mt")
    y += int(48 * scale)

    week = ""
    topic = ""
    pretty_date = ""
    if project is not None:
        week = (project.week_focus or project.month_theme or "").strip()
        topic = (project.topic or project.title or "").strip()
        if project.devotional_date:
            from bmt_voice_studio.video.title_cards import _pretty_date

            pretty_date = (_pretty_date(project) or "").upper()
    if week:
        font_week_l = load_font(max(14, int(18 * scale)), bold=True)
        draw.text((cx, y), labels.get("week_label") or "WEEKLY THEME", font=font_week_l, fill=muted, anchor="mt")
        y += int(32 * scale)
        lines, font_week = wrap_and_shrink(
            draw, week, bar_w - int(40 * scale), start_size=int(30 * scale), min_size=16, max_lines=2, bold=True
        )
        for line in lines:
            draw.text((cx, y), line, font=font_week, fill=cream, anchor="mt")
            y += int(40 * scale)
        y += int(12 * scale)

    panel_h = int(280 * scale)
    panel_box = (bar_x, y, bar_x + bar_w, min(height - int(120 * scale), y + panel_h))
    _rounded_rect(draw, panel_box, int(18 * scale), (244, 247, 242, 255))
    font_topic_l = load_font(max(14, int(20 * scale)), bold=True)
    draw.text((bar_x + int(36 * scale), y + int(24 * scale)), labels["topic"], font=font_topic_l, fill=(10, 46, 34, 255))
    body = topic or labels["default_topic"]
    lines, font_topic = wrap_and_shrink(
        draw, body, bar_w - int(80 * scale), start_size=int(36 * scale), min_size=18, max_lines=4, bold=True
    )
    ty = y + int(70 * scale)
    for line in lines:
        draw.text((bar_x + int(36 * scale), ty), line, font=font_topic, fill=(10, 32, 24, 255))
        ty += int(44 * scale)
    if pretty_date:
        font_date = load_font(max(16, int(26 * scale)), bold=True)
        draw.text((cx, height - int(88 * scale)), pretty_date, font=font_date, fill=gold, anchor="mt")

    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(dest, "PNG")
    return dest


FLYER_SIGNPOSTS = (
    "HEAVENLY FOCUS",
    "ETERNAL IMPACT",
    "KINGDOM PURPOSE",
    "LASTING LEGACY",
)
GOLD_BORDER = (196, 148, 48, 255)


def flyer_copy(project: VideoProject | None) -> tuple[str, str, str]:
    """Dynamic flyer fields: hero quote, theme line, weekday date."""
    from bmt_voice_studio.video.brand_strings import brand_strings

    labels = brand_strings(getattr(project, "language", None) if project else None)
    topic = ""
    week = ""
    month = ""
    verse = ""
    title = ""
    if project is not None:
        topic = (project.topic or "").strip()
        week = (project.week_focus or "").strip()
        month = (project.month_theme or "").strip()
        verse = (project.memory_verse or "").strip()
        title = (project.title or "").strip()
    quote = verse or week or title or topic or labels["default_topic"]
    theme = ""
    for candidate in (topic, week, month):
        if candidate and candidate.casefold() != quote.casefold():
            theme = candidate
            break
    if not theme:
        theme = topic or week or month
    pretty_date = ""
    if project is not None and project.devotional_date:
        pretty_date = _flyer_date(project)
    return quote, theme, pretty_date


def _flyer_date(project: VideoProject) -> str:
    from bmt_voice_studio.daily.naming import freeze_devotional_date

    try:
        day = freeze_devotional_date(project.devotional_date)
    except Exception:
        return (project.devotional_date or "").strip()
    n = day.day
    if 10 <= (n % 100) <= 20:
        suf = "th"
    else:
        suf = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{day.strftime('%A')}, {n}{suf} {day.strftime('%B %Y')}"


def _draw_calendar(draw, cx: int, cy: int, size: int, fill=INK) -> None:
    w = max(14, int(size))
    x0 = cx - w // 2
    y0 = cy - w // 2
    draw.rounded_rectangle((x0, y0, x0 + w, y0 + w), radius=max(2, w // 8), outline=fill, width=max(2, w // 10))
    draw.rectangle((x0, y0, x0 + w, y0 + w // 4), fill=fill)
    gap = max(3, w // 5)
    for col in range(2):
        for row in range(2):
            px = x0 + gap + col * gap + 2
            py = y0 + w // 3 + row * gap
            draw.ellipse((px, py, px + 3, py + 3), fill=fill)


def _draw_wood_sign(draw, box: tuple[int, int, int, int], text: str, font, scale: float) -> None:
    x0, y0, x1, y1 = box
    h = y1 - y0
    arrow = max(18, int(h * 0.55))
    wood = (150, 96, 42, 255)
    edge = (92, 56, 22, 255)
    pts = [
        (x0, y0),
        (x1 - arrow, y0),
        (x1, y0 + h // 2),
        (x1 - arrow, y1),
        (x0, y1),
    ]
    draw.polygon(pts, fill=wood, outline=edge)
    draw.line((x0 + 3, y0 + 3, x1 - arrow - 2, y0 + 3), fill=(196, 148, 88, 180), width=2)
    draw.text(((x0 + x1 - arrow) // 2, y0 + h // 2), text, font=font, fill=WHITE, anchor="mm")


_SCENE_CACHE: dict[tuple[int, int], object] = {}


def _bmt_scene_canvas(width: int, height: int):
    from PIL import Image, ImageDraw, ImageFilter

    from bmt_voice_studio.resources import _first_existing

    key = (int(width), int(height))
    cached = _SCENE_CACHE.get(key)
    if cached is not None:
        return cached.copy()

    img = Image.new("RGBA", (width, height), (255, 255, 255, 255))
    scene = _first_existing("bmt_thumbnail_scene.png")
    dest_h = int(height * 0.58)
    dest_y = height - dest_h
    placed = False
    if scene and Path(scene).is_file():
        try:
            photo = Image.open(scene).convert("RGBA")
            # Lower-left photographic band only — skip baked header, quote, and signposts.
            crop_top = int(photo.height * 0.70)
            crop_right = int(photo.width * 0.55)
            band = photo.crop((0, crop_top, max(crop_right, 8), photo.height))
            scale = max(width / max(1, band.width), dest_h / max(1, band.height))
            nw, nh = int(band.width * scale), int(band.height * scale)
            band = band.resize((max(width, nw), max(dest_h, nh)), Image.Resampling.LANCZOS)
            x0 = max(0, (band.width - width) // 2)
            y0 = max(0, band.height - dest_h)
            img.paste(band.crop((x0, y0, x0 + width, y0 + dest_h)), (0, dest_y))
            placed = True
        except Exception:
            placed = False
    if not placed:
        _warm_glow(img, width, height)
        hill = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        hd = ImageDraw.Draw(hill)
        hd.ellipse((int(-width * 0.1), int(height * 0.62), int(width * 0.7), int(height * 1.2)), fill=(46, 72, 36, 255))
        hd.ellipse((int(width * 0.35), int(height * 0.68), int(width * 1.15), int(height * 1.25)), fill=(28, 52, 28, 255))
        hd.ellipse((int(width * 0.55), int(-height * 0.02), int(width * 1.2), int(height * 0.28)), fill=(214, 132, 58, 90))
        img.alpha_composite(hill.filter(ImageFilter.GaussianBlur(radius=max(4, width // 80))))

    wash = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    wd = ImageDraw.Draw(wash)
    fade = int(height * 0.14)
    for i in range(fade):
        alpha = int(255 * (1 - (i / max(1, fade))))
        y = dest_y + i
        wd.rectangle((0, y, width, y + 1), fill=(255, 255, 255, alpha))
    img.alpha_composite(wash)
    _SCENE_CACHE[key] = img.copy()
    return img


def _render_bmt_flyer_card(
    project: VideoProject | None,
    dest: Path,
    *,
    width: int = CANVAS_WIDTH,
    height: int = CANVAS_HEIGHT,
) -> Path:
    """9:16 thumbnail / intro matching the Believers Manna Today flyer template."""
    from PIL import Image, ImageDraw

    from bmt_voice_studio.video.brand_strings import brand_strings
    from bmt_voice_studio.video.title_cards import _prepare_logo, load_font, wrap_and_shrink

    labels = brand_strings(getattr(project, "language", None) if project else None)
    width = even_dim(width)
    height = even_dim(height)
    img = _bmt_scene_canvas(width, height)
    draw = ImageDraw.Draw(img)
    scale = width / CANVAS_WIDTH
    sx, sy, sw, sh = safe_rect(width, height)
    cx = width // 2
    y = sy + int(18 * scale)

    logo = packaged_logo_path()
    if logo and Path(logo).is_file():
        try:
            mark = _prepare_logo(Path(logo), max_w=int(220 * scale), max_h=int(118 * scale))
            img.alpha_composite(mark, (cx - mark.width // 2, y))
            y += mark.height + int(8 * scale)
        except Exception:
            pass

    font_believers = load_font(max(36, int(78 * scale)), bold=True)
    font_manna = load_font(max(32, int(70 * scale)), bold=True)
    line1 = labels["title_line1"]
    line2 = labels["title_line2"]
    for _ in range(2):
        bb1 = draw.textbbox((0, 0), line1, font=font_believers)
        bb2 = draw.textbbox((0, 0), line2, font=font_manna)
        if max(bb1[2] - bb1[0], bb2[2] - bb2[0]) <= sw - int(36 * scale):
            break
        font_believers = load_font(max(26, int(58 * scale)), bold=True)
        font_manna = load_font(max(24, int(52 * scale)), bold=True)
    draw.text((cx, y), line1, font=font_believers, fill=NAVY_TEXT, anchor="mt")
    y += int(82 * scale)
    draw.text((cx, y), line2, font=font_manna, fill=MAROON, anchor="mt")
    y += int(92 * scale)

    bar_w = min(sw, int(920 * scale))
    bar_x = (width - bar_w) // 2
    bar_h = int(70 * scale)
    _rounded_rect(draw, (bar_x, y, bar_x + bar_w, y + bar_h), int(20 * scale), NAVY)
    font_kicker = load_font(max(16, int(28 * scale)), bold=True)
    kicker = labels["daily_devotional"]
    tw = draw.textbbox((0, 0), kicker, font=font_kicker)
    kw = tw[2] - tw[0]
    if kw > bar_w - int(90 * scale):
        font_kicker = load_font(max(13, int(22 * scale)), bold=True)
        tw = draw.textbbox((0, 0), kicker, font=font_kicker)
        kw = tw[2] - tw[0]
    draw.text((cx, y + bar_h // 2), kicker, font=font_kicker, fill=WHITE, anchor="mm")
    dash_w = int(26 * scale)
    dash_h = max(4, int(6 * scale))
    dash_y = y + bar_h // 2 - dash_h // 2
    gap = int(22 * scale)
    draw.rectangle((cx - kw // 2 - gap - dash_w, dash_y, cx - kw // 2 - gap, dash_y + dash_h), fill=RED)
    draw.rectangle((cx + kw // 2 + gap, dash_y, cx + kw // 2 + gap + dash_w, dash_y + dash_h), fill=RED)
    y += bar_h + int(16 * scale)

    author_h = int(118 * scale)
    _rounded_rect(draw, (bar_x, y, bar_x + bar_w, y + author_h), int(20 * scale), NAVY)
    draw.rounded_rectangle(
        (bar_x, y, bar_x + bar_w, y + author_h),
        radius=int(20 * scale),
        outline=GOLD_BORDER,
        width=max(2, int(3 * scale)),
    )
    badge_r = int(40 * scale)
    _draw_flag_badge(img, bar_x + int(70 * scale), y + author_h // 2, badge_r)
    font_written = load_font(max(14, int(22 * scale)), bold=False)
    tx = bar_x + int(130 * scale)
    draw.text((tx, y + int(22 * scale)), labels["written_by"], font=font_written, fill=WHITE)
    author_lines, font_author = wrap_and_shrink(
        draw, AUTHOR, bar_w - int(170 * scale), start_size=int(26 * scale), min_size=14, max_lines=2, bold=True
    )
    ay = y + int(54 * scale)
    for line in author_lines:
        draw.text((tx, ay), line, font=font_author, fill=GOLD_AUTHOR)
        ay += int(30 * scale)
    y += author_h + int(28 * scale)

    quote, theme, pretty_date = flyer_copy(project)
    quote = " ".join(quote.upper().split())
    quote_w = bar_w - int(24 * scale)
    lines, font_quote = wrap_and_shrink(
        draw, quote, quote_w, start_size=int(42 * scale), min_size=18, max_lines=6, bold=True
    )
    line_h = int(48 * scale)
    panel_h = line_h * max(1, len(lines)) + int(28 * scale)
    panel = Image.new("RGBA", (bar_w, panel_h), (0, 0, 0, 0))
    pd = ImageDraw.Draw(panel)
    pd.rounded_rectangle((0, 0, bar_w - 1, panel_h - 1), radius=int(18 * scale), fill=(236, 244, 252, 230))
    img.alpha_composite(panel, (bar_x, y))
    qy = y + int(16 * scale)
    for line in lines:
        draw.text((cx, qy), line, font=font_quote, fill=NAVY_TEXT, anchor="mt")
        qy += line_h
    y = qy + int(16 * scale)

    chip_pad = int(16 * scale)
    font_meta = load_font(max(14, int(22 * scale)), bold=True)
    meta_lines: list[tuple[str, str]] = []
    if theme:
        meta_lines.append(("target", theme))
    if pretty_date:
        meta_lines.append(("cal", pretty_date))
    if meta_lines:
        chip_h = int(36 * scale) * len(meta_lines) + chip_pad * 2
        widest = 0
        for _, text in meta_lines:
            bb = draw.textbbox((0, 0), text, font=font_meta)
            widest = max(widest, bb[2] - bb[0])
        chip_w = min(sw, widest + int(70 * scale) + chip_pad * 2)
        chip_x = max(bar_x, min(width - sx - chip_w, cx - int(40 * scale)))
        chip = Image.new("RGBA", (chip_w, chip_h), (0, 0, 0, 0))
        cd = ImageDraw.Draw(chip)
        cd.rounded_rectangle((0, 0, chip_w - 1, chip_h - 1), radius=int(14 * scale), fill=(255, 255, 255, 200))
        img.alpha_composite(chip, (chip_x, y))
        my = y + chip_pad + int(16 * scale)
        icon_x = chip_x + int(28 * scale)
        text_x = chip_x + int(56 * scale)
        for kind, text in meta_lines:
            if kind == "target":
                _draw_target(draw, icon_x, my, int(28 * scale), INK)
            else:
                _draw_calendar(draw, icon_x, my, int(26 * scale), INK)
            draw.text((text_x, my), text, font=font_meta, fill=INK, anchor="lm")
            my += int(36 * scale)

    post_x = int(width * 0.58)
    sign_w = int(width * 0.40)
    sign_h = int(46 * scale)
    gap_s = int(12 * scale)
    stack_h = 4 * sign_h + 3 * gap_s
    sign_top = height - int(70 * scale) - stack_h
    font_sign = load_font(max(12, int(18 * scale)), bold=True)
    post_w = max(10, int(14 * scale))
    draw.rectangle(
        (post_x + int(18 * scale), sign_top - int(8 * scale), post_x + int(18 * scale) + post_w, height - int(36 * scale)),
        fill=(96, 62, 28, 255),
    )
    for i, label in enumerate(FLYER_SIGNPOSTS):
        sy0 = sign_top + i * (sign_h + gap_s)
        _draw_wood_sign(
            draw,
            (post_x, sy0, post_x + sign_w, sy0 + sign_h),
            label,
            font_sign,
            scale,
        )

    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(dest, "PNG")
    return dest


def render_locked_intro_card(
    project: VideoProject | None,
    dest: Path,
    *,
    width: int = CANVAS_WIDTH,
    height: int = CANVAS_HEIGHT,
) -> Path:
    """9:16 intro + thumbnail. BMT uses the flyer template; HHR keeps the green card."""
    from bmt_voice_studio.config.product import is_hhr

    product = getattr(project, "product_mode", None) if project else None
    if is_hhr(product):
        return _render_hhr_intro_card(project, dest, width=width, height=height)
    return _render_bmt_flyer_card(project, dest, width=width, height=height)


def embed_locked_artwork(
    mp3_path: Path | str,
    jpeg_bytes: bytes,
    *,
    title: str = "",
    date_label: str = "",
    product: str | None = None,
) -> bool:
    """Attach 9:16 cover art so players/WhatsApp show the locked card, not a generated still."""
    path = Path(mp3_path)
    if not path.is_file() or path.suffix.lower() != ".mp3":
        return False
    try:
        from mutagen.id3 import APIC, ID3, TALB, TIT2, TPE1, ID3NoHeaderError

        try:
            tags = ID3(str(path))
        except ID3NoHeaderError:
            tags = ID3()
        tags.delall("APIC")
        tags.add(
            APIC(
                encoding=3,
                mime="image/jpeg",
                type=3,
                desc="Cover",
                data=jpeg_bytes,
            )
        )
        if title:
            tags.delall("TIT2")
            tags.add(TIT2(encoding=3, text=title))
        tags.delall("TPE1")
        tags.add(TPE1(encoding=3, text=AUTHOR))
        tags.delall("TALB")
        from bmt_voice_studio.config.product import is_hhr

        album = (
            "Hope & Healing Africa — RUHUKA UMUTIMA"
            if is_hhr(product)
            else "Believers Manna Today"
        )
        tags.add(TALB(encoding=3, text=f"{album} {date_label}".strip()))
        tags.save(str(path), v2_version=3)
        return True
    except Exception:
        return False


def locked_card_jpeg_bytes(project: VideoProject | None, *, width: int = CANVAS_WIDTH, height: int = CANVAS_HEIGHT) -> bytes:
    from io import BytesIO

    from PIL import Image

    tmp = Path.cwd() / "_bmt_locked_tmp.png"
    try:
        from bmt_voice_studio.config.paths import cache_dir

        tmp = cache_dir() / "locked_artwork.png"
    except Exception:
        pass
    png = render_locked_intro_card(project, tmp, width=width, height=height)
    im = Image.open(png).convert("RGB")
    buf = BytesIO()
    im.save(buf, "JPEG", quality=90)
    return buf.getvalue()
