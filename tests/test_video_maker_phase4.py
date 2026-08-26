"""Video Maker Phase 4 — RC1: four-language, data root, captions header, Faster, packaging."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bmt_voice_studio import __version__
from bmt_voice_studio.build_info import BUILD_LABEL
from bmt_voice_studio.release_scan import (
    FORBIDDEN_NAMES,
    STABLE_12_SHA256,
    STABLE_12_ZIP_NAME,
    is_forbidden_path,
    scan_rc_tree,
    sha256_file,
)
from bmt_voice_studio.video.batch import (
    QUEUE_COMPLETE,
    QUEUE_FAILED,
    QueueItem,
    batch_completion_summary,
    projects_for_batch,
)
from bmt_voice_studio.video.captions import caption_cues_from_segments, is_intro_header_text
from bmt_voice_studio.video.discovery import extract_metadata
from bmt_voice_studio.video.encode import (
    RENDER_SPEED_FASTER,
    RENDER_SPEED_STANDARD,
    ffmpeg_crf_for,
    ffmpeg_x264_preset,
    normalize_render_speed,
)
from bmt_voice_studio.video.history import load_video_history, upsert_video_entry
from bmt_voice_studio.video.models import LanguageTrack, MediaItem, VideoProject
from bmt_voice_studio.video.project_store import load_project, save_project


def _tracks(*rows: tuple[str, bool, str]) -> list[LanguageTrack]:
    out: list[LanguageTrack] = []
    for lang, ready, topic in rows:
        out.append(
            LanguageTrack(
                language=lang,
                audio_path=f"C:/{lang}.mp3" if ready else "",
                audio_duration=90.0 if ready else 0.0,
                topic=topic,
                week_focus=f"{lang}-week",
                month_theme=f"{lang}-month",
                memory_verse=f"{lang}-verse",
                metadata_complete=bool(topic),
                ready=ready,
            )
        )
    return out


def test_sw_video_metadata_extraction():
    text = (
        "MANNA YA WAAMINIO LEO\n"
        "Mada: Vipaumbele vya Ufalme\n"
        "Msisitizo wa wiki: Utii\n"
        "Mada ya mwezi: Mavuno\n"
        "Mstari wa Kukariri: Mathayo 6:33\n"
        "Tafakari ya kwanza inaanza hapa.\n"
    )
    meta = extract_metadata(text)
    assert meta["topic"] == "Vipaumbele vya Ufalme"
    assert "Utii" in meta["week_focus"]
    assert "Mavuno" in meta["month_theme"]
    assert "Mathayo" in meta["memory_verse"]


def test_pt_video_metadata_extraction():
    text = (
        "MANÁ DIÁRIO DOS CRENTES\n"
        "Tema: Prioridades do Reino\n"
        "Foco da semana: Obediência\n"
        "Tema do mês: Colheita\n"
        "Versículo para Memorizar: Mateus 6:33\n"
        "A reflexão começa aqui.\n"
    )
    meta = extract_metadata(text)
    assert meta["topic"] == "Prioridades do Reino"
    assert "Obediência" in meta["week_focus"]
    assert "Colheita" in meta["month_theme"]
    assert "Mateus" in meta["memory_verse"]


def test_four_language_batch_shared_visuals(tmp_path: Path):
    photo = tmp_path / "shared.jpg"
    photo.write_bytes(b"x")
    tracks = _tracks(
        ("en", True, "Kingdom Priorities"),
        ("fr", True, "Les priorités du Royaume"),
        ("sw", True, "Vipaumbele vya Ufalme"),
        ("pt", True, "Prioridades do Reino"),
    )
    project = VideoProject(
        language="en",
        media_items=[MediaItem(path=str(photo), media_type="image", crop_x=0.12, crop_y=-0.08, zoom=1.15)],
        languages=tracks,
        selected_languages=["en", "fr", "sw", "pt"],
        template_id="bmt_nature",
        show_captions=True,
        skip_caption_header=True,
        render_speed="faster",
    )
    bound = projects_for_batch(project, ["en", "fr", "sw", "pt"])
    assert [p.language for p in bound] == ["en", "fr", "sw", "pt"]
    topics = [p.topic for p in bound]
    assert topics == [
        "Kingdom Priorities",
        "Les priorités du Royaume",
        "Vipaumbele vya Ufalme",
        "Prioridades do Reino",
    ]
    assert len(set(topics)) == 4
    for clone in bound:
        assert clone.media_items[0].path == str(photo)
        assert clone.media_items[0].crop_x == pytest.approx(0.12)
        assert clone.media_items[0].zoom == pytest.approx(1.15)
        assert clone.template_id == "bmt_nature"
        assert clone.skip_caption_header is True
        assert clone.render_speed == "faster"
        assert clone.audio_path.endswith(f"/{clone.language}.mp3")


def test_four_language_captions_isolated():
    en = caption_cues_from_segments(
        [{"text": "Seek first the kingdom of God.", "duration": 4.0}], language="en", audio_duration=4.0
    )
    fr = caption_cues_from_segments(
        [{"text": "Cherchez d'abord le Royaume de Dieu.", "duration": 4.0}], language="fr", audio_duration=4.0
    )
    sw = caption_cues_from_segments(
        [{"text": "Tafuteni kwanza Ufalme wa Mungu.", "duration": 4.0}], language="sw", audio_duration=4.0
    )
    pt = caption_cues_from_segments(
        [{"text": "Buscai primeiro o Reino de Deus.", "duration": 4.0}], language="pt", audio_duration=4.0
    )
    assert any("kingdom" in c.text.lower() for c in en)
    assert any("Royaume" in c.text or "é" in c.text for c in fr)
    assert any("Ufalme" in c.text for c in sw)
    assert any("Reino" in c.text for c in pt)
    blob_fr = " ".join(c.text for c in fr)
    blob_sw = " ".join(c.text for c in sw)
    blob_pt = " ".join(c.text for c in pt)
    assert "Seek first" not in blob_fr
    assert "Seek first" not in blob_sw
    assert "Seek first" not in blob_pt


def test_caption_header_skipping_portuguese():
    header = (
        "A MANÁ DOS CRENTES HOJE. Devocional Diário. Escrito por: Apóstolo David. "
        "TEMA: Perseverar na fé. Data: 22 August 2026."
    )
    body = "Mas aquele que perseverar até o fim será salvo."
    assert is_intro_header_text(header)
    assert not is_intro_header_text(body)
    segs = [
        {"text": header, "duration": 8.0},
        {"text": body, "duration": 6.0},
    ]
    skipped = caption_cues_from_segments(segs, skip_header=True, audio_duration=15.0, language="pt")
    skip_text = " ".join(c.text for c in skipped)
    assert "perseverar" in skip_text.lower()
    assert "BELIEVERS MANNA" not in skip_text.upper()
    assert "MANÁ DOS CRENTES" not in skip_text.upper()
    assert "Escrito por" not in skip_text


def test_caption_header_skipping_default():
    header = (
        "BELIEVERS MANNA TODAY. Written by Test Author. Date: 14 August 2026. "
        "Topic: Kingdom Priorities. Week Focus: Obedience. Month Theme: Harvest."
    )
    body = "Seek first the kingdom of God and his righteousness."
    assert is_intro_header_text(header)
    assert not is_intro_header_text(body)
    segs = [
        {"text": header, "duration": 8.0},
        {"text": body, "duration": 6.0},
    ]
    skipped = caption_cues_from_segments(segs, skip_header=True, audio_duration=15.0, language="en")
    full = caption_cues_from_segments(segs, skip_header=False, audio_duration=15.0, language="en")
    skip_text = " ".join(c.text for c in skipped)
    full_text = " ".join(c.text for c in full)
    assert "Seek first" in skip_text
    assert "BELIEVERS MANNA" not in skip_text.upper()
    assert "Topic:" not in skip_text
    assert skipped[0].start >= 7.5
    assert "BELIEVERS" in full_text.upper() or "Kingdom Priorities" in full_text
    project = VideoProject()
    assert project.skip_caption_header is True


def test_canonical_data_root_documents_onedrive(tmp_path: Path, monkeypatch):
    docs = tmp_path / "OneDrive" / "Documents"
    docs.mkdir(parents=True)
    monkeypatch.setenv("BMT_DOCUMENTS_DIR", str(docs))
    monkeypatch.delenv("BMT_DATA_ROOT", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "la"))
    (tmp_path / "la" / "BMTVoiceStudio").mkdir(parents=True)
    settings = tmp_path / "la" / "BMTVoiceStudio" / "settings.json"
    settings.write_text(json.dumps({"data_folder_mode": "default", "custom_data_folder": ""}), encoding="utf-8")

    from bmt_voice_studio.config.paths import (
        daily_exports_root,
        documents_location,
        user_data_root,
        video_exports_root,
    )

    assert documents_location() == docs
    root = user_data_root()
    assert root == docs / "BMT Voice Studio"
    assert daily_exports_root() == root / "Exports" / "Daily"
    assert video_exports_root() == root / "Exports" / "Video"
    for name in ("Exports", "Auditions", "Logs", "Reports", "Temp"):
        assert (root / name).is_dir()


def test_custom_data_root(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "la"))
    monkeypatch.delenv("BMT_DATA_ROOT", raising=False)
    custom = tmp_path / "CustomBMT"
    settings = tmp_path / "la" / "BMTVoiceStudio" / "settings.json"
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text(
        json.dumps({"data_folder_mode": "custom", "custom_data_folder": str(custom)}),
        encoding="utf-8",
    )
    from bmt_voice_studio.config.paths import daily_exports_root, user_data_root, video_exports_root

    root = user_data_root()
    assert root == custom
    assert daily_exports_root().parent.parent == custom
    assert video_exports_root().parent.parent == custom
    assert (custom / "Exports" / "Daily").is_dir()
    assert (custom / "Exports" / "Video").is_dir()


def test_faster_render_profile_keeps_resolution():
    assert normalize_render_speed("Faster") == RENDER_SPEED_FASTER
    assert normalize_render_speed(None) == RENDER_SPEED_STANDARD
    assert ffmpeg_x264_preset(RENDER_SPEED_STANDARD, width=1080) == "medium"
    assert ffmpeg_x264_preset(RENDER_SPEED_FASTER, width=1080) == "veryfast"
    assert ffmpeg_x264_preset(RENDER_SPEED_STANDARD, preview=True, width=1080) == "veryfast"
    assert ffmpeg_crf_for(20, RENDER_SPEED_STANDARD) == 20
    assert ffmpeg_crf_for(20, RENDER_SPEED_FASTER) == 22
    from bmt_voice_studio.video.geometry import CANVAS_HEIGHT, CANVAS_WIDTH

    assert CANVAS_WIDTH == 1080
    assert CANVAS_HEIGHT == 1920


def test_batch_completion_summary_four_and_partial():
    complete = [
        QueueItem(language="en", label="English", status=QUEUE_COMPLETE, output="en.mp4"),
        QueueItem(language="fr", label="French", status=QUEUE_COMPLETE, output="fr.mp4"),
        QueueItem(language="sw", label="Swahili", status=QUEUE_COMPLETE, output="sw.mp4"),
        QueueItem(language="pt", label="Portuguese", status=QUEUE_COMPLETE, output="pt.mp4"),
    ]
    summary = batch_completion_summary(complete)
    assert summary["headline"] == "4 VIDEOS COMPLETE"
    assert summary["complete"] == 4
    assert summary["failed"] == 0
    assert [r["language"] for r in summary["rows"]] == ["en", "fr", "sw", "pt"]
    mixed = list(complete)
    mixed[-1] = QueueItem(language="pt", label="Portuguese", status=QUEUE_FAILED, error="fail")
    partial = batch_completion_summary(mixed)
    assert "3 Complete" in partial["headline"]
    assert "1 Failed" in partial["headline"]
    assert partial["failed"] == 1


def test_four_language_history_skips_preview(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "la"))
    upsert_video_entry(
        {
            "date": "2026-08-14",
            "language": "en",
            "template": "BMT NATURE",
            "quality": "Standard 1080p",
            "duration": "01:20",
            "size": "12.0 MB",
            "status": QUEUE_COMPLETE,
            "output": str(tmp_path / "BMT_14_AUG_2026_ENGLISH_PREVIEW.mp4"),
            "preview": True,
        }
    )
    for lang, name in (("en", "ENGLISH"), ("fr", "FRENCH"), ("sw", "SWAHILI"), ("pt", "PORTUGUESE")):
        upsert_video_entry(
            {
                "date": "2026-08-14",
                "language": lang,
                "template": "BMT NATURE",
                "quality": "Standard 1080p",
                "duration": "01:20",
                "size": "18.0 MB",
                "status": QUEUE_COMPLETE,
                "output": str(tmp_path / f"BMT_14_AUG_2026_{name}_STANDARD.mp4"),
            }
        )
    rows = load_video_history()
    assert len(rows) == 4
    langs = [r["language"] for r in rows]
    assert set(langs) == {"en", "fr", "sw", "pt"}
    assert all("PREVIEW" not in str(r.get("output") or "").upper() for r in rows)


def test_project_recovery_keeps_phase4_fields(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "la"))
    missing = tmp_path / "gone.jpg"
    present = tmp_path / "keep.jpg"
    present.write_bytes(b"jpg")
    project = VideoProject(
        template_id="bmt_nature",
        selected_languages=["en", "fr", "sw", "pt"],
        show_captions=True,
        skip_caption_header=True,
        render_speed="faster",
        media_items=[
            MediaItem(path=str(present), media_type="image", order=0, crop_x=0.2, trim_start=0, trim_end=0),
            MediaItem(path=str(missing), media_type="image", order=1, crop_x=-0.1, trim_start=1.5, trim_end=8.0),
        ],
        languages=_tracks(("en", True, "A"), ("fr", True, "B"), ("sw", True, "C"), ("pt", True, "D")),
    )
    save_project(project)
    loaded = load_project()
    assert loaded.skip_caption_header is True
    assert loaded.render_speed == "faster"
    assert loaded.show_captions is True
    assert loaded.selected_languages == ["en", "fr", "sw", "pt"]
    assert loaded.template_id == "bmt_nature"
    assert loaded.media_items[0].crop_x == pytest.approx(0.2)
    assert loaded.media_items[1].trim_start == pytest.approx(1.5)
    assert loaded.media_items[1].missing is True
    assert loaded.media_items[0].missing is False


def test_rc_runtime_identity():
    root = Path(__file__).resolve().parents[1]
    assert __version__ == "1.3.38"
    assert (root / "VERSION").read_text(encoding="utf-8").strip() == "1.3.38"
    assert BUILD_LABEL == "Final"
    about = (root / "bmt_voice_studio" / "ui" / "dialogs" / "about.py").read_text(encoding="utf-8")
    assert "BUILD_LABEL" in about


def test_rc_packaging_layout_and_stable_12_untouched():
    root = Path(__file__).resolve().parents[1]
    assert (root / "BMTVoiceStudio-1.3.0.spec").is_file()
    assert (root / "BMTVoiceStudio-1.3.0-RC2.spec").is_file()
    zip12 = root / "release" / STABLE_12_ZIP_NAME
    if not zip12.is_file():
        pytest.skip("historical 1.2 release zip not present on this machine")
    assert sha256_file(zip12) == STABLE_12_SHA256
    assert not (root / "release" / "BMTVoiceStudio-1.3.0-RC2-Windows-x64-Portable.zip").exists()


def test_release_security_exclusions(tmp_path: Path):
    assert ".git" in FORBIDDEN_NAMES
    assert ".pytest_cache" in FORBIDDEN_NAMES
    assert ".env" in FORBIDDEN_NAMES
    assert "credentials.json" in FORBIDDEN_NAMES
    pkg = tmp_path / "BMTVoiceStudio-1.3.0"
    (pkg / "_internal").mkdir(parents=True)
    (pkg / "BMTVoiceStudio.exe").write_bytes(b"mz")
    (pkg / ".git").mkdir()
    (pkg / ".env").write_text("SECRET=1", encoding="utf-8")
    hits = scan_rc_tree(pkg)
    joined = "\n".join(hits)
    assert ".git" in joined
    assert ".env" in joined
    assert is_forbidden_path(Path("id_rsa"))
    rc_zip = Path(__file__).resolve().parents[1] / "release-candidate" / "BMTVoiceStudio-1.3.0-RC2-Windows-x64-Portable.zip"
    if rc_zip.is_file():
        import zipfile

        with zipfile.ZipFile(rc_zip) as zf:
            names = zf.namelist()
        lowered = "\n".join(names).lower()
        assert ".git/" not in lowered
        assert ".pytest_cache" not in lowered
        assert "qa_outputs" not in lowered
        assert "agent-transcripts" not in lowered
        assert ".cursor" not in lowered


def test_write_reports_keeps_unselected_language_blocks(tmp_path: Path):
    from bmt_voice_studio.daily.report import write_reports

    root = tmp_path / "BMT_2026_08_14"
    first = {
        "english": {
            "ok": True,
            "segments": [{"index": 1, "spoken_text": "Seek first the kingdom.", "probe": {"duration_sec": 4.0}}],
        },
        "french": {"selected": False, "status": "NOT_SELECTED", "segments": 0},
    }
    write_reports(root, first)
    second = {
        "english": {"selected": False, "status": "NOT_SELECTED", "ok": None, "segments": 0},
        "french": {
            "ok": True,
            "segments": [{"index": 1, "spoken_text": "Cherchez d'abord le Royaume.", "probe": {"duration_sec": 4.0}}],
        },
    }
    write_reports(root, second)
    data = json.loads((root / "REPORTS" / "production.json").read_text(encoding="utf-8"))
    assert data["english"]["segments"][0]["spoken_text"].startswith("Seek first")
    assert data["french"]["segments"][0]["spoken_text"].startswith("Cherchez")

