"""Locale-aware TTS text preparation — SOURCE unchanged; spoken TTS normalized."""

from __future__ import annotations

import re

# Non-strict mode only: expand "1." lists into language words (then suppression may strip them).
_EN_NUMBERED_LIST = re.compile(
    r"(?m)^(\s*)(\d+)\.\s+",
    re.MULTILINE,
)
_EN_ORDINAL_WORDS = {
    1: "Number one",
    2: "Number two",
    3: "Number three",
    4: "Number four",
    5: "Number five",
    6: "Number six",
    7: "Number seven",
    8: "Number eight",
    9: "Number nine",
    10: "Number ten",
}

_FR_ORDINAL_WORDS = {
    1: "Premièrement",
    2: "Deuxièmement",
    3: "Troisièmement",
    4: "Quatrièmement",
    5: "Cinquièmement",
    6: "Sixièmement",
    7: "Septièmement",
    8: "Huitièmement",
    9: "Neuvièmement",
    10: "Dixièmement",
}

# Trailing list punctuation / separator after a marker (required for word markers).
_SEP = r"(?:\s*[.:,\-–—)]\s+|\s*[.:,\-–—)]\s*$)"

# English list-start markers (paragraph / line start only).
_EN_LIST_MARKER = re.compile(
    r"(?mi)^(\s*)(?:"
    r"number\s+(?:one|two|three|four|five|six|seven|eight|nine|ten)"
    r"|first|second|third|fourth|fifth"
    r"|[1-9]|10"
    r")" + _SEP,
    re.MULTILINE,
)

# French list-start markers (paragraph / line start only).
# Short Un./Deux. require punctuation so "Un homme…" is not stripped.
_FR_LIST_MARKER = re.compile(
    r"(?mi)^(\s*)(?:"
    r"premi[eè]rement|deuxi[eè]mement|troisi[eè]mement|quatri[eè]mement|cinqui[eè]mement"
    r"|sixi[eè]mement|septi[eè]mement|huiti[eè]mement|neuvi[eè]mement|dixi[eè]mement"
    r"|(?:un|deux|trois|quatre|cinq)(?=\s*[.:,\-–—)])"
    r"|[1-9]|10"
    r")" + _SEP,
    re.MULTILINE,
)

# Cache / report tag — bump when spoken suppression rules change.
SPOKEN_LIST_SUPPRESSION_TAG = "spoken_list_marker_suppression_v1"
# Spoken-only French sanitizer. SOURCE unchanged.
FRENCH_SPOKEN_SANITIZE_TAG = "french_spoken_sanitize_langlock_v2"


def sanitize_french_spoken_for_tts(text: str) -> tuple[str, int]:
    """Rewrite spoken French TTS text so Edge is not nudged into English.

    SOURCE / archive text must stay unchanged — apply only to the string sent to Edge.

    Multilingual voices used to speak English on language-name phrases and on
    leftover English BMT headers mixed into a French paste.
    """
    if not text:
        return "", 0
    out = text.replace("\r\n", "\n").replace("\r", "\n")
    replacements = 0

    patterns = [
        # Full availability line (highest priority — segment before "Nous croyons…").
        (
            re.compile(
                r"\bdisponible\s+en\s+anglais\s+et\s+en\s+fran[cç]ais\b",
                re.IGNORECASE,
            ),
            "disponible en version anglaise et en version française",
        ),
        (
            re.compile(r"\ben\s+anglais\s+et\s+en\s+fran[cç]ais\b", re.IGNORECASE),
            "en version anglaise et en version française",
        ),
        (
            re.compile(r"\ben\s+anglais\b", re.IGNORECASE),
            "en version anglaise",
        ),
        (
            re.compile(r"\bEnglish\b"),
            "version anglaise",
        ),
        # English BMT headers if a mixed paste reaches spoken TTS.
        (
            re.compile(r"\bBELIEVERS\s+MANNA\s+TODAY\b", re.IGNORECASE),
            "Manne des croyants aujourd'hui",
        ),
        (
            re.compile(r"\bDAILY\s+DEVOTIONAL\b", re.IGNORECASE),
            "Dévotionnel quotidien",
        ),
        (
            re.compile(r"\bMEMORY\s+VERSE\b", re.IGNORECASE),
            "Verset à mémoriser",
        ),
        (
            re.compile(r"\bPowerful\s+Prayer\s+Points\b", re.IGNORECASE),
            "Points de prière puissants",
        ),
        (
            re.compile(r"\bRemain\s+blessed\b", re.IGNORECASE),
            "Demeurez bénis",
        ),
        (
            re.compile(r"\bWe\s+believe\b", re.IGNORECASE),
            "Nous croyons",
        ),
        (
            re.compile(r"\bFather,\s+thank\s+You\b", re.IGNORECASE),
            "Père, nous te remercions",
        ),
        (
            re.compile(r"\bWritten\s+by\b", re.IGNORECASE),
            "Écrit par",
        ),
    ]
    for pattern, repl in patterns:
        out, n = pattern.subn(repl, out)
        replacements += n
    return out, replacements


