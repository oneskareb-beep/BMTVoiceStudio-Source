"""Release Candidate package hygiene — forbidden names and content patterns."""

from __future__ import annotations

from pathlib import Path

STABLE_12_SHA256 = "ba573221b90c52f579d093e84ac42535b266fbd3c9e47599535cdb2a30b188dc"
STABLE_12_ZIP_NAME = "BMTVoiceStudio-1.2.0-Windows-x64-Portable.zip"

FORBIDDEN_NAMES = {
    ".git",
    ".gitignore",
    ".gitattributes",
    ".cursor",
    ".pytest_cache",
    "__pycache__",
    ".env",
    "credentials.json",
    "id_rsa",
    "id_rsa.pub",
    "id_ed25519",
    "id_ed25519.pub",
    ".ssh",
    "agent-transcripts",
    "qa_outputs",
    "qa_screenshots",
    "pytest.ini",
}

FORBIDDEN_SUFFIXES = {
    ".pyc",
    ".pyo",
}

FORBIDDEN_NAME_SUBSTR = (
    "pytest_cache",
)

FORBIDDEN_TEXT_MARKERS = (
    "BEGIN OPENSSH PRIVATE KEY",
    "BEGIN RSA PRIVATE KEY",
    "BEGIN PRIVATE KEY",
    "AKIA",  # AWS-style key prefix; not expected in this app
    "smtp_password",
    "api_secret",
)

# Paths that belong in the source tree, never the portable RC zip.
FORBIDDEN_RELATIVE_PREFIXES = (
    "tests/",
    "qa_outputs/",
    "qa_screenshots/",
    "agent-transcripts/",
    ".cursor/",
    ".git/",
)


def is_forbidden_path(path: Path, *, root: Path | None = None) -> str:
    """Return a reason if this path must not ship in an RC package, else empty."""
    name = path.name
    lower = name.lower()
    if name in FORBIDDEN_NAMES or lower in {n.lower() for n in FORBIDDEN_NAMES}:
        return f"forbidden name: {name}"
    if path.suffix.lower() in FORBIDDEN_SUFFIXES:
        return f"forbidden suffix: {path.suffix}"
    for token in FORBIDDEN_NAME_SUBSTR:
        if token in lower:
            return f"forbidden token in name: {name}"
    if root is not None:
        try:
            rel = path.relative_to(root).as_posix()
        except ValueError:
            rel = path.as_posix()
        for prefix in FORBIDDEN_RELATIVE_PREFIXES:
            if rel.startswith(prefix) or f"/{prefix}" in f"/{rel}":
                return f"forbidden tree: {rel}"
    return ""


def scan_rc_tree(root: Path) -> list[str]:
    """List hygiene violations under a packaged folder (not the source repo)."""
    hits: list[str] = []
    if not root.exists():
        return [f"missing package root: {root}"]
    for path in root.rglob("*"):
        reason = is_forbidden_path(path, root=root)
        if reason:
            hits.append(f"{path}: {reason}")
            continue
        if path.is_file() and path.suffix.lower() in {".json", ".txt", ".md", ".env", ".ini", ".yml", ".yaml"}:
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for marker in FORBIDDEN_TEXT_MARKERS:
                if marker in text:
                    hits.append(f"{path}: forbidden marker {marker}")
                    break
    return hits


def sha256_file(path: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()
