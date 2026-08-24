"""Discover generated Daily audio and extract devotional metadata."""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from bmt_voice_studio.config.paths import default_exports_dir
from bmt_voice_studio.daily.autosave import load_draft
from bmt_voice_studio.daily.history import load_history
from bmt_voice_studio.daily.layout import daily_project_dir, final_paths
from bmt_voice_studio.daily.naming import freeze_devotional_date
from bmt_voice_studio.video.models import LANGUAGE_FOLDERS, LANGUAGE_LABELS, LanguageTrack, language_folder

_LABEL_PATTERNS = {
    "topic": re.compile(
        r"^\s*(?:topic|titre|subject|theme of the day|th[eè]me du jour|"
        r"th[eè]me(?:\s+du\s+jour)?|mada|tema(?!\s+do)|assunto)\s*[:\-–]\s*(.+)$",
        re.IGNORECASE,
    ),
    "week_focus": re.compile(
        r"^\s*(?:week\s*focus|weekly\s*focus|focus of the week|focus de la semaine|"
        r"msisitizo wa wiki|foco da semana)\s*[:\-–]\s*(.+)$",
        re.IGNORECASE,
    ),
    "month_theme": re.compile(
        r"^\s*(?:month\s*theme|monthly\s*theme|th[eè]me du mois|mada ya mwezi|"
        r"tema do m[eê]s)\s*[:\-–]\s*(.+)$",
        re.IGNORECASE,
    ),
    "title": re.compile(
        r"^\s*(?:title|devotional title|titre du d[eé]votionnel)\s*[:\-–]\s*(.+)$",
        re.IGNORECASE,
    ),
}

_SOURCE_FILES = {
    "en": "english_source.txt",
    "fr": "french_source.txt",
    "sw": "swahili_source.txt",
    "pt": "portuguese_source.txt",
}

_DRAFT_KEYS = {
    "en": "english_text",
    "fr": "french_text",
    "sw": "swahili_text",
    "pt": "portuguese_text",
}

_HISTORY_MP3 = {"en": "en_mp3", "fr": "fr_mp3", "sw": "sw_mp3", "pt": "pt_mp3"}
_HISTORY_DUR = {
    "en": "en_duration",
    "fr": "fr_duration",
    "sw": "sw_duration",
    "pt": "pt_duration",
}


def language_label(language: str) -> str:
    key = (language or "en").strip().lower()
    return LANGUAGE_LABELS.get(key, language_folder(language).title())


