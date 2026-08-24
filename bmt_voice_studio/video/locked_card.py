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


def render_locked_intro_card(
    project: VideoProject | None,
    dest: Path,
    *,
    width: int = CANVAS_WIDTH,
    height: int = CANVAS_HEIGHT,
) -> Path:
    """Crisp 9:16 locked brand card. Labels follow project language; topic/date from project."""
    from PIL import Image, ImageDraw

    from bmt_voice_studio.video.brand_strings import brand_strings
    from bmt_voice_studio.video.title_cards import load_font, wrap_and_shrink

    labels = brand_strings(getattr(project, "language", None) if project else None)
    width = even_dim(width)
    height = even_dim(height)
    img = Image.new("RGBA", (width, height), CREAM)
    draw = ImageDraw.Draw(img)
    scale = width / CANVAS_WIDTH
    sx, sy, sw, sh = safe_rect(width, height)
    _warm_glow(img, width, height)

    cx = width // 2
    y = sy + int(28 * scale)

    logo = packaged_logo_path()
    if logo and Path(logo).is_file():
        try:
            from bmt_voice_studio.video.title_cards import _prepare_logo

            mark = _prepare_logo(Path(logo), max_w=int(260 * scale), max_h=int(140 * scale))
            img.alpha_composite(mark, (cx - mark.width // 2, y))
            y += mark.height + int(22 * scale)
        except Exception:
            pass

    font_believers = load_font(max(40, int(86 * scale)), bold=True)
    font_manna = load_font(max(36, int(78 * scale)), bold=True)
    line1 = labels["title_line1"]
    line2 = labels["title_line2"]
    # Shrink if a translated title is wider than the safe column.
    for attempt in range(2):
        bb1 = draw.textbbox((0, 0), line1, font=font_believers)
        bb2 = draw.textbbox((0, 0), line2, font=font_manna)
        if max(bb1[2] - bb1[0], bb2[2] - bb2[0]) <= sw - int(40 * scale) or attempt:
            break
        font_believers = load_font(max(28, int(64 * scale)), bold=True)
        font_manna = load_font(max(26, int(58 * scale)), bold=True)
    draw.text((cx, y), line1, font=font_believers, fill=NAVY_TEXT, anchor="mt")
    y += int(92 * scale)
    draw.text((cx, y), line2, font=font_manna, fill=MAROON, anchor="mt")
    y += int(108 * scale)

    bar_w = min(sw, int(960 * scale))
    bar_x = (width - bar_w) // 2
    bar_h = int(78 * scale)
    _rounded_rect(draw, (bar_x, y, bar_x + bar_w, y + bar_h), int(22 * scale), NAVY)
    font_kicker = load_font(max(18, int(30 * scale)), bold=True)
    kicker = labels["daily_devotional"]
    tw = draw.textbbox((0, 0), kicker, font=font_kicker)
    kw = tw[2] - tw[0]
    kh = tw[3] - tw[1]
    # Slightly smaller font if translated label is wider than the bar.
    if kw > bar_w - int(80 * scale):
        font_kicker = load_font(max(14, int(24 * scale)), bold=True)
        tw = draw.textbbox((0, 0), kicker, font=font_kicker)
        kw = tw[2] - tw[0]
        kh = tw[3] - tw[1]
    draw.text(((width - kw) // 2, y + (bar_h - kh) // 2 - 2), kicker, font=font_kicker, fill=WHITE)
    dash_w = int(28 * scale)
    dash_h = max(4, int(6 * scale))
    dash_y = y + bar_h // 2 - dash_h // 2
    draw.rectangle((bar_x + int(28 * scale), dash_y, bar_x + int(28 * scale) + dash_w, dash_y + dash_h), fill=RED)
    draw.rectangle(
        (bar_x + bar_w - int(28 * scale) - dash_w, dash_y, bar_x + bar_w - int(28 * scale), dash_y + dash_h),
        fill=RED,
    )
    y += bar_h + int(20 * scale)

    author_h = int(150 * scale)
    _rounded_rect(draw, (bar_x, y, bar_x + bar_w, y + author_h), int(22 * scale), NAVY)
    badge_r = int(48 * scale)
    _draw_flag_badge(img, bar_x + int(78 * scale), y + author_h // 2, badge_r)
    font_written = load_font(max(16, int(24 * scale)), bold=False)
    tx = bar_x + int(150 * scale)
    draw.text((tx, y + int(32 * scale)), labels["written_by"], font=font_written, fill=WHITE)
    author_lines, font_author = wrap_and_shrink(
        draw, AUTHOR, bar_w - int(190 * scale), start_size=int(28 * scale), min_size=16, max_lines=2, bold=True
    )
    ay = y + int(68 * scale)
    for line in author_lines:
        draw.text((tx, ay), line, font=font_author, fill=GOLD_AUTHOR)
        ay += int(34 * scale)
    y += author_h + int(36 * scale)

    topic = ""
    pretty_date = ""
    if project is not None:
        topic = (project.topic or project.title or "").strip()
        if project.devotional_date:
            from bmt_voice_studio.video.title_cards import _pretty_date

            pretty_date = (_pretty_date(project) or "").upper()
    if not topic:
        topic = labels["default_topic"]

    panel_h = int(320 * scale)
    panel_top = y
    panel_box = (bar_x, panel_top, bar_x + bar_w, panel_top + panel_h)
    _rounded_rect(draw, panel_box, int(18 * scale), PAPER)
    draw.rounded_rectangle(panel_box, radius=int(18 * scale), outline=NAVY, width=max(3, int(4 * scale)))
    rail = int(16 * scale)
    draw.rectangle((bar_x, panel_top + int(18 * scale), bar_x + rail, panel_top + panel_h - int(18 * scale)), fill=NAVY)
    draw.rectangle(
        (bar_x + bar_w - rail, panel_top + int(18 * scale), bar_x + bar_w, panel_top + panel_h - int(18 * scale)),
        fill=NAVY,
    )

    inner_y = panel_top + int(56 * scale)
    _draw_target(draw, bar_x + int(88 * scale), inner_y + int(48 * scale), int(84 * scale), INK)
    _draw_lock(draw, bar_x + bar_w - int(88 * scale), inner_y + int(48 * scale), int(72 * scale), NAVY)

    font_topic_lbl = load_font(max(18, int(28 * scale)), bold=True)
    label_x = bar_x + int(150 * scale)
    max_topic_w = bar_w - int(280 * scale)
    draw.text((label_x, inner_y), labels["topic"], font=font_topic_lbl, fill=INK)
    lines, font_topic = wrap_and_shrink(
        draw, topic, max_topic_w, start_size=int(40 * scale), min_size=18, max_lines=3, bold=True
    )
    ty = inner_y + int(48 * scale)
    for line in lines:
        draw.text((label_x, ty), line, font=font_topic, fill=TOPIC_BLUE)
        ty += int(46 * scale)

    # Lower 9:16 field — oversized lock so the intro is clearly the locked card, not a photo.
    lock_cy = min(height - int(260 * scale), panel_top + panel_h + int(200 * scale))
    _draw_lock(draw, cx, lock_cy, int(170 * scale), NAVY)
    # Date is required on covers/intros when the project has a production date.
    if pretty_date:
        font_date = load_font(max(18, int(32 * scale)), bold=True)
        draw.text((cx, height - int(88 * scale)), pretty_date, font=font_date, fill=NAVY, anchor="mt")

    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(dest, "PNG")
    return dest


def embed_locked_artwork(mp3_path: Path | str, jpeg_bytes: bytes, *, title: str = "", date_label: str = "") -> bool:
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
        tags.add(TALB(encoding=3, text=f"Believers Manna Today {date_label}".strip()))
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
