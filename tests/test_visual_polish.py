"""Visual polish checks: transparent logo, intro hierarchy, verse card layout."""

from __future__ import annotations

from pathlib import Path

import pytest

from bmt_voice_studio.resources import logo_path
from bmt_voice_studio.video.geometry import CANVAS_HEIGHT, CANVAS_WIDTH, safe_rect
from bmt_voice_studio.video.models import VideoProject
from bmt_voice_studio.video.title_cards import (
    knockout_black_background,
    render_intro_card,
    render_outro_card,
    render_template_chip,
    render_verse_card,
)


def test_packaged_logo_is_transparent():
    pytest.importorskip("PIL")
    from PIL import Image

    path = logo_path()
    assert path is not None and path.is_file()
    im = Image.open(path).convert("RGBA")
    w, h = im.size
    px = im.load()
    corners = [px[0, 0], px[w - 1, 0], px[0, h - 1], px[w - 1, h - 1]]
    assert all(a < 40 for (_r, _g, _b, a) in corners)
    assert any(a > 200 and max(r, g, b) > 40 for r, g, b, a in [px[w // 2, h // 2]])


def test_knockout_removes_black_field(tmp_path: Path):
    pytest.importorskip("PIL")
    from PIL import Image, ImageDraw

    src = Image.new("RGBA", (80, 80), (0, 0, 0, 255))
    draw = ImageDraw.Draw(src)
    draw.ellipse((20, 20, 60, 60), fill=(40, 160, 220, 255))
    cleaned = knockout_black_background(src)
    px = cleaned.load()
    assert px[0, 0][3] == 0


def test_intro_and_verse_cards_render(tmp_path: Path):
    pytest.importorskip("PIL")
    from PIL import Image

    project = VideoProject(
        template_id="bmt_classic",
        topic="Kingdom Priorities",
        week_focus="Obedience this week",
        month_theme="Harvest",
        memory_verse="Matthew 6:33 Seek first the kingdom of God and His righteousness.",
        devotional_date="2026-08-14",
        logo_path=str(logo_path() or ""),
    )
    intro = tmp_path / "intro.png"
    verse = tmp_path / "verse.png"
    outro = tmp_path / "outro.png"
    render_intro_card(project, intro)
    render_verse_card(project, verse)
    render_outro_card(project, outro)
    for path in (intro, verse, outro):
        assert path.is_file()
        im = Image.open(path)
        assert im.size == (CANVAS_WIDTH, CANVAS_HEIGHT)
    sx, sy, sw, sh = safe_rect()
    vim = Image.open(verse).convert("RGBA")
    # Verse panel should not live in the bottom 12% of the frame.
    y0 = int(CANVAS_HEIGHT * 0.90)
    px = vim.load()
    opaque = 0
    total = 0
    for y in range(y0, CANVAS_HEIGHT):
        for x in range(CANVAS_WIDTH):
            total += 1
            if px[x, y][3] > 20:
                opaque += 1
    assert opaque < total * 0.35
    assert sy >= 80
    assert sw < CANVAS_WIDTH


def test_template_chips_are_small_and_distinct():
    pytest.importorskip("PIL")
    from bmt_voice_studio.video.models import TEMPLATE_BMT_CLASSIC, TEMPLATE_BMT_MINIMAL, TEMPLATE_BMT_NATURE

    chips = {
        TEMPLATE_BMT_CLASSIC: render_template_chip(TEMPLATE_BMT_CLASSIC),
        TEMPLATE_BMT_NATURE: render_template_chip(TEMPLATE_BMT_NATURE),
        TEMPLATE_BMT_MINIMAL: render_template_chip(TEMPLATE_BMT_MINIMAL),
    }
    sizes = {im.size for im in chips.values()}
    assert sizes == {(44, 78)}
    pixels = {tid: chips[tid].getpixel((22, 70))[:3] for tid in chips}
    assert pixels[TEMPLATE_BMT_CLASSIC] != pixels[TEMPLATE_BMT_NATURE]
    assert pixels[TEMPLATE_BMT_MINIMAL] != pixels[TEMPLATE_BMT_NATURE]