def format_duration(seconds: float | str | None) -> str:
    try:
        total = int(round(float(seconds or 0)))
    except (TypeError, ValueError):
        return "—"
    if total <= 0:
        return "—"
    m, s = divmod(total, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h:d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def _history_entry_for(d: date, entries: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
    iso = d.isoformat()
    pid = f"BMT_{d.strftime('%Y_%m_%d')}"
    for entry in entries if entries is not None else load_history():
        if str(entry.get("date") or "")[:10] == iso or str(entry.get("project_id") or "") == pid:
            return entry
    return None


def _valid_audio(path: str | Path | None) -> Path | None:
    if not path:
        return None
    p = Path(str(path))
    try:
        if p.is_file() and p.suffix.lower() in {".mp3", ".wav"}:
            return p
    except Exception:
        return None
    return None


def find_generated_audio(
    d: date | str,
    language: str,
    *,
    base: Path | None = None,
    history_entries: list[dict[str, Any]] | None = None,
) -> Path | None:
    """Locate generated Daily MP3/WAV using history first, then the output layout."""
    day = freeze_devotional_date(d)
    lang = (language or "en").strip().lower()
    entry = _history_entry_for(day, history_entries)
    if entry:
        hist_path = _valid_audio(entry.get(_HISTORY_MP3.get(lang, "en_mp3")))
        if hist_path:
            return hist_path
        folder = entry.get("folder")
        if folder:
            mp3, wav = final_paths(Path(folder), day, language_folder(lang))
            if mp3.is_file():
                return mp3
            if wav.is_file():
                return wav
    exports = base if base is not None else default_exports_dir()
    root = daily_project_dir(day, exports)
    mp3, wav = final_paths(root, day, language_folder(lang))
    if mp3.is_file():
        return mp3
    if wav.is_file():
        return wav
    folder = root / language_folder(lang)
    if folder.is_dir():
        finals = sorted(folder.glob("*_FINAL.mp3")) + sorted(folder.glob("*_FINAL.wav"))
        for path in finals:
            if path.is_file():
                return path
    return None


def todays_audio_status(
    d: date | str,
    *,
    base: Path | None = None,
    history_entries: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Per-language Ready / Not generated rows for Video Maker."""
    day = freeze_devotional_date(d)
    entries = history_entries if history_entries is not None else load_history()
    entry = _history_entry_for(day, entries)
    rows: list[dict[str, Any]] = []
    for lang_id in LANGUAGE_FOLDERS:
        path = find_generated_audio(day, lang_id, base=base, history_entries=entries)
        duration = 0.0
        if entry:
            raw = entry.get(_HISTORY_DUR.get(lang_id, "en_duration")) or 0
            try:
                duration = float(raw or 0)
            except (TypeError, ValueError):
                duration = 0.0
        if duration <= 0.4 and path is not None:
            try:
                from bmt_voice_studio.video.media_probe import probe_audio_duration

                duration = float(probe_audio_duration(path) or 0.0)
            except Exception:
                pass
        rows.append(
            {
                "language": lang_id,
                "label": language_label(lang_id),
                "ready": path is not None,
                "status": "Ready" if path else "Not generated",
                "path": str(path) if path else "",
                "name": path.name if path else "",
                "duration": duration,
                "duration_label": format_duration(duration),
            }
        )
    return rows


def list_generated_audio_for_day(
    d: date | str,
    *,
    base: Path | None = None,
    history_entries: list[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    found: list[dict[str, str]] = []
    for row in todays_audio_status(d, base=base, history_entries=history_entries):
        if row["ready"]:
            found.append(
                {
                    "language": row["language"],
                    "label": row["label"],
                    "path": row["path"],
                    "name": row["name"],
                    "duration": str(row.get("duration") or ""),
                }
            )
    return found


def resolve_daily_project_dir(
    d: date | str,
    *,
    base: Path | None = None,
    history_entries: list[dict[str, Any]] | None = None,
    audio_path: str = "",
) -> Path:
    """Locate the Daily project folder even when Documents vs OneDrive diverge."""
    day = freeze_devotional_date(d)
    candidates: list[Path] = []
    exports = base if base is not None else default_exports_dir()
    candidates.append(daily_project_dir(day, exports))
    entries = history_entries if history_entries is not None else load_history()
    entry = _history_entry_for(day, entries)
    if entry:
        folder = entry.get("folder")
        if folder:
            candidates.append(Path(str(folder)))
        for key in _HISTORY_MP3.values():
            found = _valid_audio(entry.get(key))
            if found is not None:
                candidates.append(found.parent.parent)
    if audio_path:
        try:
            ap = Path(audio_path)
            if ap.exists():
                candidates.append(ap.parent.parent)
        except Exception:
            pass
    for cand in candidates:
        try:
            if (cand / "SOURCE").is_dir() or (cand / "REPORTS" / "production.json").is_file():
                return cand
        except Exception:
            continue
    return candidates[0]


def load_source_text(
    d: date | str,
    language: str,
    *,
    base: Path | None = None,
    history_entries: list[dict[str, Any]] | None = None,
    audio_path: str = "",
) -> str:
    day = freeze_devotional_date(d)
    root = resolve_daily_project_dir(
        day, base=base, history_entries=history_entries, audio_path=audio_path
    )
    key = (language or "en").strip().lower()
    source = root / "SOURCE" / _SOURCE_FILES.get(key, "english_source.txt")
    if source.is_file():
        try:
            return source.read_text(encoding="utf-8")
        except Exception:
            return ""
    report = root / "REPORTS" / "production.json"
    if report.is_file():
        structured = _text_from_production_json(report, key)
        if structured:
            return structured
    draft = load_draft() or {}
    draft_date = str(draft.get("date") or "")
    if draft_date.startswith(day.isoformat()):
        return str(draft.get(_DRAFT_KEYS.get(key, "english_text")) or "")
    return str(draft.get(_DRAFT_KEYS.get(key, "english_text")) or "") if draft else ""


def _text_from_production_json(path: Path, language: str) -> str:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    block_name = {"en": "english", "fr": "french", "sw": "swahili", "pt": "portuguese"}.get(language, "english")
    block = data.get(block_name) or {}
    segs = block.get("segments") or []
    parts: list[str] = []
    for seg in segs:
        text = str(seg.get("source_text") or "")
        if text.strip():
            parts.append(text)
    return "\n\n".join(parts)


def _extract_memory_verse(text: str) -> str:
    blob = text or ""
    m = re.search(
        r"\{?\s*(?:Memory Verse|Verset à mémoriser|Mstari wa Kukariri|Versículo para Memorizar)\s*[:\n]+(.+?)(?:\n\s*\n|Devotional Insight|Week Focus|Month Theme|Réflexion|Tafakari|Reflexão|\})",
        blob,
        re.IGNORECASE | re.DOTALL,
    )
    if not m:
        m = re.search(r"^\s*Memory Verse\s*[:\-–]\s*(.+)$", blob, re.IGNORECASE | re.MULTILINE)
        return (m.group(1).strip() if m else "")[:400]
    verse = " ".join(m.group(1).strip().split())
    return verse[:400]


def extract_metadata(text: str) -> dict[str, str]:
    """Pull topic / week focus / month theme / title / memory verse from script lines.

    Metadata is accepted only from explicit structured labels. In particular,
    the daily topic is never guessed from the first non-empty line: doing that
    can turn headers such as ``Memory Verse`` or stray English text into the
    title of a French, Swahili, or Portuguese video.
    """
    topic = ""
    week_focus = ""
    month_theme = ""
    title = ""
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        for key, pattern in _LABEL_PATTERNS.items():
            m = pattern.match(line)
            if not m:
                continue
            value = m.group(1).strip().strip("{}").strip()
            if key == "topic" and not topic:
                topic = value
            elif key == "week_focus" and not week_focus:
                week_focus = value
            elif key == "month_theme" and not month_theme:
                month_theme = value
            elif key == "title" and not title:
                title = value
    if not title:
        title = topic
    from bmt_voice_studio.daily.message_date import detect_message_date

    found = detect_message_date(text)
    return {
        "topic": topic,
        "week_focus": week_focus,
        "month_theme": month_theme,
        "title": title,
        "memory_verse": _extract_memory_verse(text),
        "message_date": found.isoformat() if found else "",
    }


def metadata_for_language(
    d: date | str,
    language: str,
    *,
    live_text: str = "",
    base: Path | None = None,
    history_entries: list[dict[str, Any]] | None = None,
    audio_path: str = "",
) -> dict[str, str]:
    text = live_text or load_source_text(
        d,
        language,
        base=base,
        history_entries=history_entries,
        audio_path=audio_path,
    )
    meta = extract_metadata(text)
    day = freeze_devotional_date(d)
    meta["date"] = day.isoformat()
    meta["language"] = (language or "en").strip().lower()
    return meta


def language_tracks_for_day(
    d: date | str,
    *,
    base: Path | None = None,
    history_entries: list[dict[str, Any]] | None = None,
) -> list[LanguageTrack]:
    tracks: list[LanguageTrack] = []
    for row in todays_audio_status(d, base=base, history_entries=history_entries):
        lang = row["language"]
        audio = str(row.get("path") or "")
        if row["ready"]:
            meta = metadata_for_language(
                d,
                lang,
                base=base,
                history_entries=history_entries,
                audio_path=audio,
            )
        else:
            meta = {
                "topic": "",
                "week_focus": "",
                "month_theme": "",
                "title": "",
                "memory_verse": "",
            }
        topic = str(meta.get("topic") or "")
        tracks.append(
            LanguageTrack(
                language=lang,
                audio_path=audio,
                audio_duration=float(row.get("duration") or 0.0),
                topic=topic,
                week_focus=str(meta.get("week_focus") or ""),
                month_theme=str(meta.get("month_theme") or ""),
                title=str(meta.get("title") or ""),
                memory_verse=str(meta.get("memory_verse") or ""),
                selected=False,
                metadata_complete=bool(topic.strip()),
                ready=bool(row.get("ready")),
            )
        )
    return tracks
