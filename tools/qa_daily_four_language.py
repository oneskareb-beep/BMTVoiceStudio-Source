"""Generate or verify EN/FR/SW/PT Daily BMT audio for 14 Aug 2026. Piper must stay 0."""

from __future__ import annotations

import asyncio
import json
import shutil
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DAY = date(2026, 8, 14)


def _existing_exports() -> Path | None:
    candidates = [
        Path.home() / "Documents" / "BMT Voice Studio" / "Exports",
        Path.home() / "OneDrive" / "Documents" / "BMT Voice Studio" / "Exports",
        Path(r"C:\Users\aganz\Documents\BMT Voice Studio\Exports"),
        Path(r"C:\Users\aganz\OneDrive\Documents\BMT Voice Studio\Exports"),
    ]
    for path in candidates:
        daily = path / "Daily" / "2026" / "08" / "BMT_2026_08_14"
        if daily.is_dir():
            return path
    return None


def _find_source(name: str) -> Path | None:
    exports = _existing_exports()
    if exports is None:
        return None
    daily = exports / "Daily"
    matches = list(daily.rglob(name))
    return matches[0] if matches else None


def _ensure_aug14_sources(project: Path) -> dict[str, str]:
    src = project / "SOURCE"
    src.mkdir(parents=True, exist_ok=True)
    mapping = {
        "english_source.txt": _find_source("english_source.txt"),
        "french_source.txt": _find_source("french_source.txt"),
        "swahili_source.txt": _find_source("swahili_source.txt"),
        "portuguese_source.txt": _find_source("portuguese_source.txt"),
    }
    out: dict[str, str] = {}
    for dest_name, found in mapping.items():
        dest = src / dest_name
        if not dest.is_file() and found and found.is_file():
            shutil.copy2(found, dest)
        out[dest_name] = dest.read_text(encoding="utf-8") if dest.is_file() else ""
    return out


def _final_mp3(project: Path, folder: str) -> Path:
    lang = folder  # ENGLISH etc
    matches = list((project / lang).glob("*_FINAL.mp3"))
    return matches[0] if matches else project / lang / f"missing_{folder}.mp3"


async def _generate_missing(project: Path, texts: dict[str, str], need: list[str]) -> dict:
    from bmt_voice_studio.daily.pipeline import DailyJob, run_daily_job

    exports = project.parents[2]  # .../Exports  (Daily/2026/08/BMT_...)
    # parents: 0=BMT_..., 1=08, 2=2026, 3=Daily, 4=Exports — wait
    # project = Exports/Daily/2026/08/BMT_2026_08_14
    exports = project.parent.parent.parent.parent
    job = DailyJob(
        date=DAY,
        english_text=texts.get("english_source.txt", ""),
        french_text=texts.get("french_source.txt", ""),
        swahili_text=texts.get("swahili_source.txt", ""),
        portuguese_text=texts.get("portuguese_source.txt", ""),
        generate_english="en" in need,
        generate_french="fr" in need,
        generate_swahili="sw" in need,
        generate_portuguese="pt" in need,
        base_exports=exports,
        provider="edge",
        use_piper_fallback=False,
        mastering=False,
    )
    result = await run_daily_job(job)
    piper = 0
    payload: dict = {"ok": result.ok, "status": result.status, "folder": result.folder, "errors": result.errors}
    for name in ("english", "french", "swahili", "portuguese"):
        block = getattr(result, name)
        payload[name] = None
        if isinstance(block, dict):
            piper += int(block.get("piper_invocations") or 0)
            payload[name] = {
                "ok": block.get("ok"),
                "final_mp3": block.get("final_mp3"),
                "duration": ((block.get("mp3_probe") or {}).get("duration_sec")),
                "piper_invocations": block.get("piper_invocations"),
                "actual_voice": block.get("actual_voice"),
                "configured_voice": block.get("configured_voice"),
            }
    payload["piper_invocations"] = piper
    return payload


def main() -> int:
    from bmt_voice_studio.video.discovery import find_generated_audio, language_tracks_for_day
    from bmt_voice_studio.video.media_probe import probe_audio_duration

    exports = _existing_exports()
    report: dict = {"day": DAY.isoformat(), "exports": str(exports) if exports else ""}
    if exports is None:
        report["error"] = "No existing Daily Exports tree for 2026-08-14"
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 1
    project = exports / "Daily" / "2026" / "08" / "BMT_2026_08_14"
    texts = _ensure_aug14_sources(project)
    report["source_chars"] = {k: len(v) for k, v in texts.items()}
    need: list[str] = []
    for lang in ("en", "fr", "sw", "pt"):
        found = find_generated_audio(DAY, lang)
        report[f"{lang}_existing"] = str(found) if found else ""
        if found is None or not Path(found).is_file():
            need.append(lang)
    if need:
        print("GENERATING", need, flush=True)
        gen = asyncio.run(_generate_missing(project, texts, need))
        report["generation"] = gen
        if int(gen.get("piper_invocations") or 0) != 0:
            report["error"] = "Piper invocations were not 0"
            print(json.dumps(report, indent=2, ensure_ascii=False))
            return 1
    tracks = language_tracks_for_day(DAY)
    langs = {}
    for t in tracks:
        dur = 0.0
        if t.audio_path and Path(t.audio_path).is_file():
            try:
                dur = probe_audio_duration(t.audio_path)
            except Exception:
                dur = t.audio_duration
        langs[t.language] = {
            "ready": t.ready,
            "topic": t.topic,
            "week_focus": t.week_focus,
            "month_theme": t.month_theme,
            "memory_verse": (t.memory_verse or "")[:80],
            "audio": t.audio_path,
            "duration": dur,
        }
    report["languages"] = langs
    report["all_ready"] = all(langs.get(k, {}).get("ready") for k in ("en", "fr", "sw", "pt"))
    dest = ROOT / "qa_outputs" / "video_maker_phase4" / "daily_four_language.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print("WROTE", dest)
    return 0 if report["all_ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
