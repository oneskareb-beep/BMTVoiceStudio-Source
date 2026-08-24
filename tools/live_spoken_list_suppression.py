"""Live Daily BMT EN+FR — verify spoken list markers are suppressed."""

from __future__ import annotations

import asyncio
import json
import re
from datetime import date
from pathlib import Path

from bmt_voice_studio.config.presets import BMT_ENGLISH, BMT_FRENCH
from bmt_voice_studio.core.text_prepare import count_list_marker_starts
from bmt_voice_studio.daily.pipeline import DailyJob, run_daily_job

_BANNED_FR = re.compile(
    r"(?mi)^(premi[eè]rement|deuxi[eè]mement|troisi[eè]mement|quatri[eè]mement|cinqui[eè]mement|"
    r"un|deux|trois|quatre|cinq)\s*[.:,]",
    re.MULTILINE,
)
_BANNED_EN = re.compile(
    r"(?mi)^(number\s+(?:one|two|three|four|five)|first|second|third|fourth|fifth|[1-5])\s*[.:,]",
    re.MULTILINE,
)


def _load(*candidates: Path) -> tuple[str, str]:
    for path in candidates:
        if path.exists() and path.stat().st_size > 20:
            return path.read_text(encoding="utf-8"), str(path)
    raise FileNotFoundError("source not found")


async def main() -> int:
    exports = Path.home() / "Documents" / "BMT Voice Studio" / "Exports"
    en_text, en_src = _load(
        exports / "Daily" / "2026" / "08" / "BMT_2026_08_13" / "SOURCE" / "english_source.txt",
        exports / "Daily" / "2026" / "08" / "BMT_2026_08_14" / "SOURCE" / "english_source.txt",
    )
    fr_text, fr_src = _load(
        exports / "Daily" / "2026" / "08" / "BMT_2026_08_13" / "SOURCE" / "french_source.txt",
        exports / "Daily" / "2026" / "08" / "BMT_2026_08_14" / "SOURCE" / "french_source.txt",
    )
    job = DailyJob(
        date=date(2026, 8, 13),
        english_text=en_text,
        french_text=fr_text,
        generate_english=True,
        generate_french=True,
        processing_mode="original",
        strict_source_mode=True,
        mastering=False,
        provider="edge",
        use_piper_fallback=False,
        base_exports=exports,
    )
    print("EN_SOURCE", en_src)
    print("FR_SOURCE", fr_src)
    result = await run_daily_job(job)
    en = result.english or {}
    fr = result.french or {}

    def spoken_blob(block: dict) -> str:
        return "\n".join(s.get("spoken_text") or "" for s in (block.get("segments") or []))

    en_spoken = spoken_blob(en)
    fr_spoken = spoken_blob(fr)
    report = {
        "ok": bool(result.ok and en.get("ok") and fr.get("ok")),
        "folder": result.folder,
        "report_md": result.report_md,
        "english": {
            "ok": en.get("ok"),
            "spoken_list_marker_suppression": en.get("spoken_list_marker_suppression"),
            "spoken_list_markers_removed": en.get("spoken_list_markers_removed"),
            "piper_invocations": en.get("piper_invocations"),
            "male_voice": en.get("male_voice"),
            "female_voice": en.get("female_voice"),
            "rate": en.get("rate"),
            "pitch": en.get("pitch"),
            "volume": en.get("volume"),
            "pause_ms": en.get("pause_ms"),
            "final_mp3": en.get("final_mp3"),
            "banned_in_spoken": len(_BANNED_EN.findall(en_spoken)),
            "remaining_markers": count_list_marker_starts(en_spoken, "en"),
            "samples": [
                {
                    "index": s.get("index"),
                    "source_head": (s.get("source_text") or "")[:90],
                    "spoken_head": (s.get("spoken_text") or "")[:90],
                }
                for s in (en.get("segments") or [])
                if (s.get("source_text") or "") != (s.get("spoken_text") or "")
            ][:6],
        },
        "french": {
            "ok": fr.get("ok"),
            "spoken_list_marker_suppression": fr.get("spoken_list_marker_suppression"),
            "spoken_list_markers_removed": fr.get("spoken_list_markers_removed"),
            "piper_invocations": fr.get("piper_invocations"),
            "male_voice": fr.get("male_voice"),
            "female_voice": fr.get("female_voice"),
            "rate": fr.get("rate"),
            "pitch": fr.get("pitch"),
            "volume": fr.get("volume"),
            "pause_ms": fr.get("pause_ms"),
            "final_mp3": fr.get("final_mp3"),
            "banned_in_spoken": len(_BANNED_FR.findall(fr_spoken)),
            "remaining_markers": count_list_marker_starts(fr_spoken, "fr"),
            "samples": [
                {
                    "index": s.get("index"),
                    "source_head": (s.get("source_text") or "")[:90],
                    "spoken_head": (s.get("spoken_text") or "")[:90],
                }
                for s in (fr.get("segments") or [])
                if (s.get("source_text") or "") != (s.get("spoken_text") or "")
            ][:6],
        },
        "source_still_has_fr_premiere": "Premièrement" in fr_text or "Premièrement" in Path(fr_src).read_text(encoding="utf-8"),
        "presets": {"en": BMT_ENGLISH.id, "fr": BMT_FRENCH.id},
        "errors": result.errors,
    }
    out = Path(result.folder or ".") / "REPORTS" / "spoken_list_suppression_live.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print("LIVE_JSON", out)
    ok = (
        report["ok"]
        and report["english"]["spoken_list_marker_suppression"]
        and report["french"]["spoken_list_marker_suppression"]
        and report["english"]["banned_in_spoken"] == 0
        and report["french"]["banned_in_spoken"] == 0
        and report["english"]["remaining_markers"] == 0
        and report["french"]["remaining_markers"] == 0
        and report["english"]["piper_invocations"] == 0
        and report["french"]["piper_invocations"] == 0
        and int(report["french"]["spoken_list_markers_removed"] or 0) >= 1
        and report["source_still_has_fr_premiere"]
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
