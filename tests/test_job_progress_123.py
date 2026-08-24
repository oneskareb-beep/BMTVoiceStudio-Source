"""Daily / video job percent mapping."""

from __future__ import annotations

from bmt_voice_studio.core.job_progress import (
    LANGUAGE_POST_STEPS,
    language_job_percent,
    language_work_total,
)


def test_language_work_total_reserves_export_steps():
    assert language_work_total(20) == 20 + LANGUAGE_POST_STEPS
    assert language_work_total(0) == 1 + LANGUAGE_POST_STEPS


def test_export_stage_not_already_100_percent():
    selected = ["en"]
    # Last TTS segment should stay below 100 so join/export still move the bar.
    last_seg = language_job_percent("ENGLISH", 20, language_work_total(20), selected)
    joining = language_job_percent("ENGLISH", 21, language_work_total(20), selected)
    exporting = language_job_percent("ENGLISH", 22, language_work_total(20), selected)
    done = language_job_percent("ENGLISH", 24, language_work_total(20), selected)
    assert last_seg < 100
    assert joining > last_seg
    assert exporting > joining
    assert done == 100


def test_two_language_slots_keep_export_room():
    selected = ["en", "fr"]
    en_export = language_job_percent("ENGLISH", 22, language_work_total(20), selected)
    fr_start = language_job_percent("FRENCH", 1, language_work_total(20), selected)
    assert en_export < 55
    assert fr_start >= 50
