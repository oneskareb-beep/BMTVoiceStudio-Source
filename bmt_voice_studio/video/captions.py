"""Caption cues timed from Daily TTS — Edge word clocks when present, else segment probes.

School-text style: one sentence per cue (~2–3s), starts and finishes with the voice.
Never equal-slot by sentence count alone (that desynced captions from the voice).
Never from separate STT/transcription.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any

from bmt_voice_studio.daily.naming import freeze_devotional_date

CAPTION_BODY = "body"
CAPTION_BODY_VERSE = "body_verse"
CAPTION_ALL = "all"
CAPTION_MODE_LABELS = {
    CAPTION_BODY: "Body Only",
    CAPTION_BODY_VERSE: "Body + Memory Verse",
    CAPTION_ALL: "All Spoken Content",
}


def normalize_caption_mode(value: str | None, *, skip_header: bool | None = None) -> str:
    raw = (value or "").strip().lower()
    if raw in {CAPTION_BODY, "body_only", "body-only"}:
        return CAPTION_BODY
    if raw in {CAPTION_ALL, "all", "all_spoken"}:
        return CAPTION_ALL
    if raw in {CAPTION_BODY_VERSE, "body+verse", "skip", "skip_header"}:
        return CAPTION_BODY_VERSE
    if skip_header is False:
        return CAPTION_ALL
    return CAPTION_BODY_VERSE

MAX_CAPTION_CHARS = 88
MAX_CAPTION_LINES = 3
# School-text style: one spoken sentence on screen (Sylvestre: ~2–3s cues).
SENTENCES_PER_CUE = 1
MIN_SCHOOL_CUE_SEC = 2.0
TARGET_SCHOOL_CUE_SEC = 2.5
MAX_SCHOOL_CUE_SEC = 3.25

_LANG_BLOCKS = {"en": "english", "fr": "french", "sw": "swahili", "pt": "portuguese"}
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?…;:])\s+")
_WORD_END_SENTENCE = re.compile(r"[.!?…]+$")


@dataclass
class CaptionCue:
    start: float
    end: float
    text: str
    language: str = "en"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_production_block(d: date | str, language: str, *, base: Path | None = None) -> dict[str, Any]:
    from bmt_voice_studio.video.discovery import resolve_daily_project_dir

    day = freeze_devotional_date(d)
    root = resolve_daily_project_dir(day, base=base)
    report = root / "REPORTS" / "production.json"
    if not report.is_file():
        return {}
    try:
        data = json.loads(report.read_text(encoding="utf-8"))
    except Exception:
        return {}
    key = _LANG_BLOCKS.get((language or "en").strip().lower(), "english")
    block = data.get(key) or {}
    return block if isinstance(block, dict) else {}


def _word_timings_from_sidecar(path: str | Path | None) -> list[dict[str, Any]]:
    if not path:
        return []
    side = Path(path).with_suffix(".words.json")
    if not side.is_file():
        return []
    try:
        data = json.loads(side.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    out: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        try:
            start = float(item.get("start") or 0.0)
            end = float(item.get("end") or start + 0.05)
        except (TypeError, ValueError):
            continue
        text = str(item.get("text") or "").strip()
        if text:
            out.append({"text": text, "start": start, "end": max(start + 0.02, end)})
    return out


def load_language_segments(d: date | str, language: str, *, base: Path | None = None) -> list[dict[str, Any]]:
    block = load_production_block(d, language, base=base)
    segs = block.get("segments") or []
    out: list[dict[str, Any]] = []
    for seg in segs:
        if not isinstance(seg, dict):
            continue
        probe = seg.get("probe") or {}
        dur = probe.get("duration_sec") if isinstance(probe, dict) else None
        try:
            duration = float(dur or 0.0)
        except (TypeError, ValueError):
            duration = 0.0
        text = str(seg.get("spoken_text") or seg.get("source_text") or "").strip()
        if not text:
            continue
        timings = seg.get("word_timings")
        if not isinstance(timings, list) or not timings:
            timings = _word_timings_from_sidecar(seg.get("path"))
        out.append(
            {
                "index": int(seg.get("index") or len(out) + 1),
                "role": str(seg.get("role") or ""),
                "text": text,
                "duration": duration,
                "language": (language or "en").strip().lower(),
                "word_timings": timings if isinstance(timings, list) else [],
                "path": str(seg.get("path") or ""),
            }
        )
    return out


def split_sentences(text: str) -> list[str]:
    blob = re.sub(r"\s+", " ", (text or "").strip())
    if not blob:
        return []
    parts = [p.strip() for p in _SENTENCE_SPLIT.split(blob) if p.strip()]
    return parts or [blob]


def pair_sentences(sentences: list[str], pair_size: int = SENTENCES_PER_CUE) -> list[list[str]]:
    size = max(1, int(pair_size or SENTENCES_PER_CUE))
    return [list(sentences[i : i + size]) for i in range(0, len(sentences), size)]


def sentences_from_word_timings(words: list[dict[str, Any]]) -> list[tuple[str, float, float]]:
    """Group Edge word clocks into sentences with start/end in seconds."""
    sentences: list[tuple[str, float, float]] = []
    buf: list[str] = []
    start = 0.0
    end = 0.0
    started = False
    for item in words:
        if not isinstance(item, dict):
            continue
        token = str(item.get("text") or "").strip()
        if not token:
            continue
        try:
            w_start = float(item.get("start") or 0.0)
            w_end = float(item.get("end") or w_start + 0.05)
        except (TypeError, ValueError):
            continue
        if not started:
            start = w_start
            started = True
        end = max(w_end, start + 0.05)
        buf.append(token)
        if _WORD_END_SENTENCE.search(token):
            blob = " ".join(buf).strip()
            if blob:
                sentences.append((blob, start, end))
            buf = []
            started = False
    if buf and started:
        blob = " ".join(buf).strip()
        if blob:
            sentences.append((blob, start, end))
    return sentences


def _sentence_allowed_for_mode(sentence: str, mode: str) -> bool:
    if mode == CAPTION_ALL:
        return True
    if is_intro_header_text(sentence):
        return False
    if mode == CAPTION_BODY and is_memory_verse_text(sentence):
        return False
    return True


def _fit_units_to_audio(
    units: list[tuple[str, float, float]], total: float
) -> list[tuple[str, float, float]]:
    """Stretch/compress cue clocks to the master MP3 length while keeping relative pacing."""
    if not units or total <= 0:
        return units
    t0 = units[0][1]
    t1 = units[-1][2]
    native = t1 - t0
    if native < 0.05:
        return units
    target_span = max(0.2, total - t0)
    scale = target_span / native
    scale = min(max(scale, 0.55), 1.85)
    if abs(scale - 1.0) < 0.03:
        out: list[tuple[str, float, float]] = []
        for text, s, e in units:
            ns = min(max(0.0, s), total)
            ne = min(max(ns + 0.12, e), total)
            out.append((text, ns, ne))
        return _school_pace_units(out, total)
    fitted: list[tuple[str, float, float]] = []
    for text, s, e in units:
        ns = t0 + (s - t0) * scale
        ne = t0 + (e - t0) * scale
        ns = min(max(0.0, ns), total)
        ne = min(max(ns + 0.12, ne), total)
        fitted.append((text, ns, ne))
    return _school_pace_units(fitted, total)


def _school_pace_units(
    units: list[tuple[str, float, float]], total: float
) -> list[tuple[str, float, float]]:
    """Keep voice order, but give short sentences readable ~2–3s school-text hold.

    Starts with the first spoken cue and finishes with the last (no orphan gaps at ends).
    Never overlaps the next sentence start.
    """
    if not units:
        return units
    n = len(units)
    out: list[tuple[str, float, float]] = []
    for i, (text, start, end) in enumerate(units):
        start = max(0.0, float(start))
        end = max(start + 0.12, float(end))
        next_start = float(units[i + 1][1]) if i + 1 < n else (total if total > 0 else end)
        if total > 0:
            next_start = min(next_start, total)
        # Prefer 2–3s on screen when the spoken span is tiny, without crossing the next cue.
        hold = max(end - start, MIN_SCHOOL_CUE_SEC)
        hold = min(hold, MAX_SCHOOL_CUE_SEC)
        if end - start < MIN_SCHOOL_CUE_SEC:
            hold = min(max(TARGET_SCHOOL_CUE_SEC, MIN_SCHOOL_CUE_SEC), max(0.12, next_start - start - 0.04))
            end = start + hold
        else:
            end = min(end, next_start - 0.02) if next_start > start + 0.14 else end
        if total > 0:
            start = min(start, total)
            end = min(max(start + 0.12, end), total)
        out.append((text, start, end))
    if total > 0 and out:
        # Finish with the voice: last cue rides to master end.
        last_text, last_s, _last_e = out[-1]
        out[-1] = (last_text, last_s, total)
        # Start with the voice: pin tiny leading slack to t=0.
        first_text, first_s, first_e = out[0]
        if first_s <= 0.08:
            out[0] = (first_text, 0.0, max(first_e, min(total, MIN_SCHOOL_CUE_SEC * 0.5)))
    return out


def caption_cues_from_segments(
    segments: list[dict[str, Any]],
    *,
    pause_sec: float = 0.5,
    audio_duration: float = 0.0,
    language: str = "en",
    max_chars: int = MAX_CAPTION_CHARS,
    skip_header: bool = True,
    caption_mode: str | None = None,
) -> list[CaptionCue]:
    """Build ASS cues from real TTS segment/word clocks (voice order + pacing)."""
    mode = normalize_caption_mode(caption_mode, skip_header=skip_header)
    total = float(audio_duration or 0.0)
    lang = (language or "en").strip().lower()
    pause = max(0.0, float(pause_sec or 0.0))
    units: list[tuple[str, float, float]] = []
    t = 0.0
    last_index = len(segments) - 1
    for i, seg in enumerate(segments):
        dur = max(0.2, float(seg.get("duration") or 0.0))
        words = seg.get("word_timings") if isinstance(seg.get("word_timings"), list) else []
        timed = sentences_from_word_timings(words) if words else []
        if timed:
            for sentence, s0, s1 in timed:
                if not _sentence_allowed_for_mode(sentence, mode):
                    continue
                # Clamp word ends into the probed segment length when available.
                start = t + max(0.0, min(s0, dur))
                end = t + max(start - t + 0.12, min(s1, dur))
                units.append((sentence, start, end))
        else:
            parts = split_caption_roles(str(seg.get("text") or ""))
            allowed = [p[1] for p in parts if _role_allowed(p[0], mode)]
            sentences: list[str] = []
            for piece in allowed:
                sentences.extend(split_sentences(piece))
            if not sentences:
                t += dur
                if i < last_index:
                    t += pause
                continue
            weights = [max(1, len(s)) for s in sentences]
            weight_sum = float(sum(weights))
            cursor = t
            for sentence, weight in zip(sentences, weights, strict=False):
                share = dur * (weight / weight_sum)
                units.append((sentence, cursor, cursor + share))
                cursor += share
        t += dur
        if i < last_index:
            t += pause
    if not units:
        return []
    fitted = _fit_units_to_audio(units, total) if total > 0 else units
    cues: list[CaptionCue] = []
    i = 0
    n_sent = len(fitted)
    while i < n_sent:
        group = fitted[i : i + SENTENCES_PER_CUE]
        blob = " ".join(item[0] for item in group).strip()
        wrapped = _wrap_chunk(blob, max_chars, MAX_CAPTION_LINES) if blob else ""
        start = group[0][1]
        end = group[-1][2]
        if total > 0:
            start = min(max(0.0, start), total)
            end = min(max(start + 0.12, end), total)
        if wrapped and end > start + 0.12:
            cues.append(CaptionCue(start=round(start, 3), end=round(end, 3), text=wrapped, language=lang))
        i += SENTENCES_PER_CUE
    if total > 0 and cues:
        cues[-1].end = min(max(cues[-1].end, cues[-1].start + 0.2), total)
    return cues


def split_caption_text(text: str, max_chars: int = MAX_CAPTION_CHARS, max_lines: int = MAX_CAPTION_LINES) -> list[str]:
    """Flow captions one sentence at a time (school text), wrapped to 2–3 short lines."""
    sentences = split_sentences(text)
    if not sentences:
        return []
    chunks: list[str] = []
    for group in pair_sentences(sentences, SENTENCES_PER_CUE):
        blob = " ".join(group).strip()
        if blob:
            chunks.append(_wrap_chunk(blob, max_chars, max_lines))
    return [c for c in chunks if c.strip()]


def _hard_wrap(text: str, limit: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    cur = ""
    for word in words:
        trial = f"{cur} {word}".strip()
        if len(trial) <= limit or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def _wrap_chunk(text: str, max_chars: int, max_lines: int) -> str:
    words = text.split()
    lines: list[str] = []
    cur = ""
    for word in words:
        trial = f"{cur} {word}".strip()
        if len(trial) <= max_chars or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
            if len(lines) >= max_lines:
                break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip() + "…"
    return "\n".join(lines)


_HEADER_TITLE = re.compile(
    r"believers manna today|la manne quotidienne|manna ya waaminio|"
    r"man[aá] di[aá]rio|a man[aá] dos crentes|devocional di[aá]rio",
    re.IGNORECASE,
)
_HEADER_LABEL = re.compile(
    r"(topic|th[eè]me|mada|tema|week focus|month theme|focus de la semaine|"
    r"msisitizo wa wiki|foco da semana|mada ya mwezi|tema do m|"
    r"written |r[eé]dig[eé]e|imeandikwa|escrito por|escrito pelo|"
    r"devocional di[aá]rio|d[eé]votion quotidienne|ibada ya kila siku|"
    r"\bdate\s*:|\btarehe\s*:|\bdata\s*:)",
    re.IGNORECASE,
)
_VERSE_LABEL = re.compile(
    r"(memory verse|verset\s*[àa]\s*m[ée]moriser|mstari wa kukariri|vers[ií]culo para memorizar)",
    re.IGNORECASE,
)
_BODY_MARK = re.compile(
    r"(devotional insight|r[ée]flexion|tafakari ya leo|reflex[aã]o|"
    r"powerful prayer|action steps|hoja za maombi|pontos de ora|"
    r"hatua za kuchukua|a[cç][oõ]es para hoje)",
    re.IGNORECASE,
)
_ROLE_SPLIT = re.compile(
    r"(?=(?:Memory Verse|Verset à mémoriser|Mstari wa Kukariri|Versículo para Memorizar|"
    r"Devotional Insight|Tafakari ya Leo|Powerful Prayer|Action Steps|"
    r"Hoja za Maombi|Pontos de Ora[cç][aã]o|Hatua za Kuchukua|"
    r"BELIEVERS MANNA TODAY|LA MANNE QUOTIDIENNE|MANNA YA WAAMINIO|"
    r"A MANÁ DOS CRENTES|DEVOCIONAL DIÁRIO|MANÁ DIÁRIO))",
    re.IGNORECASE,
)


def is_memory_verse_text(text: str) -> bool:
    blob = re.sub(r"\s+", " ", (text or "")).strip()
    if not blob or not _VERSE_LABEL.search(blob):
        return False
    if _BODY_MARK.search(blob) and _VERSE_LABEL.search(blob):
        verse_at = _VERSE_LABEL.search(blob).start()
        body_at = _BODY_MARK.search(blob).start()
        return verse_at < body_at and body_at - verse_at < 900 and len(blob) < 1200
    return True


def is_intro_header_text(text: str) -> bool:
    """True for title/author/date/topic/week/month intro — not body, not verse-only."""
    blob = re.sub(r"\s+", " ", (text or "")).strip()
    if not blob:
        return True
    if is_memory_verse_text(blob) and not _HEADER_TITLE.search(blob) and len(_HEADER_LABEL.findall(blob)) == 0:
        return False
    if _HEADER_TITLE.search(blob):
        return True
    labels = len(_HEADER_LABEL.findall(blob))
    if labels >= 2:
        return True
    if labels >= 1 and len(blob) < 480:
        return True
    return False


def split_caption_roles(text: str) -> list[tuple[str, str]]:
    """Split one spoken segment into header / verse / body spans without changing source audio."""
    blob = (text or "").strip()
    if not blob:
        return []
    pieces = [p.strip() for p in _ROLE_SPLIT.split(blob) if p and p.strip()]
    if not pieces:
        pieces = [blob]
    out: list[tuple[str, str]] = []
    for piece in pieces:
        if is_memory_verse_text(piece) and _BODY_MARK.search(piece):
            m = _BODY_MARK.search(piece)
            verse = piece[: m.start()].strip()
            body = piece[m.start() :].strip()
            if verse:
                out.append(("verse", verse))
            if body:
                out.append(("body", body))
            continue
        if is_memory_verse_text(piece):
            out.append(("verse", piece))
        elif is_intro_header_text(piece):
            out.append(("header", piece))
        else:
            out.append(("body", piece))
    return out or [("body", blob)]


def _role_allowed(role: str, mode: str) -> bool:
    if mode == CAPTION_ALL:
        return True
    if mode == CAPTION_BODY:
        return role == "body"
    return role in {"body", "verse"}


def captions_for_language(
    d: date | str,
    language: str,
    *,
    audio_duration: float = 0.0,
    base: Path | None = None,
    skip_header: bool = True,
    caption_mode: str | None = None,
) -> list[CaptionCue]:
    block = load_production_block(d, language, base=base)
    pause_ms = block.get("pause_ms")
    if pause_ms is None:
        pause_ms = 500
    try:
        pause_sec = max(0.0, float(pause_ms) / 1000.0)
    except (TypeError, ValueError):
        pause_sec = 0.5
    segs = load_language_segments(d, language, base=base)
    return caption_cues_from_segments(
        segs,
        pause_sec=pause_sec,
        audio_duration=audio_duration,
        language=language,
        skip_header=skip_header,
        caption_mode=caption_mode,
    )


def _chunk_sentences(sentences: list[str], n: int) -> list[str]:
    if n <= 0:
        return []
    if not sentences:
        return [""] * n
    if len(sentences) <= n:
        out = list(sentences) + [""] * (n - len(sentences))
        return out
    groups: list[list[str]] = [[] for _ in range(n)]
    for i, sentence in enumerate(sentences):
        groups[min(n - 1, int(i * n / len(sentences)))].append(sentence)
    return [" ".join(g).strip() for g in groups]


def align_text_to_cues(text: str, timing: list[CaptionCue], language: str) -> list[CaptionCue]:
    """Keep Swahili voice clocks; display another language's transcript on those clocks."""
    blob = (text or "").strip()
    if not blob or not timing:
        return []
    parts = _chunk_sentences(split_sentences(blob) or [blob], len(timing))
    out: list[CaptionCue] = []
    for cue, piece in zip(timing, parts, strict=False):
        wrapped = _wrap_chunk(piece, MAX_CAPTION_CHARS, MAX_CAPTION_LINES) if piece else ""
        if not wrapped:
            continue
        out.append(
            CaptionCue(start=cue.start, end=cue.end, text=wrapped, language=language)
        )
    return out


