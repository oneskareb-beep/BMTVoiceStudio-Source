"""1.3.3 FINAL: Windows icon identity + branded intro/outro timeline."""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

from bmt_voice_studio import __version__
from bmt_voice_studio.build_info import BUILD_LABEL
from bmt_voice_studio.resources import WINDOWS_APP_USER_MODEL_ID, app_icon_path
from bmt_voice_studio.video.branding_audio import music_display_name
from bmt_voice_studio.video.captions import CaptionCue, shift_caption_cues
from bmt_voice_studio.video.composition import branding_pads, overlay_windows, window_is_active
from bmt_voice_studio.video.models import MediaItem, VideoProject
from bmt_voice_studio.video.project_store import load_project, save_project

ROOT = Path(__file__).resolve().parents[1]
ICO = ROOT / "bmt_voice_studio" / "resources" / "bmt_voice_studio.ico"
REQUIRED = {(16, 16), (20, 20), (24, 24), (32, 32), (40, 40), (48, 48), (64, 64), (128, 128), (256, 256)}
STABLE_131 = "1abd8500897136120cd610049b81210c7eae2ac5e3526995954166b4428dc9a2"


def _ico_sizes(path: Path) -> set[tuple[int, int]]:
    data = path.read_bytes()
    _reserved, itype, count = struct.unpack_from("<HHH", data)
    sizes = set()
    for i in range(count):
        w, h = data[6 + i * 16], data[7 + i * 16]
        sizes.add((w or 256, h or 256))
    return sizes


def test_final_identity_134():
    assert __version__ == "1.3.36"
    assert BUILD_LABEL == "Final"
    assert (ROOT / "VERSION").read_text(encoding="utf-8").strip() == "1.3.36"
    assert "dev" not in __version__.lower()


def test_stable_131_final_not_modified():
    from bmt_voice_studio.release_scan import sha256_file

    zips = [
        ROOT / "release" / "BMTVoiceStudio-1.3.1-Windows-x64-Portable.zip",
        ROOT / "release" / "_protected_1.3.1_pre_icon" / "BMTVoiceStudio-1.3.1-Windows-x64-Portable.zip",
    ]
    for path in zips:
        if not path.is_file():
            pytest.skip(f"historical release artifact missing: {path.name}")
        assert sha256_file(path) == STABLE_131


def test_app_user_model_id_unversioned():
    assert WINDOWS_APP_USER_MODEL_ID == "BelieversBusinessmenNetwork.BMTVoiceStudio.App"
    assert "1.3" not in WINDOWS_APP_USER_MODEL_ID
    assert "dev" not in WINDOWS_APP_USER_MODEL_ID.lower()


def test_ico_has_windows_taskbar_sizes():
    assert ICO.is_file()
    assert _ico_sizes(ICO) == REQUIRED


def test_final_spec_embeds_ico():
    spec = (ROOT / "BMTVoiceStudio-1.3.36.spec").read_text(encoding="utf-8")
    assert 'icon="bmt_voice_studio/resources/bmt_voice_studio.ico"' in spec
    assert "BMTVoiceStudio-1.3.36" in spec
    assert "1.3.36-dev" not in spec


def test_branding_pads_are_exactly_ten():
    project = VideoProject(intro_enabled=True, outro_enabled=True)
    assert branding_pads(project) == (10.0, 10.0)
    off = VideoProject(intro_enabled=False, outro_enabled=False)
    assert branding_pads(off) == (0.0, 0.0)


def test_final_duration_is_master_plus_twenty():
    intro, outro = branding_pads(VideoProject())
    master = 20.0
    assert intro + master + outro == pytest.approx(40.0)


def test_overlay_windows_shift_after_intro():
    windows = overlay_windows(10.0, 20.0, 10.0, has_verse=True)
    assert windows["intro"] == (0.0, 10.0)
    assert windows["outro"][0] == pytest.approx(30.0)
    assert windows["outro"][1] == pytest.approx(40.0)
    assert windows["verse_card"][0] >= 10.0
    assert windows["lower_third"][0] >= windows["verse_card"][1] - 0.01
    assert windows["lower_third"][1] <= windows["outro"][0]
    assert not window_is_active(windows["verse_card"]) or windows["verse_card"][0] >= 10.0


def test_caption_and_verse_shift_plus_ten():
    cues = [CaptionCue(start=0.0, end=2.0, text="first", language="en")]
    shifted = shift_caption_cues(cues, 10.0)
    assert shifted[0].start == pytest.approx(10.0)
    assert shifted[0].end == pytest.approx(12.0)
    windows = overlay_windows(10.0, 50.0, 10.0, has_verse=True)
    assert windows["verse_card"][0] >= 10.0
    assert windows["lower_third"][0] >= 10.0


def test_music_missing_fallback_and_persistence(tmp_path: Path):
    project = VideoProject(
        intro_enabled=True,
        outro_enabled=True,
        intro_duration=10.0,
        outro_duration=10.0,
        music_path=str(tmp_path / "missing.mp3"),
        audio_path=str(tmp_path / "a.mp3"),
        audio_duration=20.0,
    )
    dest = tmp_path / "proj.json"
    save_project(project, dest)
    loaded = load_project(dest)
    assert loaded.intro_duration == 10.0
    assert loaded.outro_duration == 10.0
    assert loaded.music_path.endswith("missing.mp3")
    assert loaded.music_intro_start == 0.0
    assert loaded.music_outro_start == -1.0
    assert not Path(loaded.music_path).is_file()
    assert "Soft background" in music_display_name("") or "No music" in music_display_name("")
    assert "missing" not in music_display_name("").lower()


def test_composition_adds_twenty_seconds(tmp_path: Path):
    pytest.importorskip("PIL")
    from PIL import Image

    from bmt_voice_studio.video.composition import build_composition_plan

    audio = tmp_path / "master.wav"
    audio.write_bytes(b"RIFF")
    photo = tmp_path / "p.png"
    Image.new("RGB", (900, 1600), (10, 20, 30)).save(photo)
    project = VideoProject(
        devotional_date="2026-08-15",
        language="en",
        audio_path=str(audio),
        audio_duration=20.0,
        topic="Hope",
        media_items=[MediaItem(path=str(photo), media_type="image", order=0, width=900, height=1600)],
        intro_enabled=True,
        outro_enabled=True,
    )
    plan = build_composition_plan(project, output_path=tmp_path / "out.mp4", temp_dir=tmp_path / "tmp", job_id="t")
    assert plan.scenes[0].kind == "intro"
    assert plan.scenes[-1].kind == "outro"
    assert plan.intro_duration == 10.0
    assert plan.outro_duration == 10.0
    assert plan.total_duration == pytest.approx(40.0)
    assert plan.audio_duration == pytest.approx(20.0)


def test_batch_language_duration_uses_own_master():
    en = VideoProject(audio_duration=30.0, intro_enabled=True, outro_enabled=True)
    fr = VideoProject(audio_duration=45.0, intro_enabled=True, outro_enabled=True)
    assert branding_pads(en)[0] + en.audio_duration + branding_pads(en)[1] == pytest.approx(50.0)
    assert branding_pads(fr)[0] + fr.audio_duration + branding_pads(fr)[1] == pytest.approx(65.0)
