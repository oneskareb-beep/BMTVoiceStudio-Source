"""Daily BMT script validation (reuses v1.0 curly-brace parser)."""

from __future__ import annotations

from dataclasses import dataclass

from bmt_voice_studio.core.models import Speaker
from bmt_voice_studio.core.parser import parse_speaker_script_source


@dataclass
class ScriptValidation:
    ok: bool
    segment_count: int
    male_count: int
    female_count: int
    errors: list[str]
    status: str  # READY | SCRIPT ERROR | EMPTY

    @property
    def label(self) -> str:
        if self.status == "EMPTY":
            return "EMPTY"
        if self.ok:
            return "READY"
        return "SCRIPT ERROR"


def validate_daily_script(text: str) -> ScriptValidation:
    raw = (text or "").strip()
    if not raw:
        return ScriptValidation(
            ok=False,
            segment_count=0,
            male_count=0,
            female_count=0,
            errors=["Script is empty."],
            status="EMPTY",
        )
    parsed = parse_speaker_script_source(text)
    errors = [e.message for e in parsed.errors if e.severity == "error"]
    male = sum(1 for s in parsed.segments if s.speaker == Speaker.MALE)
    female = sum(1 for s in parsed.segments if s.speaker == Speaker.FEMALE)
    ok = parsed.ok and len(parsed.segments) > 0 and not errors
    return ScriptValidation(
        ok=ok,
        segment_count=len(parsed.segments),
        male_count=male,
        female_count=female,
        errors=errors,
        status="READY" if ok else "SCRIPT ERROR",
    )


def overall_status(english_ok: bool | None, french_ok: bool | None, *, gen_en: bool, gen_fr: bool) -> str:
    """Compute daily production status from language results (legacy EN/FR)."""
    return overall_status_selected(
        {
            "en": english_ok if gen_en else None,
            "fr": french_ok if gen_fr else None,
        },
        selected=["en"] * bool(gen_en) + ["fr"] * bool(gen_fr),
    )


def overall_status_selected(
    results: dict[str, bool | None],
    *,
    selected: list[str],
) -> str:
    """Status from selected languages only (True/False/None)."""
    if not selected:
        return "FAILED"
    wanted = [results.get(lid) for lid in selected]
    if all(v is True for v in wanted):
        return "COMPLETE"
    if any(v is True for v in wanted) and any(v is False for v in wanted):
        return "WARNING"
    if any(v is None for v in wanted):
        return "GENERATING"
    return "FAILED"
