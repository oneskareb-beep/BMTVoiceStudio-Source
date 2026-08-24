"""Message date, locked 9:16 card, transparent overlay, in-app updater."""

from __future__ import annotations

from datetime import date
from pathlib import Path
import zipfile

import pytest

from bmt_voice_studio.daily.message_date import detect_message_date, parse_date_token
from bmt_voice_studio.update import (
    extract_portable_zip,
    is_newer,
    normalize_feed,
    parse_version,
    write_updater_script,
)
from bmt_voice_studio.video.composition import build_composition_plan
from bmt_voice_studio.video.ffmpeg_renderer import build_image_scene_command
from bmt_voice_studio.video.geometry import CANVAS_HEIGHT, CANVAS_WIDTH
from bmt_voice_studio.video.models import MediaItem, VideoProject


def test_message_date_beats_today_and_whatsapp_stamp():
    today = date(2026, 8, 19)
    text = (
        "[19/08/2026, 13:32:38] Pastor: BELIEVERS MANNA TODAY\n"
        "Tuesday, 13 August 2026\n"
        "- DAILY DEVOTIONAL -\n"
        "Written by: Apostle (Dr.) David A. Aderibigbe\n"
        "TOPIC: Discipleship Lifestyle\n"
    )
    found = detect_message_date(text, today=today)
    assert found == date(2026, 8, 13)
    assert found != today
    assert parse_date_token("August 13, 2026") == date(2026, 8, 13)
    assert parse_date_token("13/08/2026") == date(2026, 8, 13)
    assert parse_date_token("2026-08-14") == date(2026, 8, 14)
    assert parse_date_token("13.08.2026") == date(2026, 8, 13)
    assert detect_message_date("No calendar line here", today=today) is None


def test_labeled_date_wins():
    text = "Opening remarks\nDate: 11 August 2026\nTOPIC: Faith\n"
    assert detect_message_date(text, today=date(2026, 8, 19)) == date(2026, 8, 11)


def test_locked_intro_is_9x16_not_photo(tmp_path: Path):
    pytest.importorskip("PIL")
    from PIL import Image

    from bmt_voice_studio.video.title_cards import render_intro_card

    photo = tmp_path / "user.jpg"
    Image.new("RGB", (800, 600), (200, 10, 10)).save(photo)
    project = VideoProject(
        topic="Discipleship Lifestyle",
        devotional_date="2026-08-19",
        media_items=[MediaItem(path=str(photo), media_type="image")],
    )
    dest = tmp_path / "intro.png"
    render_intro_card(project, dest)
    im = Image.open(dest)
    assert im.size == (CANVAS_WIDTH, CANVAS_HEIGHT)
    # Locked cream card — not a stretched user photo.
    px = im.convert("RGB").getpixel((24, 24))
    assert px[1] > 160 and px[2] > 160


def test_transparent_item_becomes_overlay(tmp_path: Path):
    pytest.importorskip("PIL")
    from PIL import Image

    from bmt_voice_studio.video.media_probe import probe_media

    bed = tmp_path / "bed.jpg"
    Image.new("RGB", (1080, 1920), (20, 40, 80)).save(bed)
    logo = tmp_path / "cutout.png"
    im = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
    for x in range(40, 160):
        for y in range(40, 160):
            im.putpixel((x, y), (212, 160, 23, 255))
    im.save(logo)
    overlay = probe_media(logo)
    assert overlay.has_alpha is True
    assert overlay.overlay is True
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"RIFF")
    project = VideoProject(
        audio_path=str(audio),
        audio_duration=40.0,
        media_items=[
            MediaItem(path=str(bed), media_type="image"),
            overlay,
        ],
    )
    plan = build_composition_plan(project, output_path=tmp_path / "o.mp4", temp_dir=tmp_path / "t", job_id="ov")
    photos = [s for s in plan.scenes if s.kind == "photo"]
    assert photos
    assert any(Path(s.overlay_path).name == logo.name for s in photos)


