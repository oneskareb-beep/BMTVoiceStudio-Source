"""Filename, hashing, project, fallback logic tests."""

from pathlib import Path

from bmt_voice_studio.core.filenames import sanitize_filename, unique_path
from bmt_voice_studio.core.hashing import needs_regeneration, segment_cache_hash
from bmt_voice_studio.core.models import Segment, Speaker
from bmt_voice_studio.projects.project import ProjectData, ProjectService


def test_sanitize_invalid_chars():
    assert "<" not in sanitize_filename('BMT: "Devotional"*?')
    assert sanitize_filename("") == "untitled"
    assert sanitize_filename("CON") == "_CON"


def test_unique_path(tmp_path: Path):
    p = tmp_path / "final.mp3"
    p.write_bytes(b"x")
    u = unique_path(p)
    assert u.name == "final_2.mp3"
    u.write_bytes(b"y")
    u2 = unique_path(p)
    assert u2.name == "final_3.mp3"


def test_cache_hash_changes_with_text():
    s = Segment(index=1, speaker=Speaker.MALE, text="Hello", voice="v1", rate="-10%", pitch="-3Hz")
    h1 = segment_cache_hash(s)
    s.text = "Hello!"
    h2 = segment_cache_hash(s)
    assert h1 != h2


def test_cache_hash_changes_with_voice():
    s = Segment(index=1, speaker=Speaker.MALE, text="Hello", voice="v1", rate="-10%", pitch="-3Hz")
    h1 = segment_cache_hash(s)
    h2 = segment_cache_hash(s, voice="v2")
    assert h1 != h2


def test_needs_regeneration():
    s = Segment(index=1, speaker=Speaker.MALE, text="Hi", voice="v", cache_hash="abc", audio_path="")
    assert needs_regeneration(s, "abc")  # no audio path
    s.audio_path = "x.mp3"
    assert not needs_regeneration(s, "abc")
    assert needs_regeneration(s, "zzz")
    s.enabled = False
    assert not needs_regeneration(s, "zzz")


def test_project_serialization(tmp_path: Path):
    svc = ProjectService()
    project = svc.new_project("BMT_2026_08_13_FRENCH")
    project.source_text = "Hello {World}"
    project.set_segments(
        [Segment(index=1, speaker=Speaker.MALE, text="Hello"), Segment(index=2, speaker=Speaker.FEMALE, text="World")]
    )
    root = tmp_path / "exports"
    root.mkdir()
    # Force layout under tmp
    project.output_folder = str(svc.ensure_layout(project, root))
    path = svc.save(project, Path(project.output_folder) / "project" / "project.json")
    loaded = svc.load(path)
    assert loaded.name == "BMT_2026_08_13_FRENCH"
    assert len(loaded.get_segments()) == 2
    assert loaded.source_text.startswith("Hello")


def test_export_keeps_assigned_output_folder(tmp_path: Path):
    svc = ProjectService()
    project = svc.new_project("BMT_FOLDER_LOCK")
    custom = tmp_path / "custom_root" / "BMT_FOLDER_LOCK"
    root = svc.ensure_layout(project, tmp_path / "custom_root")
    assert root == custom
    mp3, wav = svc.export_final_names(project)
    assert mp3.parent == custom / "final"
    assert Path(project.output_folder) == custom


def test_audio_ordering_preserved():
    """Segment indices define join order."""
    segs = [
        Segment(index=1, speaker=Speaker.MALE, text="A"),
        Segment(index=2, speaker=Speaker.FEMALE, text="B"),
        Segment(index=3, speaker=Speaker.MALE, text="C"),
    ]
    assert [s.index for s in segs] == [1, 2, 3]
    assert [s.speaker for s in segs] == [Speaker.MALE, Speaker.FEMALE, Speaker.MALE]


def test_provider_fallback_setting_default():
    from bmt_voice_studio.config.settings import AppSettings

    s = AppSettings()
    assert s.auto_piper_fallback is True
    assert s.default_provider == "edge"
