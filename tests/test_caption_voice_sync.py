"""Voice-matched caption timing (Edge word clocks + segment probes)."""

from __future__ import annotations

from bmt_voice_studio.video.captions import caption_cues_from_segments, sentences_from_word_timings


def test_sentences_from_word_timings_groups_punctuation():
    words = [
        {"text": "Seek", "start": 0.0, "end": 0.2},
        {"text": "first.", "start": 0.2, "end": 0.5},
        {"text": "Trust", "start": 0.6, "end": 0.9},
        {"text": "God.", "start": 0.9, "end": 1.2},
    ]
    sents = sentences_from_word_timings(words)
    assert len(sents) == 2
    assert sents[0][0].startswith("Seek")
    assert sents[0][1] == 0.0
    assert sents[1][0].startswith("Trust")
    assert sents[1][2] == 1.2


def test_caption_cues_prefer_word_timings_over_equal_slots():
    segs = [
        {
            "text": "Seek first the kingdom. Trust the Lord always.",
            "duration": 4.0,
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
    cues = caption_cues_from_segments(segs, audio_duration=4.0, language="en")
    assert cues
    # School text: one sentence per cue; second cue tracks the late spoken end.
    assert len(cues) == 2
    assert cues[1].end >= 3.5
    assert "Seek" in cues[0].text
    assert "Trust" in cues[1].text


def test_long_segment_keeps_more_caption_time_than_short():
    segs = [
        {"text": "This is a long spoken sentence that takes eight seconds.", "duration": 8.0},
        {"text": "Short one.", "duration": 2.0},
    ]
    cues = caption_cues_from_segments(segs, pause_sec=0.0, audio_duration=10.0, language="en")
    assert len(cues) == 2
    assert (cues[0].end - cues[0].start) > (cues[1].end - cues[1].start) * 2.5
