"""Regression: Daily BMT date freeze + single Daily export folder."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from bmt_voice_studio.daily.layout import (
    daily_exports_root,
    daily_project_dir,
    ensure_daily_layout,
)
from bmt_voice_studio.daily.naming import (
    display_date,
    freeze_devotional_date,
    final_mp3_name,
    parse_iso_date,
    project_id,
)
from bmt_voice_studio.daily.pipeline import DailyJob
from bmt_voice_studio.daily.report import write_reports


def test_no_duplicated_daily_directory(tmp_path: Path):
    exports = tmp_path / "Exports"
    exports.mkdir()
    # Normal: base is Exports → Exports/Daily/...
    root = ensure_daily_layout(date(2026, 8, 13), exports)
    parts = root.parts
    assert parts[-1] == "BMT_2026_08_13"
    assert parts[-2] == "08"
    assert parts[-3] == "2026"
    assert parts[-4] == "Daily"
    assert parts.count("Daily") == 1

    # Caller already passes .../Daily → still only one Daily segment
    already = exports / "Daily"
    root2 = ensure_daily_layout(date(2026, 8, 13), already)
    assert root2 == root
    assert str(root2).count("Daily") == 1
    assert "Daily\\Daily" not in str(root2) and "Daily/Daily" not in str(root2).replace("\\", "/")


def test_daily_exports_root_canonical(tmp_path: Path):
    exports = tmp_path / "Exports"
    a = daily_exports_root(exports)
    b = daily_exports_root(exports / "Daily")
    assert a == b
    assert a.name == "Daily"
    assert a.parent == exports


def test_ui_selected_date_not_advanced_by_utc_eat():
    """East Africa (UTC+3) evening must not advance calendar day via UTC conversion."""
    # Fixed UTC+3 offset (EAT) — no tzdata dependency.
    eat = timezone(timedelta(hours=3), name="EAT")
    local_dt = datetime(2026, 8, 13, 22, 30, tzinfo=eat)
    assert local_dt.astimezone(timezone.utc).date() == date(2026, 8, 13)

    ui_year, ui_month, ui_day = 2026, 8, 13
    frozen = freeze_devotional_date(
        type("QD", (), {"year": lambda self: ui_year, "month": lambda self: ui_month, "day": lambda self: ui_day})()
    )
    assert frozen == date(2026, 8, 13)
    assert project_id(frozen) == "BMT_2026_08_13"
    assert display_date(frozen) == "August 13, 2026"

    # UTC 22:00 on Aug 13 == Aug 14 01:00 EAT — TZ conversion advances local day.
    utc_rollover = datetime(2026, 8, 13, 22, 0, tzinfo=timezone.utc)
    assert utc_rollover.astimezone(eat).date() == date(2026, 8, 14)
    # Production must ignore that UTC/EAT conversion and keep UI date:
    assert freeze_devotional_date(date(2026, 8, 13)) == date(2026, 8, 13)
    assert freeze_devotional_date("2026-08-13T23:59:59+03:00") == date(2026, 8, 13)
    assert freeze_devotional_date("2026-08-13T21:00:00Z") == date(2026, 8, 13)


def test_datetime_freeze_uses_calendar_components_not_tz_convert():
    # Aware datetime: use .year/.month/.day of the object as-is (no astimezone).
    dt = datetime(2026, 8, 13, 23, 0, tzinfo=timezone.utc)
    assert freeze_devotional_date(dt) == date(2026, 8, 13)
    # Naive datetime past local midnight boundary still uses its own Y/M/D.
    assert freeze_devotional_date(datetime(2026, 8, 13, 0, 5)) == date(2026, 8, 13)


def test_job_date_folder_history_report_agree(tmp_path: Path):
    selected = date(2026, 8, 13)
    job = DailyJob(
        date=selected,
        english_text="Hello",
        french_text="Bonjour",
        generate_english=True,
        generate_french=False,
        base_exports=tmp_path / "Exports",
    )
    job.date = freeze_devotional_date(job.date)
    folder = ensure_daily_layout(job.date, job.base_exports)
    assert folder.name == "BMT_2026_08_13"
    assert "Daily" in folder.parts
    assert folder.parts.count("Daily") == 1
    assert final_mp3_name(job.date, "ENGLISH") == "BMT_13_AUG_2026_ENGLISH_FINAL.mp3"

    history_date = display_date(job.date)
    assert history_date == "August 13, 2026"

    md, js = write_reports(
        folder,
        {
            "date": job.date.isoformat(),
            "status": "COMPLETE",
            "folder": str(folder),
            "pause_ms": 500,
            "english": {"ok": True},
            "french": None,
        },
    )
    text = md.read_text(encoding="utf-8")
    assert "2026-08-13" in text
    assert str(folder) in text or "BMT_2026_08_13" in text
    assert md.parent == folder / "REPORTS"
    assert daily_project_dir(selected, tmp_path / "Exports") == folder


def test_parse_iso_strips_timezone_without_advancing_day():
    assert parse_iso_date("2026-08-13T23:30:00+03:00") == date(2026, 8, 13)
    assert parse_iso_date("2026-08-13") == date(2026, 8, 13)
