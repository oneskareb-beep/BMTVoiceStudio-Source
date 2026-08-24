"""French spoken list markers — suppression (no Un./Deux. rewrite)."""

from __future__ import annotations

from bmt_voice_studio.core.text_prepare import normalize_french_spoken_numbering


def test_legacy_alias_suppresses_premiere():
    assert normalize_french_spoken_numbering("Premièrement. Père...") == "Père..."


def test_legacy_alias_does_not_emit_un():
    out = normalize_french_spoken_numbering("Deuxièmement. Seigneur...")
    assert out == "Seigneur..."
    assert not out.startswith("Deux")
