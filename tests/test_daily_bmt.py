"""V1.1 Daily BMT workflow tests — no live TTS required."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from bmt_voice_studio.core.hashing import needs_regeneration, segment_cache_hash
from bmt_voice_studio.core.models import Segment, Speaker
from bmt_voice_studio.daily.autosave import (
    clear_draft,
    draft_has_content,
    load_draft,
    load_incomplete,
    mark_incomplete,
    save_draft,
    clear_incomplete,
)
from bmt_voice_studio.daily.history import filter_history, load_history, save_history, upsert_entry
from bmt_voice_studio.daily.layout import ensure_daily_layout, final_paths
from bmt_voice_studio.daily.naming import final_mp3_name, final_wav_name, project_id
from bmt_voice_studio.daily.pipeline import DailyJob, preflight
from bmt_voice_studio.daily.report import write_reports
from bmt_voice_studio.daily.validate import overall_status, validate_daily_script


def test_date_based_naming():
    d = date(2026, 8, 13)
    assert project_id(d) == "BMT_2026_08_13"
    assert final_mp3_name(d, "ENGLISH") == "BMT_13_AUG_2026_ENGLISH_FINAL.mp3"
    assert final_wav_name(d, "FRENCH") == "BMT_13_AUG_2026_FRENCH_FINAL.wav"


def test_dual_language_output_structure(tmp_path: Path):
    d = date(2026, 8, 13)
    root = ensure_daily_layout(d, tmp_path)
    assert (root / "ENGLISH" / "segments").is_dir()
    assert (root / "FRENCH" / "segments").is_dir()
    assert (root / "REPORTS").is_dir()
    assert (root / "SOURCE").is_dir()
    assert root.name == "BMT_2026_08_13"
    assert root.parent.name == "08"
    assert root.parent.parent.name == "2026"
    en_mp3, en_wav = final_paths(root, d, "ENGLISH")
    assert en_mp3.name == "BMT_13_AUG_2026_ENGLISH_FINAL.mp3"
    assert en_wav.parent.name == "ENGLISH"


def test_dual_language_validation():
    ok = validate_daily_script("Hello male\n{\nFemale\n}\nMale again")
    assert ok.ok and ok.segment_count == 3 and ok.male_count == 2 and ok.female_count == 1
    bad = validate_daily_script("Hello { unfinished")
    assert not bad.ok and bad.status == "SCRIPT ERROR"
    empty = validate_daily_script("  ")
    assert empty.status == "EMPTY"


def test_one_language_mode_preflight():
    job = DailyJob(
        date=date(2026, 8, 13),
        english_text="Only english narration.",
        french_text="",
        generate_english=True,
        generate_french=False,
    )
    issues = [i for i in preflight(job) if "French" in i or "English" in i]
    assert not any("English" in i for i in issues)
    both_empty = DailyJob(
        date=date(2026, 8, 13),
        english_text="",
        french_text="",
        generate_english=True,
        generate_french=True,
    )
    issues2 = preflight(both_empty)
    assert any("ENGLISH" in i.upper() for i in issues2)
    assert any("FRENCH" in i.upper() for i in issues2)


def test_daily_autosave_and_recovery(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "la"))
    clear_draft()
    assert load_draft() is None
    save_draft({"english_text": "Hello", "french_text": "{Bonjour}", "date": "2026-08-13"})
    d = load_draft()
    assert draft_has_content(d)
    assert d["english_text"] == "Hello"
    clear_draft()
    assert not draft_has_content(load_draft())


def test_incomplete_marker(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "la"))
    clear_incomplete()
    mark_incomplete({"date": "2026-08-13", "folder": "x"})
    inc = load_incomplete()
    assert inc and inc["date"] == "2026-08-13"
    clear_incomplete()
    assert load_incomplete() is None


def test_production_history_filter(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "la"))
    save_history([])
    upsert_entry({"date": "2026-08-13", "project_id": "BMT_2026_08_13", "status": "COMPLETE", "english": True, "french": True})
    upsert_entry({"date": "2026-07-01", "project_id": "BMT_2026_07_01", "status": "FAILED", "english": False, "french": False})
    all_e = load_history()
    assert len(all_e) == 2
    aug = filter_history(all_e, year=2026, month=8)
    assert len(aug) == 1 and aug[0]["date"] == "2026-08-13"
    failed = filter_history(all_e, status="FAILED")
    assert len(failed) == 1


def test_language_failure_isolation_status():
    assert overall_status(True, False, gen_en=True, gen_fr=True) == "WARNING"
    assert overall_status(True, True, gen_en=True, gen_fr=True) == "COMPLETE"
    assert overall_status(False, False, gen_en=True, gen_fr=True) == "FAILED"
    assert overall_status(True, None, gen_en=True, gen_fr=False) == "COMPLETE"


def test_daily_smart_regeneration_isolation():
    en = Segment(index=1, speaker=Speaker.MALE, text="EN", voice="abeo", rate="-10%", pitch="-3Hz")
    fr = Segment(index=1, speaker=Speaker.MALE, text="FR", voice="remy", rate="-8%", pitch="-1Hz")
    en.cache_hash = segment_cache_hash(en)
    fr.cache_hash = segment_cache_hash(fr)
    en.audio_path = "en.mp3"
    fr.audio_path = "fr.mp3"
    # Changing French text does not invalidate English hash
    fr.text = "FR changed"
    assert not needs_regeneration(en, segment_cache_hash(en))
    assert needs_regeneration(fr, segment_cache_hash(fr))


def test_production_report_generation(tmp_path: Path):
    root = tmp_path / "BMT_2026_08_13"
    md, js = write_reports(
        root,
        {
            "date": "2026-08-13",
            "status": "COMPLETE",
            "pause_ms": 450,
            "english": {"ok": True, "male_voice": "en-NG-AbeoNeural", "segment_count": 10, "mp3_probe": {"duration_sec": 404.1}},
            "french": {"ok": True, "male_voice": "fr-FR-HenriNeural", "segment_count": 10},
        },
    )
    assert md.exists() and js.exists()
    text = md.read_text(encoding="utf-8")
    assert "Abeo" in text and "COMPLETE" in text
    from bmt_voice_studio import __version__

    assert __version__ in text


def test_final_status_calculation():
    assert overall_status(True, True, gen_en=True, gen_fr=True) == "COMPLETE"
    assert overall_status(True, False, gen_en=True, gen_fr=True) == "WARNING"
