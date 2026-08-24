"""Stamp build_info.py with UTC timestamp and version before packaging."""

from __future__ import annotations

from pathlib import Path

from bmt_voice_studio import __version__
from bmt_voice_studio.build_info import stamp_now


def main() -> int:
    path = Path(__file__).resolve().parents[1] / "bmt_voice_studio" / "build_info.py"
    text = path.read_text(encoding="utf-8")
    ts = stamp_now()
    marker = 'BUILD_TIMESTAMP = "'
    start = text.index(marker) + len(marker)
    end = text.index('"', start)
    text = text[:start] + ts + text[end:]
    # Keep BUILD_ID aligned with package version.
    id_marker = "BUILD_ID = "
    if id_marker in text:
        # BUILD_ID is derived from __version__ at import; ensure label stays production.
        pass
    path.write_text(text, encoding="utf-8")
    print("STAMPED", __version__, ts, "->", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