def count_system_english_contamination(text: str) -> int:
    """Count English list/spoken markers that must not appear in French TTS text."""
    if not text:
        return 0
    patterns = [
        r"\bNumber (?:one|two|three|four|five|six|seven|eight|nine|ten)\b",
        r"\bRemain blessed\b",
        r"\bWe believe\b",
        r"\bFather, thank You\b",
        r"\bPowerful Prayer Points\b",
        r"\bFirst\.",
        r"\bSecond\.",
        r"\bEnglish\b",
        # Bare language name that Multilingual often speaks in English:
        r"(?i)\ben anglais\b",
    ]
    total = 0
    for pat in patterns:
        total += len(re.findall(pat, text))
    return total


def _expand_numbered_list(text: str, language: str) -> str:
    lang = (language or "").lower()
    use_french = lang.startswith("fr")
    words = _FR_ORDINAL_WORDS if use_french else _EN_ORDINAL_WORDS

    def repl(match: re.Match[str]) -> str:
        indent = match.group(1)
        num = int(match.group(2))
        word = words.get(num)
        if not word:
            return match.group(0)
        return f"{indent}{word}. "

    return _EN_NUMBERED_LIST.sub(repl, text)


def _language_family(language: str) -> str:
    lang = (language or "").lower()
    if lang.startswith("fr"):
        return "fr"
    if lang.startswith("en"):
        return "en"
    if lang.startswith("sw"):
        return "sw"
    if lang.startswith("pt"):
        return "pt"
    return lang.split("-")[0] if lang else ""


def suppress_spoken_list_markers(text: str, language: str = "en") -> str:
    """Remove paragraph/list-start enumeration markers from spoken TTS text.

    SOURCE / editor / archive must stay unchanged — apply only after speaker parsing.
    """
    spoken, _ = suppress_spoken_list_markers_counted(text, language)
    return spoken


def suppress_spoken_list_markers_counted(text: str, language: str = "en") -> tuple[str, int]:
    """Like suppress_spoken_list_markers, also returns removal count."""
    if not text:
        return "", 0
    source = text.replace("\r\n", "\n").replace("\r", "\n")
    family = _language_family(language)
    if family == "fr":
        pattern = _FR_LIST_MARKER
    elif family == "en":
        pattern = _EN_LIST_MARKER
    elif family in {"sw", "pt"}:
        # Architecture hook: language-specific markers can be added safely later.
        # Until approved SW/PT marker lists exist, do not strip numbers from prose.
        return source, 0
    else:
        return source, 0

    count = 0

    def repl(match: re.Match[str]) -> str:
        nonlocal count
        count += 1
        return match.group(1)  # keep indent only; drop marker + separator

    out = pattern.sub(repl, source)
    out = re.sub(r"[ \t]{2,}", " ", out)
    # Avoid blank-only lines collapsing awkwardly — keep newlines as-is.
    return out, count


# Backward-compatible French aliases (now suppress, do not rewrite to Un./Deux.).
def normalize_french_spoken_numbering(text: str) -> str:
    return suppress_spoken_list_markers(text, language="fr")


def normalize_french_spoken_numbering_counted(text: str) -> tuple[str, int]:
    return suppress_spoken_list_markers_counted(text, language="fr")


def prepare_tts_text(
    text: str,
    *,
    language: str = "en",
    strict_source_mode: bool = True,
    allow_normalization: bool = False,
    apply_spoken_list_suppression: bool | None = None,
    apply_french_spoken_numbering: bool | None = None,  # legacy alias
) -> str:
    """Prepare segment text for Edge TTS.

    Strict source mode preserves wording except newline normalization and
    language-aware spoken list-marker suppression for EN/FR TTS.
    """
    if text is None:
        return ""
    source = text.replace("\r\n", "\n").replace("\r", "\n")
    family = _language_family(language)

    if strict_source_mode or not allow_normalization:
        out = source
    elif family in {"fr", "en"}:
        out = _expand_numbered_list(source, language)
    else:
        out = source

    apply = apply_spoken_list_suppression
    if apply is None and apply_french_spoken_numbering is not None:
        # Legacy kwarg: historically French-only; ignore for English when False.
        apply = bool(apply_french_spoken_numbering) if family == "fr" else (family == "en")
    if apply is None:
        apply = family in {"en", "fr"}
    if apply and family in {"en", "fr"}:
        out = suppress_spoken_list_markers(out, language=language)
    return out


def count_english_number_contamination(text: str) -> int:
    """Count English 'Number N' phrases that should not appear in French source."""
    return len(re.findall(r"\bNumber (?:one|two|three|four|five|six|seven|eight|nine|ten)\b", text, re.I))


def count_list_marker_starts(text: str, language: str) -> int:
    """Count list-start markers still present (for live verification)."""
    if not text:
        return 0
    family = _language_family(language)
    source = text.replace("\r\n", "\n").replace("\r", "\n")
    if family == "fr":
        return len(_FR_LIST_MARKER.findall(source))
    if family == "en":
        return len(_EN_LIST_MARKER.findall(source))
    return 0


def count_french_list_adverb_starts(text: str) -> int:
    """Legacy helper — French list-start marker count."""
    return count_list_marker_starts(text, "fr")