def test_overlay_only_keeps_cutout_over_template_bed(tmp_path: Path):
    pytest.importorskip("PIL")
    from PIL import Image

    from bmt_voice_studio.video.media_probe import probe_media

    logo = tmp_path / "cutout.png"
    im = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
    for x in range(40, 160):
        for y in range(40, 160):
            im.putpixel((x, y), (212, 160, 23, 255))
    im.save(logo)
    overlay = probe_media(logo)
    overlay.zoom = 0.7
    overlay.crop_x = 0.25
    overlay.crop_y = -0.1
    overlay.fit_mode = "fit"
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"RIFF")
    project = VideoProject(
        audio_path=str(audio),
        audio_duration=40.0,
        media_items=[overlay],
    )
    plan = build_composition_plan(project, output_path=tmp_path / "o.mp4", temp_dir=tmp_path / "t", job_id="ov2")
    photos = [s for s in plan.scenes if s.kind == "photo"]
    assert photos
    assert Path(photos[0].overlay_path).name == logo.name
    assert "template_bed" in Path(photos[0].media_path).name
    assert photos[0].overlay_zoom == pytest.approx(0.7)
    assert photos[0].overlay_crop_x == pytest.approx(0.25)
    assert photos[0].overlay_crop_y == pytest.approx(-0.1)
    assert photos[0].overlay_fit_mode == "fit"


def test_overlay_ffmpeg_command_includes_second_input(tmp_path: Path):
    ov = tmp_path / "ov.png"
    ov.write_bytes(b"x")
    cmd = build_image_scene_command(
        "ffmpeg",
        "bed.jpg",
        "out.mp4",
        duration=8,
        fps=30,
        width=1080,
        height=1920,
        animation="zoom_in",
        fit_mode="fill",
        overlay_path=str(ov),
        overlay_zoom=0.6,
        overlay_crop_x=0.2,
        overlay_crop_y=-0.1,
        overlay_fit_mode="fit",
    )
    joined = " ".join(cmd)
    assert "-filter_complex" in cmd
    assert str(ov) in cmd
    assert "overlay=0:0" in joined
    assert "format=rgba" in joined
    assert "black@0" in joined
    assert "eval=frame" not in joined


def test_updater_version_compare_and_zip_extract(tmp_path: Path):
    assert is_newer("1.3.4", "1.3.3")
    assert not is_newer("1.3.3", "1.3.3")
    assert not is_newer("1.3.2", "1.3.3")
    assert parse_version("1.3.3") == (1, 3, 3)
    nested = tmp_path / "pkg" / "BMTVoiceStudio"
    nested.mkdir(parents=True)
    (nested / "BMTVoiceStudio.exe").write_bytes(b"mz")
    zpath = tmp_path / "BMTVoiceStudio-1.3.4-Windows-x64-Portable.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.write(nested / "BMTVoiceStudio.exe", "BMTVoiceStudio/BMTVoiceStudio.exe")
    extracted = extract_portable_zip(zpath, tmp_path / "out")
    assert (extracted / "BMTVoiceStudio.exe").is_file()


def test_github_release_feed_normalizes_portable_zip():
    feed = normalize_feed(
        {
            "tag_name": "v1.3.4",
            "assets": [
                {
                    "name": "notes.txt",
                    "browser_download_url": "https://example.com/notes.txt",
                },
                {
                    "name": "BMTVoiceStudio-1.3.4-Windows-x64-Portable.zip",
                    "browser_download_url": "https://github.com/example/BMTVoiceStudio/releases/download/v1.3.4/BMTVoiceStudio-1.3.4-Windows-x64-Portable.zip",
                },
            ],
        }
    )
    assert feed["version"] == "1.3.4"
    assert feed["zip_url"].endswith("BMTVoiceStudio-1.3.4-Windows-x64-Portable.zip")
    assert feed["asset_api_url"] == ""


def test_github_feed_keeps_asset_api_url():
    feed = normalize_feed(
        {
            "tag_name": "v1.3.15",
            "assets": [
                {
                    "name": "BMTVoiceStudio-1.3.15-Windows-x64-Portable.zip",
                    "url": "https://api.github.com/repos/example/BMTVoiceStudio/releases/assets/1",
                    "browser_download_url": "https://github.com/example/BMTVoiceStudio/releases/download/v1.3.15/BMTVoiceStudio-1.3.15-Windows-x64-Portable.zip",
                }
            ],
        }
    )
    assert feed["asset_api_url"].endswith("/releases/assets/1")


