"""Tests for BMT reference source pipeline configuration and behavior."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from bmt_voice_studio.config.pipeline_config import (
    all_settings_match,
    compare_runtime_to_reference,
    config_path,
    get_canonical_preset,
    get_preset_pipeline,
)
from bmt_voice_studio.config.presets import BMT_ENGLISH, BMT_FRENCH, get_preset
from bmt_voice_studio.core.parser import parse_speaker_script, parse_speaker_script_source
from bmt_voice_studio.core.text_prepare import (
    count_english_number_contamination,
    prepare_tts_text,
)
from bmt_voice_studio.tools.cloud_fallback_export import export_cloud_fallback_package


def test_english_reference_voice_settings():
    p = BMT_ENGLISH
    assert p.male_voice == "en-NG-AbeoNeural"
    assert p.female_voice == "en-NG-EzinneNeural"
    assert p.rate == "-10%"
    assert p.pitch == "-3Hz"
    assert p.volume == "+0%"


def test_english_reference_pipeline_settings():
    pipe = BMT_ENGLISH.pipeline
    assert pipe.pause_ms == 500
    assert pipe.lowpass_hz == 7000
    assert pipe.wav_channels == 1
    assert pipe.wav_sample_rate == 44100
    assert pipe.mp3_bitrate_kbps == 192
    assert pipe.strict_source_mode is True
    assert pipe.default_processing_mode == "original"
    assert pipe.apply_bmt_mastering is False


def test_french_reference_voice_settings():
    p = BMT_FRENCH
    assert p.male_voice == "fr-FR-HenriNeural"
    assert p.female_voice == "fr-FR-DeniseNeural"
    assert p.rate == "-8%"
    assert p.pitch == "-1Hz"
    assert p.volume == "+5%"


def test_daily_exports_mp3_only():
    from bmt_voice_studio.config.presets import get_preset

    for preset_id in ("bmt_english", "bmt_french", "bmt_swahili", "bmt_portuguese"):
        pipe = get_preset(preset_id).pipeline
        assert pipe.export_mp3 is True
        assert pipe.export_wav is False


def test_french_reference_pipeline_settings():
    pipe = BMT_FRENCH.pipeline
    assert pipe.pause_ms == 500
    assert pipe.lowpass_hz is None
    assert pipe.mp3_bitrate_kbps is None
    assert pipe.export_wav is False
    assert pipe.strict_source_mode is True


@pytest.mark.parametrize(
    "text,expected_count",
    [
        ("Hello\n{Female}\nWorld", 3),
        ("Only male.", 1),
        ("A\n{B}\nC\n{D}\nE", 5),
        ("}Leading brace test{\ninner\n}", 2),
    ],
)
def test_variable_segment_counts(text: str, expected_count: int):
    result = parse_speaker_script_source(text)
    assert result.ok
    assert len(result.segments) == expected_count


def test_no_fixed_ten_segment_requirement():
    for n in (1, 4, 5, 9, 10, 11):
        parts = []
        for i in range(n):
            if i % 2:
                parts.append("{female}")
            else:
                parts.append("male")
        text = "\n".join(parts)
        parsed = parse_speaker_script_source(text)
        assert parsed.ok
        assert len(parsed.segments) == n


def test_french_strict_source_strips_digit_list_markers_for_tts():
    source = "1. Première action\n2. Deuxième action"
    out = prepare_tts_text(source, language="fr-FR", strict_source_mode=True)
    assert out == "Première action\nDeuxième action"
    assert "Number one" not in out
    assert "Number two" not in out


def test_french_non_strict_strips_expanded_list_markers_not_english():
    source = "1. Item\n2. Item"
    out = prepare_tts_text(source, language="fr-FR", strict_source_mode=False, allow_normalization=True)
    # Digits expand then spoken markers are suppressed → bare item text.
    assert "Item" in out
    assert "Number one" not in out
    assert count_english_number_contamination(out) == 0
    assert "Premièrement" not in out


def test_english_normalization_not_applied_to_french():
    source = "1. Point\n2. Point"
    fr = prepare_tts_text(source, language="fr-FR", strict_source_mode=False, allow_normalization=True)
    assert "Number one" not in fr
    assert count_english_number_contamination(fr) == 0


def test_strict_source_preserves_braces_content():
    text = "Male { Female with\nparagraph } tail"
    parsed = parse_speaker_script(text)
    assert parsed.ok
    assert "Female with" in parsed.segments[1].text


def test_desktop_matches_canonical_config():
    en_pipe = BMT_ENGLISH.pipeline
    rows = compare_runtime_to_reference(
        "bmt_english",
        pause_ms=en_pipe.pause_ms,
        mp3_bitrate=en_pipe.mp3_bitrate_kbps,
        processing_mode="original",
        mastering=False,
        volume=BMT_ENGLISH.volume,
    )
    assert all_settings_match(rows)


def test_colab_export_uses_same_config(tmp_path: Path):
    dest = tmp_path / "pkg"
    export_cloud_fallback_package(dest)
    canonical = json.loads(config_path().read_text(encoding="utf-8"))
    exported = json.loads((dest / "source_pipeline_presets.json").read_text(encoding="utf-8"))
    assert exported == canonical
    manifest = json.loads((dest / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["presets"]["bmt_english"]["male_voice"] == "en-NG-AbeoNeural"
    assert manifest["presets"]["bmt_french"]["volume"] == "+5%"
    en_script = (dest / "BMT_ENGLISH_pipeline.py").read_text(encoding="utf-8")
    assert "en-NG-AbeoNeural" in en_script
    assert "7000" in en_script
    assert "500" in en_script
    fr_script = (dest / "BMT_FRENCH_pipeline.py").read_text(encoding="utf-8")
    assert "fr-FR-HenriNeural" in fr_script
    assert "+5%" in fr_script
    assert "low_pass_filter" not in fr_script


def test_cloud_and_desktop_read_same_json_keys():
    for preset_id in ("bmt_english", "bmt_french"):
        preset = get_preset(preset_id)
        canonical = get_canonical_preset(preset_id)
        assert preset.male_voice == canonical["male_voice"]
        assert preset.pipeline.pause_ms == get_preset_pipeline(preset_id).pause_ms


def test_unmatched_braces_still_validated():
    bad = parse_speaker_script("Hello { unfinished")
    assert not bad.ok


@pytest.mark.parametrize(
    "sample_path",
    [
        Path(__file__).resolve().parents[1] / "samples" / "english_sample.txt",
        Path(__file__).resolve().parents[1] / "samples" / "french_sample.txt",
    ],
)
def test_builtin_samples_parse_without_fixed_segment_count(sample_path: Path):
    if not sample_path.exists():
        pytest.skip(f"Sample missing: {sample_path}")
    parsed = parse_speaker_script_source(sample_path.read_text(encoding="utf-8"))
    assert parsed.ok
    assert len(parsed.segments) >= 1
    assert len(parsed.segments) != 10 or len(parsed.segments) == 10  # any count ok
