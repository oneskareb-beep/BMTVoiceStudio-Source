"""Live French Daily BMT path — verify spoken numbering sent to Edge TTS."""

from __future__ import annotations

import asyncio
import json
import re
from datetime import date
from pathlib import Path

from bmt_voice_studio.config.presets import BMT_FRENCH
from bmt_voice_studio.core.text_prepare import count_french_list_adverb_starts
from bmt_voice_studio.daily.pipeline import DailyJob, run_daily_job

_ADVERB = re.compile(
    r"(?mi)^(premi[eè]rement|deuxi[eè]mement|troisi[eè]mement|quatri[eè]mement|cinqui[eè]mement)\b",
    re.MULTILINE,
)


def _load_french() -> tuple[str, str]:
    exports = Path.home() / "Documents" / "BMT Voice Studio" / "Exports"
    candidates = [
        exports / "Daily" / "2026" / "08" / "BMT_2026_08_13" / "SOURCE" / "french_source.txt",
        exports / "Daily" / "2026" / "08" / "BMT_2026_08_14" / "SOURCE" / "french_source.txt",
        Path.home() / "Downloads" / "BMT_FRENCH_ONE_CLICK_GENERATOR" / "BMT_13_AUG_2026_FR_TTS_READY.txt",
    ]
    for path in candidates:
        if path.exists() and path.stat().st_size > 20:
            return path.read_text(encoding="utf-8"), str(path)
    raise FileNotFoundError("French source not found")


async def main() -> int:
    fr_text, fr_src = _load_french()
    # Keep a tiny EN stub so job can optionally skip EN
    en_stub = "Male open. {Female close.}"
    out_root = Path.home() / "Documents" / "BMT Voice Studio" / "Exports"
    job = DailyJob(
        date=date(2026, 8, 13),
        english_text=en_stub,
        french_text=fr_text,
        generate_english=False,
        generate_french=True,
        processing_mode="original",
        strict_source_mode=True,
        mastering=False,
        provider="edge",
        use_piper_fallback=False,
        base_exports=out_root,
    )
    print("FR_SOURCE", fr_src)
    print("SOURCE_ADVERB_STARTS", count_french_list_adverb_starts(fr_text))
    result = await run_daily_job(job)
    fr = result.french or {}
    spoken_chunks = [s.get("spoken_text") or "" for s in (fr.get("segments") or [])]
    spoken_all = "\n".join(spoken_chunks)
    adverb_in_spoken = len(_ADVERB.findall(spoken_all))
    has_un = any(re.search(r"(?m)^Un\.", t) for t in spoken_chunks)
    report = {
        "ok": result.ok and bool(fr.get("ok")),
        "folder": result.folder,
        "report_md": result.report_md,
        "report_json": result.report_json,
        "spoken_numbering_normalization": fr.get("spoken_numbering_normalization"),
        "french_numbering_replacements": fr.get("french_numbering_replacements"),
        "piper_invocations": fr.get("piper_invocations"),
        "actual_provider": fr.get("actual_provider"),
        "male_voice": fr.get("male_voice"),
        "female_voice": fr.get("female_voice"),
        "voice_audit": fr.get("voice_audit"),
        "final_mp3": fr.get("final_mp3"),
        "adverb_starts_in_spoken": adverb_in_spoken,
        "has_un_marker": has_un,
        "spoken_samples": [
            {
                "index": s.get("index"),
                "source_head": (s.get("source_text") or "")[:80],
                "spoken_head": (s.get("spoken_text") or "")[:80],
            }
            for s in (fr.get("segments") or [])[:8]
        ],
        "errors": result.errors or fr.get("errors"),
        "preset": BMT_FRENCH.id,
    }
    out = Path(result.folder or ".") / "REPORTS" / "french_numbering_live.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print("LIVE_JSON", out)
    ok = (
        report["ok"]
        and report["spoken_numbering_normalization"] is True
        and int(report["french_numbering_replacements"] or 0) >= 1
        and report["adverb_starts_in_spoken"] == 0
        and report["piper_invocations"] == 0
        and "Premièrement" not in spoken_all
        and "Deuxièmement" not in spoken_all
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