def load_hhr_transcripts(d: date | str, *, base: Path | None = None) -> tuple[str, str]:
    from bmt_voice_studio.video.discovery import resolve_daily_project_dir

    root = resolve_daily_project_dir(freeze_devotional_date(d), base=base)
    rw_path = root / "SOURCE" / "kinyarwanda_transcript.txt"
    en_path = root / "SOURCE" / "english_captions.txt"
    rw = rw_path.read_text(encoding="utf-8") if rw_path.is_file() else ""
    en = en_path.read_text(encoding="utf-8") if en_path.is_file() else ""
    return rw, en


def hhr_dual_captions(
    d: date | str,
    *,
    audio_duration: float = 0.0,
    base: Path | None = None,
    kinyarwanda_text: str = "",
    english_caption_text: str = "",
    skip_header: bool = True,
    caption_mode: str | None = None,
) -> list[CaptionCue]:
    timing = captions_for_language(
        d,
        "sw",
        audio_duration=audio_duration,
        base=base,
        skip_header=skip_header,
        caption_mode=caption_mode,
    )
    rw_text, en_text = load_hhr_transcripts(d, base=base)
    rw_text = (kinyarwanda_text or rw_text or "").strip()
    en_text = (english_caption_text or en_text or "").strip()
    cues: list[CaptionCue] = []
    cues.extend(align_text_to_cues(rw_text, timing, "rw"))
    cues.extend(align_text_to_cues(en_text, timing, "en"))
    if not cues and timing:
        return timing
    return cues


