"""French spoken sanitizer — prevent English leakage in spoken TTS."""

from __future__ import annotations

from bmt_voice_studio.core.text_prepare import (
    count_system_english_contamination,
    sanitize_french_spoken_for_tts,
)


def test_sanitize_removes_en_anglais_before_blessing():
    source = (
        "Ce dévotionnel est disponible en anglais et en français.\n\n"
        "Demeurez bénis."
    )
    spoken, n = sanitize_french_spoken_for_tts(source)
    assert n >= 1
    assert "en anglais" not in spoken.lower()
    assert "version anglaise" in spoken.lower()
    assert count_system_english_contamination(spoken) == 0
    # SOURCE-like original still has the phrase — sanitizer is spoken-only.
    assert "en anglais" in source.lower()


def test_nous_croyons_segment_clean():
    spoken = (
        "Nous croyons que ce dévotionnel vous a bénis.\n\n"
        "Nous vous invitons à faire de Jésus-Christ le Seigneur de votre vie."
    )
    out, n = sanitize_french_spoken_for_tts(spoken)
    assert n == 0
    assert out == spoken
    assert count_system_english_contamination(out) == 0


def test_sanitize_rewrites_english_headers_spoken_only():
    source = "BELIEVERS MANNA TODAY\nRemain blessed\nWe believe"
    spoken, n = sanitize_french_spoken_for_tts(source)
    assert n >= 3
    assert "BELIEVERS MANNA TODAY" not in spoken.upper()
    assert "Remain blessed" not in spoken
    assert "We believe" not in spoken
    assert "Manne des croyants" in spoken
    assert "Demeurez bénis" in spoken
    assert count_system_english_contamination(spoken) == 0
    assert "BELIEVERS MANNA TODAY" in source
