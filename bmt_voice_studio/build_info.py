"""Runtime / build identity for verifying which binary is running."""

from __future__ import annotations

import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from bmt_voice_studio import __version__

# Stamped by tools/stamp_build.py immediately before packaging.
BUILD_LABEL = "Final"
BUILD_TIMESTAMP = "2026-08-26T13:21:51Z"
BUILD_ID = f"{__version__} — {BUILD_LABEL}"


def _redact(text: str) -> str:
    text = re.sub(r"(?i)([A-Z]:\\Users\\)[^\\/\s]+", r"\1<user>", text)
    text = re.sub(r"(?i)(/Users/)[^/\s]+", r"\1<user>", text)
    return text


def runtime_diagnostics() -> str:
    """Human-readable identity block for About / console (usernames redacted)."""
    exe = Path(sys.executable).resolve()
    argv0 = Path(sys.argv[0]).resolve() if sys.argv else Path(".")
    try:
        import bmt_voice_studio

        pkg_root = Path(bmt_voice_studio.__file__).resolve().parent
        entry = "bmt_voice_studio.app:main"
        pkg_file = Path(bmt_voice_studio.__file__).resolve()
    except Exception as exc:  # noqa: BLE001
        pkg_root = Path("?")
        entry = f"(unavailable: {exc})"
        pkg_file = Path("?")
    frozen = getattr(sys, "frozen", False)
    block = (
        f"BMT Voice Studio {BUILD_ID}\n"
        f"Version: {__version__}\n"
        f"Build timestamp: {BUILD_TIMESTAMP}\n"
        f"Frozen (packaged): {frozen}\n"
        f"sys.executable: {exe}\n"
        f"sys.argv[0]: {argv0}\n"
        f"Entry module: {entry}\n"
        f"Package __file__: {pkg_file}\n"
        f"Application source root: {pkg_root.parent if pkg_root != Path('?') else '?'}"
    )
    return _redact(block)


def stamp_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
