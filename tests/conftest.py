"""Isolate BMT data paths from the developer machine during tests."""

from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def _isolate_bmt_user_dirs(monkeypatch, tmp_path_factory):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    root = tmp_path_factory.mktemp("bmt_iso")
    monkeypatch.setenv("LOCALAPPDATA", str(root / "la"))
    monkeypatch.setenv("BMT_DOCUMENTS_DIR", str(root / "canonical_docs"))
    monkeypatch.setenv("BMT_PHYSICAL_DOCUMENTS_DIR", str(root / "physical_docs"))
    monkeypatch.setenv("BMT_SKIP_LIBRARY_DIALOG", "1")
    monkeypatch.delenv("BMT_DATA_ROOT", raising=False)
    os.environ.pop("BMT_DATA_ROOT", None)
    try:
        from bmt_voice_studio.config import settings as settings_mod

        settings_mod._settings = None
    except Exception:
        pass
    yield
    try:
        from bmt_voice_studio.config import settings as settings_mod

        settings_mod._settings = None
    except Exception:
        pass
