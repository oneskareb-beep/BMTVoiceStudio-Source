"""Optional live audio validation against BMT reference pipeline (requires Edge TTS + FFmpeg)."""

from __future__ import annotations

import asyncio
import json
from datetime import date
from pathlib import Path

from bmt_voice_studio.config.presets import BMT_ENGLISH, BMT_FRENCH
from bmt_voice_studio.daily.pipeline import DailyJob, run_daily_job
from bmt_voice_studio.production_batch import _probe


async def _run_language(sample: Path, language: str, preset, tmp: Path) -> dict:
    text = sample.read_text(encoding="utf-8")
    job = DailyJob(
        date=date(2026, 8, 13),
        english_text=text if language == "ENGLISH" else "",
        french_text=text if language == "FRENCH" else "",
        generate_english=language == "ENGLISH",
        generate_french=language == "FRENCH",
        base_exports=tmp,
        strict_source_mode=True,
        processing_mode="original",
    )
    result = await run_daily_job(job)
    block = result.english if language == "ENGLISH" else result.french
    mp3_probe = (block or {}).get("mp3_probe") or {}
    wav_probe = (block or {}).get("wav_probe") or {}
    return {
        "source": sample.name,
        "ok": bool(block and block.get("ok")),
        "segment_count": (block or {}).get("segment_count"),
        "voice_audit": (block or {}).get("voice_audit"),
        "rate": (block or {}).get("rate"),
        "pitch": (block or {}).get("pitch"),
        "volume": (block or {}).get("volume"),
        "pause_ms": (block or {}).get("pause_ms"),
        "lowpass_hz": (block or {}).get("lowpass_hz"),
        "mp3_probe": mp3_probe,
        "wav_probe": wav_probe,
        "errors": (block or {}).get("errors") or result.errors,
    }


async def run_live_validation(tmp_dir: Path) -> dict:
    root = Path(__file__).resolve().parents[1]
    samples = {
        "english": root / "samples" / "english_sample.txt",
        "french": root / "samples" / "french_sample.txt",
    }
    report = {"english": None, "french": None}
    if samples["english"].exists():
        report["english"] = await _run_language(samples["english"], "ENGLISH", BMT_ENGLISH, tmp_dir)
    if samples["french"].exists():
        report["french"] = await _run_language(samples["french"], "FRENCH", BMT_FRENCH, tmp_dir)
    return report


def main() -> int:
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="bmt_pipeline_live_"))
    report = asyncio.run(run_live_validation(tmp))
    out = tmp / "live_validation.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    ok = all((report.get(k) or {}).get("ok") for k in ("english", "french") if report.get(k))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
