"""School-text captions, mid-band paysage, and eng/fra/port language codes."""

from __future__ import annotations

from bmt_voice_studio.video.captions import (
    MIN_SCHOOL_CUE_SEC,
    SENTENCES_PER_CUE,
    caption_cues_from_segments,
)
from bmt_voice_studio.video.discovery import extract_metadata
from bmt_voice_studio.video.geometry import CANVAS_HEIGHT, CANVAS_WIDTH, ffmpeg_mid_band_filter
from bmt_voice_studio.video.meditation_paysage import default_paysage_items, paysage_still_path
from bmt_voice_studio.video.models import FitMode, language_still_code, normalize_language_id


def test_school_text_one_sentence_per_cue():
    assert SENTENCES_PER_CUE == 1
    segs = [
        {
            "text": "Seek first the kingdom. Trust the Lord always.",
            "duration": 5.0,
            "word_timings": [
                {"text": "Seek", "start": 0.0, "end": 0.25},
                {"text": "first", "start": 0.25, "end": 0.45},
                {"text": "the", "start": 0.45, "end": 0.55},
                {"text": "kingdom.", "start": 0.55, "end": 1.0},
                {"text": "Trust", "start": 2.5, "end": 2.8},
                {"text": "the", "start": 2.8, "end": 2.95},
                {"text": "Lord", "start": 2.95, "end": 3.2},
                {"text": "always.", "start": 3.2, "end": 3.9},
            ],
        }
    ]
    cues = caption_cues_from_segments(segs, audio_duration=5.0, language="en")
    assert len(cues) == 2
    assert cues[0].start == 0.0
    assert "Seek" in cues[0].text
    assert "Trust" not in cues[0].text
    assert "Trust" in cues[1].text
    assert cues[0].end - cues[0].start >= MIN_SCHOOL_CUE_SEC - 0.05


def test_school_text_starts_and_finishes_with_voice():
    segs = [
        {"text": "First line spoken.", "duration": 2.2},
        {"text": "Second line spoken.", "duration": 2.2},
    ]
    cues = caption_cues_from_segments(segs, pause_sec=0.0, audio_duration=4.4, language="en")
    assert cues
    assert cues[0].start == 0.0
    assert cues[-1].end == 4.4


def test_fr_pt_topic_labels_extract_like_english():
    fr = extract_metadata("LA MANNE QUOTIDIENNE\nThème : Les priorités du Royaume\n")
    pt = extract_metadata("MANÁ DIÁRIO\nTema: Prioridades do Reino\n")
    en = extract_metadata("BELIEVERS MANNA TODAY\nTopic: Kingdom Priorities\n")
    assert fr["topic"] == "Les priorités du Royaume"
    assert pt["topic"] == "Prioridades do Reino"
    assert en["topic"] == "Kingdom Priorities"


def test_language_codes_eng_fra_port():
    assert normalize_language_id("eng") == "en"
    assert normalize_language_id("fra") == "fr"
    assert normalize_language_id("port") == "pt"
    assert language_still_code("en") == "eng"
    assert language_still_code("fr") == "fra"
    assert language_still_code("pt") == "port"
    assert language_still_code("eng") == "eng"


def test_mid_band_filter_quarters():
    filt = ffmpeg_mid_band_filter(CANVAS_WIDTH, CANVAS_HEIGHT)
    assert "960" in filt or f"{CANVAS_HEIGHT // 2}" in filt
    assert f"pad={CANVAS_WIDTH}:{CANVAS_HEIGHT}" in filt
    assert FitMode.BAND.value == "band"


def test_meditation_paysage_stills_bundled():
    for lang, code in (("en", "eng"), ("fr", "fra"), ("pt", "port")):
        path = paysage_still_path(lang)
        assert path is not None, code
        assert path.is_file()
        assert path.stem == code
    items = default_paysage_items("fr")
    assert items
    assert items[0].fit_mode == FitMode.BAND.value
    assert "fra" in items[0].path.replace("\\", "/")