def shift_caption_cues(cues: list[CaptionCue], offset: float) -> list[CaptionCue]:
    """Shift speech-relative cues onto the muxed video timeline (intro pad)."""
    delta = float(offset or 0.0)
    if abs(delta) < 0.001:
        return list(cues)
    out: list[CaptionCue] = []
    for cue in cues:
        out.append(
            CaptionCue(
                start=round(float(cue.start) + delta, 3),
                end=round(float(cue.end) + delta, 3),
                text=cue.text,
                language=cue.language,
            )
        )
    return out


def clip_caption_cues(
    cues: list[CaptionCue],
    *,
    hide_ranges: list[tuple[float, float]] | None = None,
) -> list[CaptionCue]:
    """Trim cues so they do not play during exclusive intro/outro scenes."""
    ranges = [
        (float(start), float(end))
        for start, end in (hide_ranges or [])
        if float(end) - float(start) > 0.05
    ]
    if not ranges:
        return list(cues)
    out: list[CaptionCue] = []
    for cue in cues:
        pieces = [(float(cue.start), float(cue.end))]
        for hide_start, hide_end in ranges:
            nxt: list[tuple[float, float]] = []
            for start, end in pieces:
                if end <= hide_start or start >= hide_end:
                    nxt.append((start, end))
                    continue
                if start < hide_start:
                    nxt.append((start, min(end, hide_start)))
                if end > hide_end:
                    nxt.append((max(start, hide_end), end))
            pieces = nxt
        for start, end in pieces:
            if end - start >= 0.12 and (cue.text or "").strip():
                out.append(
                    CaptionCue(
                        start=round(start, 3),
                        end=round(end, 3),
                        text=cue.text,
                        language=cue.language,
                    )
                )
    return out