def test_download_update_zip_retries_dns_then_succeeds(tmp_path, monkeypatch):
    from io import BytesIO
    from urllib.error import URLError

    import bmt_voice_studio.update as upd

    nested = tmp_path / "pkg"
    nested.mkdir()
    (nested / "BMTVoiceStudio.exe").write_bytes(b"mz")
    zpath = tmp_path / "src.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.write(nested / "BMTVoiceStudio.exe", "BMTVoiceStudio/BMTVoiceStudio.exe")
    payload = zpath.read_bytes()
    hits = {"n": 0}

    class _Resp:
        def __enter__(self):
            return BytesIO(payload)

        def __exit__(self, *_exc):
            return False

    def fake_urlopen(req, timeout=None):
        hits["n"] += 1
        if hits["n"] < 3:
            raise URLError("[Errno 11001] getaddrinfo failed")
        return _Resp()

    monkeypatch.setattr(upd, "urlopen", fake_urlopen)
    monkeypatch.setattr(upd.time, "sleep", lambda _s: None)
    dest = tmp_path / "out.zip"
    got = upd.download_update_zip("https://example.com/app.zip", dest)
    assert got.is_file()
    assert zipfile.is_zipfile(got)
    assert hits["n"] == 3


def test_download_reports_progress(tmp_path, monkeypatch):
    from io import BytesIO

    import bmt_voice_studio.update as upd

    nested = tmp_path / "pkg"
    nested.mkdir()
    (nested / "BMTVoiceStudio.exe").write_bytes(b"mz")
    zpath = tmp_path / "src.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.write(nested / "BMTVoiceStudio.exe", "BMTVoiceStudio/BMTVoiceStudio.exe")
    payload = zpath.read_bytes()
    hits: list[tuple[int, int]] = []

    class _Resp:
        headers = {"Content-Length": str(len(payload))}

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def read(self, n: int = -1):
            if not hasattr(self, "_buf"):
                self._buf = BytesIO(payload)
            return self._buf.read(n)

    monkeypatch.setattr(upd, "urlopen", lambda *a, **k: _Resp())
    dest = tmp_path / "out.zip"
    got = upd.download_update_zip(
        "https://example.com/app.zip",
        dest,
        on_progress=lambda got_n, total: hits.append((got_n, total)),
    )
    assert got.is_file()
    assert hits
    assert hits[-1][0] >= len(payload)
    assert hits[0][1] == len(payload)


def test_download_prefers_asset_api_url_first(tmp_path, monkeypatch):
    from io import BytesIO

    import bmt_voice_studio.update as upd

    nested = tmp_path / "pkg"
    nested.mkdir()
    (nested / "BMTVoiceStudio.exe").write_bytes(b"mz")
    zpath = tmp_path / "src.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.write(nested / "BMTVoiceStudio.exe", "BMTVoiceStudio/BMTVoiceStudio.exe")
    payload = zpath.read_bytes()
    seen: list[str] = []

    class _Resp:
        headers = {"Content-Length": str(len(payload))}

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def read(self, n: int = -1):
            if not hasattr(self, "_buf"):
                self._buf = BytesIO(payload)
            return self._buf.read(n)

    def fake_urlopen(req, timeout=None):
        seen.append(req.full_url)
        return _Resp()

    monkeypatch.setattr(upd, "urlopen", fake_urlopen)
    dest = tmp_path / "out.zip"
    got = upd.download_update_zip(
        "https://github.com/example/BMTVoiceStudio/releases/download/v1.3.30/app.zip",
        dest,
        asset_api_url="https://api.github.com/repos/example/BMTVoiceStudio/releases/assets/99",
    )
    assert got.is_file()
    assert seen[0].startswith("https://api.github.com/")


def test_updater_script_avoids_timeout_quickedit_hang(tmp_path: Path):
    script = write_updater_script(tmp_path, tmp_path / "src", tmp_path / "BMTVoiceStudio.exe")
    text = script.read_text(encoding="utf-8")
    assert "timeout" not in text.lower()
    assert "ping -n" in text
    assert "start" in text and "/min" in text
