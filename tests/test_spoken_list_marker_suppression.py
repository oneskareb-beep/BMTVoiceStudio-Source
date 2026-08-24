"""Spoken list-marker suppression (TTS only; SOURCE unchanged)."""

from __future__ import annotations

from bmt_voice_studio.core.parser import parse_speaker_script_source
from bmt_voice_studio.core.text_prepare import (
    count_english_number_contamination,
    count_list_marker_starts,
    prepare_tts_text,
    suppress_spoken_list_markers,
)


def test_fr_premiere_removed():
    assert suppress_spoken_list_markers("Premièrement. Père, merci...", "fr") == "Père, merci..."


def test_fr_deuxieme_removed():
    assert suppress_spoken_list_markers("Deuxièmement. Seigneur...", "fr") == "Seigneur..."


def test_fr_troisieme_removed():
    assert suppress_spoken_list_markers("Troisièmement. Saint-Esprit...", "fr") == "Saint-Esprit..."


def test_fr_short_cardinal_removed():
    assert suppress_spoken_list_markers("Un. Père...", "fr") == "Père..."
    assert suppress_spoken_list_markers("Deux. Seigneur...", "fr") == "Seigneur..."


def test_en_number_one_removed():
    assert suppress_spoken_list_markers("Number one. Father, thank You...", "en") == (
        "Father, thank You..."
    )


def test_en_first_removed():
    assert suppress_spoken_list_markers("First. Evaluate your current priorities...", "en") == (
        "Evaluate your current priorities..."
    )


def test_digit_list_removed_en():
    assert suppress_spoken_list_markers("1. Pray for wisdom.", "en") == "Pray for wisdom."


def test_digit_list_removed_fr():
    assert suppress_spoken_list_markers("1. Priez pour la sagesse.", "fr") == "Priez pour la sagesse."


def test_prose_safety_french():
    prose = "Il faut premièrement comprendre la volonté de Dieu."
    assert suppress_spoken_list_markers(prose, "fr") == prose


def test_prose_safety_english_content():
    assert (
        suppress_spoken_list_markers("Matthew chapter six, verse thirty-three.", "en")
        == "Matthew chapter six, verse thirty-three."
    )
    assert suppress_spoken_list_markers("August 14, 2026", "en") == "August 14, 2026"
    assert suppress_spoken_list_markers("Call +234 800 000 0000", "en") == "Call +234 800 000 0000"
    assert suppress_spoken_list_markers("There were three people.", "en") == "There were three people."


def test_un_homme_not_stripped():
    assert suppress_spoken_list_markers("Un homme vint à la porte.", "fr") == "Un homme vint à la porte."


def test_brace_segmentation_stable():
    source = (
        "Intro male.\n"
        "{Premièrement. Prière femme.}\n"
        "Number one. Male item.\n"
        "{First. Female item.}"
    )
    parsed = parse_speaker_script_source(source)
    assert parsed.ok
    assert len(parsed.segments) == 4
    spoken = [
        suppress_spoken_list_markers(s.text, "fr" if i in (1,) else "en")
        for i, s in enumerate(parsed.segments)
    ]
    # Segment 1 is French-style marker inside braces — use fr for that segment text
    assert suppress_spoken_list_markers(parsed.segments[1].text, "fr").startswith("Prière")
    assert suppress_spoken_list_markers(parsed.segments[2].text, "en").startswith("Male item")
    assert suppress_spoken_list_markers(parsed.segments[3].text, "en").startswith("Female item")
    assert parsed.segments[1].text.startswith("Premièrement")
    assert len(spoken) == 4


def test_prepare_tts_strips_markers_strict():
    assert prepare_tts_text(
        "Premièrement. Père...", language="fr-FR", strict_source_mode=True
    ).startswith("Père")
    assert prepare_tts_text(
        "Number one. Father...", language="en", strict_source_mode=True
    ).startswith("Father")
    assert "Premièrement" not in prepare_tts_text(
        "Premièrement. Père...", language="fr-FR", strict_source_mode=True
    )
    assert "Number one" not in prepare_tts_text(
        "Number one. Father...", language="en", strict_source_mode=True
    )


def test_no_english_contamination_in_french_spoken():
    out = suppress_spoken_list_markers(
        "Premièrement. A\nDeuxièmement. B\nTroisièmement. C", "fr"
    )
    assert count_english_number_contamination(out) == 0
    assert count_list_marker_starts(out, "fr") == 0
    assert "Un." not in out
    assert "Deux." not in out
