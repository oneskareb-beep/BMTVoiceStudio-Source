"""Live Daily BMT Original Pipeline production for Thursday scripts."""

from __future__ import annotations

import asyncio
import json
from datetime import date
from pathlib import Path

from bmt_voice_studio.config.presets import BMT_ENGLISH, BMT_FRENCH
from bmt_voice_studio.daily.pipeline import DailyJob, effective_job_config, run_daily_job


def _load_text(*candidates: Path) -> tuple[str, str]:
    for path in candidates:
        if path.exists() and path.stat().st_size > 20:
            return path.read_text(encoding="utf-8"), str(path)
    raise FileNotFoundError("No source script found among: " + ", ".join(str(c) for c in candidates))


async def main() -> int:
    downloads = Path.home() / "Downloads"
    exports = Path.home() / "Documents" / "BMT Voice Studio" / "Exports"
    en_text, en_src = _load_text(
        exports / "Daily" / "2026" / "08" / "BMT_2026_08_14" / "SOURCE" / "english_source.txt",
        exports / "Daily" / "2026" / "08" / "BMT_2026_08_13" / "SOURCE" / "english_source.txt",
        downloads / "BMT_13_AUG_2026_EN_CLEAN.txt",
        downloads / "BMT_13_AUG_2026_EN_CLEAN (1).txt",
    )
    fr_text, fr_src = _load_text(
        exports / "Daily" / "2026" / "08" / "BMT_2026_08_14" / "SOURCE" / "french_source.txt",
        exports / "Daily" / "2026" / "08" / "BMT_2026_08_13" / "SOURCE" / "french_source.txt",
        downloads / "BMT_FRENCH_ONE_CLICK_GENERATOR" / "BMT_13_AUG_2026_FR_TTS_READY.txt",
    )

    out_root = exports  # Exports root — layout appends Daily once
    job = DailyJob(
        date=date(2026, 8, 13),  # Thursday — UI/devotional date, not system clock
        english_text=en_text,
        french_text=fr_text,
        generate_english=True,
        generate_french=True,
        processing_mode="original",
        strict_source_mode=True,
        mastering=False,
        provider="piper",  # must be ignored
        use_piper_fallback=False,
        pause_ms=450,
        mp3_bitrate=128,
        base_exports=out_root,
    )
    print("EN_SOURCE", en_src)
    print("FR_SOURCE", fr_src)
    print("EFFECTIVE_EN", json.dumps(effective_job_config(job, BMT_ENGLISH), indent=2))
    print("EFFECTIVE_FR", json.dumps(effective_job_config(job, BMT_FRENCH), indent=2))

    result = await run_daily_job(job)
    report = {
        "ok": result.ok,
        "status": result.status,
        "folder": result.folder,
        "errors": result.errors,
        "report_md": result.report_md,
        "report_json": result.report_json,
        "english": {
            "ok": (result.english or {}).get("ok"),
            "provider": (result.english or {}).get("provider"),
            "actual_provider": (result.english or {}).get("actual_provider"),
            "piper_invocations": (result.english or {}).get("piper_invocations"),
            "pause_ms": (result.english or {}).get("pause_ms"),
            "mp3_bitrate": (result.english or {}).get("mp3_bitrate"),
            "lowpass_hz": (result.english or {}).get("lowpass_hz"),
            "mastering": (result.english or {}).get("mastering"),
            "segment_count": (result.english or {}).get("segment_count"),
            "voice_audit": (result.english or {}).get("voice_audit"),
            "final_mp3": (result.english or {}).get("final_mp3"),
            "final_wav": (result.english or {}).get("final_wav"),
            "mp3_probe": (result.english or {}).get("mp3_probe"),
            "wav_probe": (result.english or {}).get("wav_probe"),
            "errors": (result.english or {}).get("errors"),
        },
        "french": {
            "ok": (result.french or {}).get("ok"),
            "provider": (result.french or {}).get("provider"),
            "actual_provider": (result.french or {}).get("actual_provider"),
            "piper_invocations": (result.french or {}).get("piper_invocations"),
            "pause_ms": (result.french or {}).get("pause_ms"),
            "mp3_bitrate": (result.french or {}).get("mp3_bitrate"),
            "lowpass_hz": (result.french or {}).get("lowpass_hz"),
            "mastering": (result.french or {}).get("mastering"),
            "segment_count": (result.french or {}).get("segment_count"),
            "voice_audit": (result.french or {}).get("voice_audit"),
            "final_mp3": (result.french or {}).get("final_mp3"),
            "final_wav": (result.french or {}).get("final_wav"),
            "mp3_probe": (result.french or {}).get("mp3_probe"),
            "errors": (result.french or {}).get("errors"),
        },
    }
    out = Path(result.folder or out_root) / "REPORTS" / "runtime_fix_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print("REPORT_MD", result.report_md)
    print("RUNTIME_JSON", out)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
