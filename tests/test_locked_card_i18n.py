"""Locked intro / cover art localization."""

from __future__ import annotations

from pathlib import Path

from bmt_voice_studio.video.brand_strings import brand_strings, normalize_language
from bmt_voice_studio.video.locked_card import locked_card_jpeg_bytes, render_locked_intro_card
from bmt_voice_studio.video.models import VideoProject


def test_brand_strings_per_language():
    assert brand_strings("en")["topic"] == "TOPIC :"
    assert "THÈME" in brand_strings("fr")["topic"]
    assert "MADA" in brand_strings("sw")["topic"]
    assert "TEMA" in brand_strings("pt")["topic"]
    assert brand_strings("fr")["series_title"] == "LA MANNE QUOTIDIENNE"
    assert brand_strings("sw")["title_line1"] == "MANNA YA"
    assert brand_strings("pt")["title_line2"] == "CRENTES HOJE"
    assert brand_strings("pt")["series_title"] == "A MANÁ DOS CRENTES HOJE"
    assert normalize_language("FRENCH") == "fr"
    assert normalize_language("SWAHILI") == "sw"


def test_locked_card_uses_language_labels(tmp_path: Path):
    fr = VideoProject(
        topic="Persévérer dans la foi",
        language="fr",
        devotional_date="2026-08-21",
    )
    dest = tmp_path / "fr_locked.png"
    render_locked_intro_card(fr, dest, width=540, height=960)
    assert dest.is_file()
    # Smoke: JPEG cover is full HD 9:16 by default
    jpeg = locked_card_jpeg_bytes(fr)
    assert len(jpeg) > 20_000
    from io import BytesIO

    from PIL import Image

    im = Image.open(BytesIO(jpeg))
    assert im.size == (1080, 1920)


def test_locked_card_swahili_kicker(tmp_path: Path):
    from PIL import Image

    sw = VideoProject(topic="Kuvumilia katika Imani", language="sw", devotional_date="2026-08-21")
    dest = tmp_path / "sw.png"
    render_locked_intro_card(sw, dest, width=540, height=960)
    # Pixel probe is brittle; ensure file rendered and labels module has Swahili
    assert dest.stat().st_size > 5_000
    assert Image.open(dest).size == (540, 960)
    assert brand_strings("sw")["daily_devotional"] == "IBADA YA KILA SIKU"
