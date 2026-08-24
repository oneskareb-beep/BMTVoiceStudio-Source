"""Lightweight verification: Aug 13 UI date → correct folder (no TTS)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from bmt_voice_studio.config.paths import default_exports_dir
from bmt_voice_studio.daily.layout import daily_project_dir, ensure_daily_layout
from bmt_voice_studio.daily.naming import display_date, freeze_devotional_date, final_mp3_name, project_id


def main() -> int:
    selected_ui_date = date(2026, 8, 13)  # Thursday
    project_date = freeze_devotional_date(selected_ui_date)
    history_date = display_date(project_date)

    # Correct base = Exports (not Exports/Daily)
    folder = ensure_daily_layout(project_date, default_exports_dir())
    report_folder = folder / "REPORTS"

    # Also prove passing .../Daily does not double
    folder2 = daily_project_dir(project_date, default_exports_dir() / "Daily")

    print("Selected UI date:", selected_ui_date.isoformat())
    print("Project date:", project_date.isoformat(), project_id(project_date))
    print("History date:", history_date)
    print("Generated folder:", folder)
    print("Report folder:", report_folder)
    print("Filename sample:", final_mp3_name(project_date, "ENGLISH"))
    print("Daily count in path:", Path(folder).parts.count("Daily"))
    print("Same when base already Daily:", folder == folder2)

    ok = (
        project_date == date(2026, 8, 13)
        and history_date == "August 13, 2026"
        and folder.name == "BMT_2026_08_13"
        and folder.parts.count("Daily") == 1
        and "Daily\\Daily" not in str(folder)
        and "Daily/Daily" not in str(folder).replace("\\", "/")
        and folder == folder2
        and report_folder == folder / "REPORTS"
        and final_mp3_name(project_date, "ENGLISH") == "BMT_13_AUG_2026_ENGLISH_FINAL.mp3"
    )
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
