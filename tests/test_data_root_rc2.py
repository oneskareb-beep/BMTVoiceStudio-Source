"""RC2 data-root, migration, caption modes, and identity tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bmt_voice_studio import __version__
from bmt_voice_studio.build_info import BUILD_LABEL
from bmt_voice_studio.config.data_root import (
    KIND_CANONICAL,
    KIND_LEGACY,
    decide_startup_root,
    discover_library_candidates,
    is_populated_library,
    persist_active_root,
    physical_documents_location,
    canonical_documents_location,
)
from bmt_voice_studio.config.migrate_library import (
    copy_library,
    migrate_library,
    preflight_migration,
    verify_copy,
)
from bmt_voice_studio.config.paths import (
    EXPORT_DIR_NAME,
    daily_exports_root,
    logs_dir,
    projects_dir,
    reports_dir,
    temp_work_dir,
    user_data_root,
    video_exports_root,
    video_temp_root,
)
from bmt_voice_studio.video.captions import (
    CAPTION_ALL,
    CAPTION_BODY,
    CAPTION_BODY_VERSE,
    caption_cues_from_segments,
    is_intro_header_text,
    is_memory_verse_text,
    normalize_caption_mode,
)
from bmt_voice_studio.video.models import VideoProject
from bmt_voice_studio.release_scan import STABLE_12_SHA256, STABLE_12_ZIP_NAME, sha256_file


def _populate_library(root: Path, *, stamp: str = "EN") -> Path:
    daily = root / "Exports" / "Daily" / "BMT_2026_08_14"
    daily.mkdir(parents=True, exist_ok=True)
    (daily / f"{stamp}_FINAL.mp3").write_bytes(b"mp3")
    (daily / "production.json").write_text("{}", encoding="utf-8")
    hist = root / "History"
    hist.mkdir(parents=True, exist_ok=True)
    (hist / "daily.json").write_text("[]", encoding="utf-8")
    proj = root / "Projects"
    proj.mkdir(parents=True, exist_ok=True)
    (proj / "autosave.json").write_text("{}", encoding="utf-8")
    video = root / "Exports" / "Video" / "BMT_2026_08_14"
    video.mkdir(parents=True, exist_ok=True)
    (video / f"{stamp}.mp4").write_bytes(b"mp4")
    return root


def test_rc2_identity():
    """Stable 1.3.0 FINAL artifacts remain; runtime identity is 1.3.36 FINAL."""
    root = Path(__file__).resolve().parents[1]
    assert __version__ == "1.3.36"
    assert (root / "VERSION").read_text(encoding="utf-8").strip() == "1.3.36"
    assert BUILD_LABEL == "Final"
    about = (root / "bmt_voice_studio" / "ui" / "dialogs" / "about.py").read_text(encoding="utf-8")
    assert "BUILD_LABEL" in about
    assert (root / "BMTVoiceStudio-1.3.0.spec").is_file()
    assert (root / "BMTVoiceStudio-1.3.1.spec").is_file()
    assert (root / "BMTVoiceStudio-1.3.2.spec").is_file()
    assert (root / "BMTVoiceStudio-1.3.3.spec").is_file()
    assert (root / "BMTVoiceStudio-1.3.4.spec").is_file()
    assert (root / "BMTVoiceStudio-1.3.5.spec").is_file()
    assert (root / "BMTVoiceStudio-1.3.6.spec").is_file()
    assert (root / "BMTVoiceStudio-1.3.7.spec").is_file()
    assert (root / "BMTVoiceStudio-1.3.8.spec").is_file()
    assert (root / "BMTVoiceStudio-1.3.9.spec").is_file()
    assert (root / "BMTVoiceStudio-1.3.10.spec").is_file()
    assert (root / "BMTVoiceStudio-1.3.11.spec").is_file()
    assert (root / "BMTVoiceStudio-1.3.12.spec").is_file()
    assert (root / "BMTVoiceStudio-1.3.13.spec").is_file()
    assert (root / "BMTVoiceStudio-1.3.14.spec").is_file()
    assert (root / "BMTVoiceStudio-1.3.15.spec").is_file()
    assert (root / "BMTVoiceStudio-1.3.16.spec").is_file()
    assert (root / "BMTVoiceStudio-1.3.17.spec").is_file()
    assert (root / "BMTVoiceStudio-1.3.33.spec").is_file()
    assert (root / "BMTVoiceStudio-1.3.36.spec").is_file()
    zip12 = root / "release" / STABLE_12_ZIP_NAME
    if not zip12.is_file():
        pytest.skip("historical 1.2 release zip not present on this machine")
    assert sha256_file(zip12) == STABLE_12_SHA256
    assert not (root / "release" / "BMTVoiceStudio-1.3.0-RC2-Windows-x64-Portable.zip").exists()
    from bmt_voice_studio.ui.theme import STABLE_130_SHA256, STABLE_130_ZIP_NAME

    zip130 = root / "release" / STABLE_130_ZIP_NAME
    if not zip130.is_file():
        pytest.skip("historical 1.3.0 release zip not present on this machine")
    assert sha256_file(zip130) == STABLE_130_SHA256


def test_final_130_packaging_layout():
    root = Path(__file__).resolve().parents[1]
    spec = (root / "BMTVoiceStudio-1.3.0.spec").read_text(encoding="utf-8")
    assert 'name="BMTVoiceStudio-1.3.0"' in spec
    assert 'name="BMTVoiceStudio-1.3.0-RC2"' not in spec
    assert (root / "tools" / "package_final_130.py").is_file()
    zip12 = root / "release" / STABLE_12_ZIP_NAME
    if not zip12.is_file():
        pytest.skip("historical 1.2 release zip not present on this machine")
    assert sha256_file(zip12) == STABLE_12_SHA256

def test_single_data_root_authority(tmp_path: Path, monkeypatch):
    docs = tmp_path / "OneDrive" / "Documents"
    docs.mkdir(parents=True)
    monkeypatch.setenv("BMT_DOCUMENTS_DIR", str(docs))
    monkeypatch.setenv("BMT_PHYSICAL_DOCUMENTS_DIR", str(tmp_path / "Documents"))
    monkeypatch.delenv("BMT_DATA_ROOT", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "la"))
    root = user_data_root()
    assert root == docs / EXPORT_DIR_NAME
    assert daily_exports_root().parent.parent == root
    assert video_exports_root().parent.parent == root
    assert logs_dir().parent == root
    assert reports_dir().parent == root
    assert projects_dir().parent == root
    assert temp_work_dir().parent == root
    assert video_temp_root().parent.parent == root
    studio = Path(__file__).resolve().parents[1] / "bmt_voice_studio"
    offenders = []
    for path in studio.rglob("*.py"):
        if path.name in {"production_batch.py"}:
            continue
        text = path.read_text(encoding="utf-8")
        if "OneDrive\\Documents\\BMT Voice Studio" in text or "OneDrive/Documents/BMT Voice Studio" in text:
            offenders.append(str(path))
        if 'Path.home() / "Documents" / "BMT Voice Studio"' in text:
            offenders.append(str(path))
    assert offenders == []


def test_legacy_and_onedrive_documents_detection(tmp_path: Path, monkeypatch):
    profile = tmp_path / "Users" / "someone"
    legacy_docs = profile / "Documents"
    canonical_docs = profile / "OneDrive" / "Documents"
    monkeypatch.setenv("USERPROFILE", str(profile))
    monkeypatch.setenv("BMT_PHYSICAL_DOCUMENTS_DIR", str(legacy_docs))
    monkeypatch.setenv("BMT_DOCUMENTS_DIR", str(canonical_docs))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "la"))
    monkeypatch.delenv("BMT_DATA_ROOT", raising=False)
    _populate_library(legacy_docs / EXPORT_DIR_NAME, stamp="EN")
    (canonical_docs / EXPORT_DIR_NAME).mkdir(parents=True)
    assert physical_documents_location() == legacy_docs
    assert canonical_documents_location() == canonical_docs
    cands = discover_library_candidates()
    kinds = {c.kind: c for c in cands}
    assert KIND_LEGACY in kinds and kinds[KIND_LEGACY].populated
    assert KIND_CANONICAL in kinds and not kinds[KIND_CANONICAL].populated
    decision = decide_startup_root(allow_prompt=True)
    assert decision.needs_prompt is False
    assert decision.root == legacy_docs / EXPORT_DIR_NAME
    assert decision.reason == "single"


def test_multiple_library_decision_requires_prompt(tmp_path: Path, monkeypatch):
    legacy_docs = tmp_path / "Documents"
    canonical_docs = tmp_path / "OneDrive" / "Documents"
    monkeypatch.setenv("BMT_PHYSICAL_DOCUMENTS_DIR", str(legacy_docs))
    monkeypatch.setenv("BMT_DOCUMENTS_DIR", str(canonical_docs))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "la"))
    monkeypatch.delenv("BMT_DATA_ROOT", raising=False)
    monkeypatch.delenv("BMT_SKIP_LIBRARY_DIALOG", raising=False)
    _populate_library(legacy_docs / EXPORT_DIR_NAME, stamp="EN")
    _populate_library(canonical_docs / EXPORT_DIR_NAME, stamp="FR")
    decision = decide_startup_root(allow_prompt=True)
    assert decision.needs_prompt is True
    assert decision.reason == "multi"
    assert len([c for c in decision.candidates if c.populated]) >= 2


def test_use_existing_library_persists_custom_root(tmp_path: Path, monkeypatch):
    legacy_docs = tmp_path / "Documents"
    canonical_docs = tmp_path / "OneDrive" / "Documents"
    monkeypatch.setenv("BMT_PHYSICAL_DOCUMENTS_DIR", str(legacy_docs))
    monkeypatch.setenv("BMT_DOCUMENTS_DIR", str(canonical_docs))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "la"))
    monkeypatch.delenv("BMT_DATA_ROOT", raising=False)
    legacy = _populate_library(legacy_docs / EXPORT_DIR_NAME, stamp="EN")
    persist_active_root(legacy, mode="custom")
    from bmt_voice_studio.config import settings as settings_mod

    settings_mod._settings = None
    assert user_data_root() == legacy
    assert daily_exports_root().parent.parent == legacy
    assert video_exports_root().parent.parent == legacy
    assert (legacy / "Exports" / "Daily" / "BMT_2026_08_14" / "EN_FINAL.mp3").is_file()
    # no duplicate copy into canonical
    assert not is_populated_library(canonical_docs / EXPORT_DIR_NAME)


def test_fresh_machine_creates_canonical_root(tmp_path: Path, monkeypatch):
    docs = tmp_path / "OneDrive" / "Documents"
    monkeypatch.setenv("BMT_DOCUMENTS_DIR", str(docs))
    monkeypatch.setenv("BMT_PHYSICAL_DOCUMENTS_DIR", str(tmp_path / "Documents"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "la"))
    monkeypatch.delenv("BMT_DATA_ROOT", raising=False)
    decision = decide_startup_root(allow_prompt=True)
    assert decision.needs_prompt is False
    assert decision.reason == "fresh"
    root = user_data_root()
    assert root == docs / EXPORT_DIR_NAME
    assert root.is_dir()


def test_migration_preflight_copy_conflict_verify(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "la"))
    src = _populate_library(tmp_path / "legacy" / EXPORT_DIR_NAME, stamp="EN")
    dest = tmp_path / "canonical" / EXPORT_DIR_NAME
    dest.mkdir(parents=True)
    # colliding different file
    clash = dest / "Exports" / "Daily" / "BMT_2026_08_14"
    clash.mkdir(parents=True)
    (clash / "EN_FINAL.mp3").write_bytes(b"other")
    pre = preflight_migration(src, dest)
    assert pre["ok"] is True
    assert pre["files_found"] >= 4
    assert pre["destination_writable"] is True
    copied = copy_library(src, dest)
    assert copied["files_copied"] >= 1
    assert copied["conflicts"]
    verify = verify_copy(src, dest)
    assert verify["ok"] is True
    alts = list(clash.glob("EN_FINAL__from_other_library_*.mp3"))
    assert alts
    assert (src / "Exports" / "Daily" / "BMT_2026_08_14" / "EN_FINAL.mp3").is_file()


def test_migrate_library_activates_destination(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "la"))
    monkeypatch.setenv("BMT_DOCUMENTS_DIR", str(tmp_path / "OneDrive" / "Documents"))
    monkeypatch.setenv("BMT_PHYSICAL_DOCUMENTS_DIR", str(tmp_path / "Documents"))
    monkeypatch.delenv("BMT_DATA_ROOT", raising=False)
    src = _populate_library(tmp_path / "Documents" / EXPORT_DIR_NAME, stamp="EN")
    dest = tmp_path / "OneDrive" / "Documents" / EXPORT_DIR_NAME
    result = migrate_library(src, dest)
    assert result["ok"] is True
    assert result["activated_root"] == str(dest)
    assert Path(result["report_path"]).is_file()
    payload = json.loads(Path(result["report_path"]).read_text(encoding="utf-8"))
    for key in (
        "source_root",
        "destination_root",
        "files_found",
        "files_copied",
        "files_skipped",
        "conflicts",
        "errors",
        "verification_result",
        "activated_root",
    ):
        assert key in payload
    from bmt_voice_studio.config import settings as settings_mod

    settings_mod._settings = None
    assert user_data_root() == dest
    assert src.is_dir()
    assert (dest / "Exports" / "Daily" / "BMT_2026_08_14" / "EN_FINAL.mp3").is_file()


def test_persistent_custom_root_survives_restart(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "la"))
    monkeypatch.delenv("BMT_DATA_ROOT", raising=False)
    custom = tmp_path / "D_DRIVE" / "BMT_DATA_TEST"
    persist_active_root(custom, mode="custom")
    from bmt_voice_studio.config import settings as settings_mod

    settings_mod._settings = None
    assert user_data_root() == custom
    (custom / "Exports" / "Daily" / "new.txt").write_text("x", encoding="utf-8")
    settings_mod._settings = None
    assert user_data_root() == custom
    assert (custom / "Exports" / "Daily" / "new.txt").is_file()


def test_app_and_data_location_independence(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "la"))
    monkeypatch.delenv("BMT_DATA_ROOT", raising=False)
    data = tmp_path / "data_root"
    persist_active_root(data, mode="custom")
    from bmt_voice_studio.config import settings as settings_mod

    settings_mod._settings = None
    app_moved = tmp_path / "BMT_APP_TEST"
    app_moved.mkdir()
    monkeypatch.chdir(app_moved)
    assert user_data_root() == data
    assert str(app_moved) not in str(user_data_root())


def test_caption_body_only_and_body_plus_verse():
    header = (
        "BELIEVERS MANNA TODAY. Written by Test Author. Date: 14 August 2026. "
        "Topic: Kingdom Priorities. Week Focus: Obedience. Month Theme: Harvest."
    )
    verse = "Memory Verse: Matthew 6:33 Seek first the kingdom of God."
    body = "Devotional Insight. Walk in the light of the Word today."
    segs = [
        {"text": header, "duration": 5.0},
        {"text": verse, "duration": 4.0},
        {"text": body, "duration": 6.0},
    ]
    assert is_intro_header_text(header)
    assert is_memory_verse_text(verse)
    assert not is_intro_header_text(body)
    body_only = caption_cues_from_segments(segs, caption_mode=CAPTION_BODY, audio_duration=16.0)
    body_verse = caption_cues_from_segments(segs, caption_mode=CAPTION_BODY_VERSE, audio_duration=16.0)
    all_spoken = caption_cues_from_segments(segs, caption_mode=CAPTION_ALL, audio_duration=16.0)
    only_txt = " ".join(c.text for c in body_only)
    verse_txt = " ".join(c.text for c in body_verse)
    all_txt = " ".join(c.text for c in all_spoken)
    assert "Walk in the light" in only_txt
    assert "BELIEVERS MANNA" not in only_txt.upper()
    assert "Memory Verse" not in only_txt
    assert "Walk in the light" in verse_txt
    assert "Matthew 6:33" in verse_txt or "Memory Verse" in verse_txt
    assert "BELIEVERS MANNA" not in verse_txt.upper()
    assert "BELIEVERS" in all_txt.upper()
    assert VideoProject().caption_content == CAPTION_BODY_VERSE
    assert normalize_caption_mode(None, skip_header=True) == CAPTION_BODY_VERSE
    assert normalize_caption_mode(None, skip_header=False) == CAPTION_ALL


def test_upgrade_persistence_use_existing_then_restart(tmp_path: Path, monkeypatch):
    legacy_docs = tmp_path / "Documents"
    canonical_docs = tmp_path / "OneDrive" / "Documents"
    monkeypatch.setenv("BMT_PHYSICAL_DOCUMENTS_DIR", str(legacy_docs))
    monkeypatch.setenv("BMT_DOCUMENTS_DIR", str(canonical_docs))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "la"))
    monkeypatch.delenv("BMT_DATA_ROOT", raising=False)
    legacy = _populate_library(legacy_docs / EXPORT_DIR_NAME, stamp="EN")
    _populate_library(canonical_docs / EXPORT_DIR_NAME, stamp="FR")
    persist_active_root(legacy, mode="custom")
    from bmt_voice_studio.config import settings as settings_mod

    settings_mod._settings = None
    first = user_data_root()
    settings_mod._settings = None
    second = user_data_root()
    assert first == second == legacy
    assert (legacy / "Exports" / "Daily" / "BMT_2026_08_14" / "EN_FINAL.mp3").is_file()
    # writes stay on active root
    (legacy / "Exports" / "Daily" / "new_write.txt").write_text("only-here", encoding="utf-8")
    assert not (canonical_docs / EXPORT_DIR_NAME / "Exports" / "Daily" / "new_write.txt").exists()
