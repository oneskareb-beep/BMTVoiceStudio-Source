"""v1.3.36 — localized-topic, moving-text, paysage-motion and first-frame regressions."""

from __future__ import annotations

from pathlib import Path

from bmt_voice_studio.video.captions import CaptionCue, write_ass
from bmt_voice_studio.video.discovery import extract_metadata
from bmt_voice_studio.video.ffmpeg_renderer import (
    BAND_KEN_BURNS_AMOUNT,
    INTRO_FADE_IN_SEC,
    ken_burns_filter,
)
from bmt_voice_studio.video.meditation_paysage import default_paysage_items
from bmt_voice_studio.video.models import AnimationMode, FitMode


def test_unlabelled_text_never_becomes_topic():
    # Headers/body lines are not a trustworthy substitute for the real translated topic.
    assert extract_metadata("BELIEVERS MANNA TODAY\nMemory Verse\nMatthew 6:33\n")["topic"] == ""
    assert extract_metadata("MANNE DES CROYANTS\nVerset à mémoriser\nMatthieu 6:33\n")["topic"] == ""
    assert extract_metadata("IBADA YA KILA SIKU\nAya ya Kukariri\nMathayo 6:33\n")["topic"] == ""
    assert extract_metadata("MANÁ DIÁRIO\nVersículo para Memorizar\nMateus 6:33\n")["topic"] == ""


def test_explicit_localized_topics_stay_language_specific():
    assert extract_metadata("Topic: Staying Spiritually Alert\n")["topic"] == "Staying Spiritually Alert"
    assert extract_metadata("Thème : Rester spirituellement vigilant\n")["topic"] == "Rester spirituellement vigilant"
    assert extract_metadata("Mada: Kubaki Macho Kiroho\n")["topic"] == "Kubaki Macho Kiroho"
    assert extract_metadata("Tema: Permanecer Espiritualmente Alerta\n")["topic"] == "Permanecer Espiritualmente Alerta"


def test_paysage_stills_use_subtle_motion():
    items = default_paysage_items("fr")
    assert items
    assert items[0].fit_mode == FitMode.BAND.value
    assert items[0].animation_mode == AnimationMode.ZOOM_IN.value
    assert 0.02 <= BAND_KEN_BURNS_AMOUNT <= 0.05


def test_band_ken_burns_keeps_middle_half_locked():
    filt = ken_burns_filter(
        AnimationMode.ZOOM_IN.value,
        duration=5.0,
        fps=30,
        width=1080,
        height=1920,
        fit_mode=FitMode.BAND.value,
        zoom_amount=BAND_KEN_BURNS_AMOUNT,
    )
    # Motion renders to the 960px band first, then pads to the fixed 1080x1920 canvas.
    assert "zoompan" in filt
    assert "s=1080x960" in filt
    assert "pad=1080:1920:0:480" in filt


def test_intro_has_no_black_fade():
    assert INTRO_FADE_IN_SEC == 0.0
    filt = ken_burns_filter(
        AnimationMode.ZOOM_IN.value,
        duration=10.0,
        fps=30,
        width=1080,
        height=1920,
        fade_in=INTRO_FADE_IN_SEC,
    )
    assert "fade=t=in" not in filt


def test_devotional_caption_motion_preserves_timing_and_safe_region(tmp_path: Path):
    cues = [CaptionCue(start=1.25, end=4.75, text="Stay spiritually alert.", language="en")]
    dest = tmp_path / "moving.ass"
    write_ass(cues, dest, width=1080, height=1920, motion=True)
    blob = dest.read_text(encoding="utf-8")
    assert "Dialogue: 0,0:00:01.25,0:00:04.75" in blob
    assert r"\move(540," in blob
    assert r"\fad(120,120)" in blob
    # 1920px canvas with 10% lower margin gives anchor 1728; motion stays
    # entirely inside that safe margin and glides upward by only ~15px.
    assert ",1728,540,1713," in blob
