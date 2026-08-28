"""BMT flyer thumbnail template + East African Swahili voices."""

from __future__ import annotations

from pathlib import Path

from bmt_voice_studio.config.presets import BMT_SWAHILI
from bmt_voice_studio.config.swahili_tts import (
    SWAHILI_FEMALE_VOICE,
    SWAHILI_MALE_VOICE,
    remap_swahili_voice,
)
from bmt_voice_studio.video.locked_card import FLYER_SIGNPOSTS, flyer_copy, render_locked_intro_card
from bmt_voice_studio.video.models import VideoProject


def test_swahili_production_is_east_african_kenya():
    assert BMT_SWAHILI.male_voice == SWAHILI_MALE_VOICE
    assert BMT_SWAHILI.female_voice == SWAHILI_FEMALE_VOICE
    assert BMT_SWAHILI.language.startswith("sw-KE")
    assert remap_swahili_voice("sw-TZ-DaudiNeural") == "sw-KE-RafikiNeural"
    assert remap_swahili_voice("sw-TZ-RehemaNeural") == "sw-KE-ZuriNeural"


def test_tanzania_saved_approval_upgrades(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "la"))
    from bmt_voice_studio.config.paths import local_appdata
    from bmt_voice_studio.daily.regional_approval import (
        approved_voices_for,
        load_regional_approvals,
        save_regional_approvals,
    )

    data = {
        "languages": {
            "sw": {
                "status": "approved",
                "approved_by_user": True,
                "approved_male": "sw-TZ-DaudiNeural",
                "approved_female": "sw-TZ-RehemaNeural",
                "male_voice": "sw-TZ-DaudiNeural",
                "female_voice": "sw-TZ-RehemaNeural",
                "fallback_locale": "sw-TZ",
            }
        }
    }
    path = local_appdata() / "regional_voice_approval.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    import json

    path.write_text(json.dumps(data), encoding="utf-8")
    loaded = load_regional_approvals()
    sw = loaded["languages"]["sw"]
    assert sw["approved_male"] == "sw-KE-RafikiNeural"
    assert sw["approved_female"] == "sw-KE-ZuriNeural"
    assert sw["fallback_locale"] == "sw-KE"
    assert approved_voices_for("sw") == ("sw-KE-RafikiNeural", "sw-KE-ZuriNeural")


def test_flyer_copy_uses_verse_theme_and_date():
    project = VideoProject(
        topic="Living every day for eternity",
        memory_verse="This life is temporary, but eternity is forever.",
        devotional_date="2026-08-29",
    )
    quote, theme, pretty = flyer_copy(project)
    assert "temporary" in quote.lower()
    assert "eternity" in theme.lower()
    assert "Saturday" in pretty
    assert "29th" in pretty
    assert "August" in pretty


def test_flyer_thumbnail_matches_template_chrome(tmp_path: Path):
    from PIL import Image

    dest = tmp_path / "flyer.png"
    project = VideoProject(
        topic="Living every day for eternity",
        memory_verse="This life is temporary, but eternity is forever. Set your mind on things above.",
        week_focus="Heavenly focus",
        devotional_date="2026-08-29",
        language="en",
    )
    render_locked_intro_card(project, dest, width=540, height=960)
    assert dest.is_file()
    im = Image.open(dest).convert("RGB")
    assert im.size == (540, 960)
    px = im.load()
    navy = 0
    white = 0
    wood = 0
    for y in range(0, 420):
        for x in range(40, 500, 4):
            r, g, b = px[x, y]
            if r < 45 and g < 70 and b > 50:
                navy += 1
            if r > 230 and g > 230 and b > 230:
                white += 1
    for y in range(700, 940, 2):
        for x in range(300, 530, 3):
            r, g, b = px[x, y]
            if 90 < r < 200 and 40 < g < 130 and b < 90:
                wood += 1
    assert navy > 80
    assert white > 200
    assert wood > 20
    assert FLYER_SIGNPOSTS[0] == "HEAVENLY FOCUS"