def _ass_timestamp(seconds: float) -> str:
    t = max(0.0, float(seconds))
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    return f"{h:d}:{m:02d}:{s:05.2f}"


def hex_to_ass_color(value: str, *, default: str = "#FFFFFF", alpha: str = "00") -> str:
    from bmt_voice_studio.video.models import hex_to_rgb

    r, g, b = hex_to_rgb(value, hex_to_rgb(default, (255, 255, 255)))
    return f"&H{alpha}{b:02X}{g:02X}{r:02X}"


def write_ass(
    cues: list[CaptionCue],
    dest: Path,
    *,
    width: int = 1080,
    height: int = 1920,
    style=None,
    motion: bool = False,
) -> Path:
    """BMT CLEAN CAPTIONS with optional voice-timed gentle upward motion.

    ``motion=True`` keeps the existing sentence/voice timing but glides each
    devotional sentence a few pixels upward while it is spoken. The movement
    stays inside the 9:16 safe area and does not convert the script into a
    separate, unsynchronised marquee/teleprompter layer.
    """
    from bmt_voice_studio.video.models import TextStyle

    text_style = (style or TextStyle()).normalized()
    dest.parent.mkdir(parents=True, exist_ok=True)
    margin_v = max(160, int(round(height * 0.10)))
    margin_lr = max(56, int(round(width * 0.08)))
    fontsize = max(18, int(round(text_style.font_size * max(1, int(width)) / 1080.0)))
    langs = {(cue.language or "en").strip().lower() for cue in cues}
    dual = "rw" in langs
    primary = hex_to_ass_color(text_style.text_color, default="#E89430")
    outline = hex_to_ass_color(text_style.stroke_color, default="#0A204A")
    if dual:
        primary = hex_to_ass_color("#F4F7F2", default="#F4F7F2")
        outline = hex_to_ass_color("#0A2E22", default="#0A2E22")
    # ASS Outline paints heavier than Pillow stroke_width — keep modest but always visible.
    stroke = max(3, min(8, int(round(int(text_style.stroke_width) * 0.65))))
    border_style = 1
    outline_w = stroke
    rw_size = max(fontsize + 10, int(round(fontsize * 1.18)))
    en_size = max(18, int(round(fontsize * 0.72)))
    en_margin = margin_v + max(88, int(round(rw_size * 2.1)))
    styles = [
        f"Style: Default,Arial,{fontsize},{primary},{primary},{outline},&HFF000000,"
        f"0,0,0,0,100,100,0,0,{border_style},{outline_w},0,2,{margin_lr},{margin_lr},{margin_v},1"
    ]
    if dual:
        styles = [
            f"Style: Kinyarwanda,Arial,{rw_size},{primary},{primary},{outline},&HFF000000,"
            f"1,0,0,0,100,100,0,0,{border_style},{outline_w},0,2,{margin_lr},{margin_lr},{margin_v},1",
            f"Style: English,Arial,{en_size},{primary},{primary},{outline},&HFF000000,"
            f"0,0,0,0,100,100,0,0,{border_style},{max(2, outline_w - 1)},0,2,{margin_lr},{margin_lr},{en_margin},1",
        ]
    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "WrapStyle: 0\n"
        f"PlayResX: {int(width)}\n"
        f"PlayResY: {int(height)}\n"
        "ScaledBorderAndShadow: no\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        + "\n".join(styles)
        + "\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    lines = [header]
    anchor_x = max(1, int(width) // 2)
    anchor_y = max(1, int(height) - margin_v)
    motion_px = max(8, min(24, int(round(max(1, int(height)) * 0.008))))
    for cue in cues:
        text = (cue.text or "").replace("\r", "").replace("\n", r"\N")
        text = text.replace("{", "(").replace("}", ")")
        if motion:
            # Alignment=2 means the coordinates are the bottom-centre anchor.
            # Keep both endpoints inside the same safe lower caption region.
            # Start exactly on the configured bottom safe-margin anchor, then
            # glide upward. Never move closer to the bottom edge than margin_v.
            start_y = anchor_y
            end_y = max(int(height) // 2, anchor_y - motion_px)
            duration_ms = max(1, int(round(max(0.001, cue.end - cue.start) * 1000.0)))
            text = (
                rf"{{\move({anchor_x},{start_y},{anchor_x},{end_y},0,{duration_ms})"
                rf"\fad(120,120)}}" + text
            )
        if dual:
            style_name = "Kinyarwanda" if (cue.language or "").lower() == "rw" else "English"
        else:
            style_name = "Default"
        lines.append(
            f"Dialogue: 0,{_ass_timestamp(cue.start)},{_ass_timestamp(cue.end)},{style_name},,0,0,0,,{text}\n"
        )
    dest.write_text("".join(lines), encoding="utf-8")
    return dest


def render_caption_preview(
    style=None,
    text: str = "Seek first the kingdom of God",
    *,
    width: int = 180,
    height: int = 320,
    background: tuple[int, int, int, int] | None = (15, 20, 28, 255),
):
    """9:16 still of a sample caption using the same type settings as the render."""
    from PIL import Image, ImageDraw

    from bmt_voice_studio.video.models import TextStyle, hex_to_rgb
    from bmt_voice_studio.video.title_cards import load_font, wrap_text

    text_style = (style or TextStyle()).normalized()
    bg = background if background is not None else (0, 0, 0, 0)
    img = Image.new("RGBA", (max(72, int(width)), max(128, int(height))), bg)
    draw = ImageDraw.Draw(img)
    fs = max(11, int(round(text_style.font_size * img.width / 1080.0)))
    font = load_font(fs, bold=True)
    margin = max(8, int(img.width * 0.08))
    sample = (text or "").strip() or "Seek first the kingdom of God"
    lines = wrap_text(draw, sample, font, img.width - 2 * margin, 3) or [sample]
    fill = (*hex_to_rgb(text_style.text_color), 255)
    stroke_fill = (*hex_to_rgb(text_style.stroke_color, (0, 0, 0)), 255)
    stroke = max(0, int(round(text_style.stroke_width * img.width / 1080.0)))
    gap = max(2, int(fs * 0.22))
    block_h = 0
    sizes = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font, stroke_width=stroke)
        sizes.append((bbox[2] - bbox[0], bbox[3] - bbox[1]))
        block_h += (bbox[3] - bbox[1]) + gap
    y = img.height - max(18, int(img.height * 0.12)) - block_h
    for line, (tw, th) in zip(lines, sizes, strict=False):
        x = max(margin, (img.width - tw) // 2)
        draw.text(
            (x, y),
            line,
            font=font,
            fill=fill,
            stroke_width=stroke,
            stroke_fill=stroke_fill,
        )
        y += th + gap
    return img


def ffmpeg_ass_filter(ass_path: Path) -> str:
    raw = str(ass_path).replace("\\", "/")
    escaped = raw.replace(":", "\\:").replace("'", r"\'")
    return f"ass='{escaped}'"


def cues_language_isolated(cues: list[CaptionCue], language: str) -> bool:
    lang = (language or "en").strip().lower()
    return all(c.language == lang for c in cues)
