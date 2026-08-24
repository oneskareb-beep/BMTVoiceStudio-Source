"""Curly-brace speaker parser: outside = male, {inside} = female."""

from __future__ import annotations

import re

from bmt_voice_studio.core.models import ParseError, ParseResult, Segment, Speaker


_BRACE_OPEN = "{"
_BRACE_CLOSE = "}"


def _line_col(text: str, index: int) -> tuple[int, int]:
    line = text.count("\n", 0, index) + 1
    last_nl = text.rfind("\n", 0, index)
    col = index - last_nl
    return line, col


def parse_speaker_script(text: str) -> ParseResult:
    """Parse script into alternating male/female segments.

    Text outside curly braces → MALE.
    Text inside {...} → FEMALE.
    Nested braces are treated as syntax errors.
    """
    errors: list[ParseError] = []
    segments: list[Segment] = []

    if text is None:
        return ParseResult(errors=[ParseError("Empty script.")])

    # Normalize newlines
    source = text.replace("\r\n", "\n").replace("\r", "\n")

    stack: list[int] = []
    parts: list[tuple[Speaker, str, int, int]] = []
    cursor = 0
    i = 0
    n = len(source)

    while i < n:
        ch = source[i]
        if ch == _BRACE_OPEN:
            if stack:
                line, col = _line_col(source, i)
                errors.append(
                    ParseError(
                        "Nested braces are not allowed.",
                        line=line,
                        column=col,
                    )
                )
                # Continue scanning but mark error
                stack.append(i)
                i += 1
                continue
            # Flush male text before brace
            if i > cursor:
                male = source[cursor:i]
                if male.strip():
                    parts.append((Speaker.MALE, male, cursor, i))
            stack.append(i)
            cursor = i + 1
            i += 1
        elif ch == _BRACE_CLOSE:
            if not stack:
                line, col = _line_col(source, i)
                errors.append(
                    ParseError(
                        "Unmatched closing brace '}'.",
                        line=line,
                        column=col,
                    )
                )
                i += 1
                continue
            open_idx = stack.pop()
            if stack:
                # Nested close after nested open — already reported
                cursor = i + 1
                i += 1
                continue
            female = source[cursor:i]
            if female.strip():
                parts.append((Speaker.FEMALE, female, cursor, i))
            elif female == "":
                errors.append(
                    ParseError(
                        "Empty female section {}.",
                        line=_line_col(source, open_idx)[0],
                        column=_line_col(source, open_idx)[1],
                        severity="warning",
                    )
                )
            cursor = i + 1
            i += 1
        else:
            i += 1

    if stack:
        for open_idx in stack:
            line, col = _line_col(source, open_idx)
            errors.append(
                ParseError(
                    "Unmatched opening brace '{'.",
                    line=line,
                    column=col,
                )
            )
        # Remaining text after unmatched open is ignored for segments
    elif cursor < n:
        male = source[cursor:]
        if male.strip():
            parts.append((Speaker.MALE, male, cursor, n))

    # Build segments with cleaned text (preserve internal newlines, strip edges)
    index = 1
    for speaker, raw, _start, _end in parts:
        cleaned = raw.strip()
        if not cleaned:
            continue
        # Collapse excessive blank lines inside a segment but keep paragraph breaks
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        segments.append(
            Segment(
                index=index,
                speaker=speaker,
                text=cleaned,
            )
        )
        index += 1

    pattern = r"\{(.*?)\}"
    parts = re.split(pattern, source, flags=re.DOTALL)
    segments: list[Segment] = []
    index = 1
    for i, part in enumerate(parts):
        cleaned = part.strip()
        if not cleaned:
            continue
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        speaker = Speaker.MALE if i % 2 == 0 else Speaker.FEMALE
        segments.append(Segment(index=index, speaker=speaker, text=cleaned))
        index += 1

    if not segments and not errors:
        if source.strip():
            # All whitespace-only braces or similar — treat whole as male if no braces
            if _BRACE_OPEN not in source and _BRACE_CLOSE not in source:
                segments.append(
                    Segment(index=1, speaker=Speaker.MALE, text=source.strip())
                )
            else:
                errors.append(ParseError("No speakable segments found."))
        else:
            errors.append(ParseError("Script is empty."))

    return ParseResult(segments=segments, errors=errors)


def parse_speaker_script_source(text: str) -> ParseResult:
    """Parse using the same re.split brace logic as the reference Colab pipeline.

    Text outside ``{...}`` → MALE. Text inside → FEMALE. Segment count is
    determined only by brace positions (no fixed count). A lightweight brace
    balance check flags clearly broken scripts.
    """
    errors: list[ParseError] = []
    if text is None:
        return ParseResult(errors=[ParseError("Empty script.")])

    source = text.replace("\r\n", "\n").replace("\r", "\n")
    if not source.strip():
        return ParseResult(errors=[ParseError("Script is empty.")])

    stack = 0
    for ch in source:
        if ch == _BRACE_OPEN:
            stack += 1
        elif ch == _BRACE_CLOSE:
            if stack > 0:
                stack -= 1
    if stack > 0:
        errors.append(ParseError("Unmatched opening brace '{'."))

    pattern = r"\{(.*?)\}"
    parts = re.split(pattern, source, flags=re.DOTALL)
    segments: list[Segment] = []
    index = 1
    for i, part in enumerate(parts):
        cleaned = part.strip()
        if not cleaned:
            continue
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        speaker = Speaker.MALE if i % 2 == 0 else Speaker.FEMALE
        segments.append(Segment(index=index, speaker=speaker, text=cleaned))
        index += 1

    if not segments and not errors:
        errors.append(ParseError("No speakable segments found."))

    return ParseResult(segments=segments, errors=errors)


def validate_braces(text: str) -> list[ParseError]:
    return parse_speaker_script(text).errors
