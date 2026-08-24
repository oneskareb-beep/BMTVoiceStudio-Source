"""Tests for speaker parser."""

from bmt_voice_studio.core.models import Speaker
from bmt_voice_studio.core.parser import parse_speaker_script


def test_male_female_alternation():
    text = "Hello male\n{\nFemale part\n}\nMale again"
    result = parse_speaker_script(text)
    assert result.ok
    assert len(result.segments) == 3
    assert result.segments[0].speaker == Speaker.MALE
    assert result.segments[1].speaker == Speaker.FEMALE
    assert result.segments[2].speaker == Speaker.MALE
    assert result.segments[0].index == 1
    assert "Female" in result.segments[1].text


def test_unmatched_open_brace():
    result = parse_speaker_script("Hello { unfinished")
    assert not result.ok
    assert any("Unmatched opening" in e.message for e in result.errors)


def test_unmatched_close_brace():
    result = parse_speaker_script("Hello } there")
    assert not result.ok
    assert any("Unmatched closing" in e.message for e in result.errors)


def test_nested_braces():
    result = parse_speaker_script("A { B { C } D }")
    assert not result.ok
    assert any("Nested" in e.message for e in result.errors)


def test_segment_ordering_labels():
    text = "One\n{Two}\nThree\n{Four}"
    result = parse_speaker_script(text)
    assert [s.label for s in result.segments] == [
        "01 MALE",
        "02 FEMALE",
        "03 MALE",
        "04 FEMALE",
    ]


def test_empty_script():
    result = parse_speaker_script("   ")
    assert not result.ok


def test_male_only():
    result = parse_speaker_script("Only male narration here.")
    assert result.ok
    assert len(result.segments) == 1
    assert result.segments[0].speaker == Speaker.MALE
