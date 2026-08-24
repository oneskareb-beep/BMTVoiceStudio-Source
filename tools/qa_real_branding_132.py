"""Real Daily BMT mix + synthetic 40s video duration QA."""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PIL import Image

from bmt_voice_studio.audio.ffmpeg_service import FFmpegService
from bmt_voice_studio.video.branding_audio import mix_branding_audio
from bmt_voice_studio.video.composition import build_composition_plan
from bmt_voice_studio.video.ffmpeg_renderer import VideoRenderer
from bmt_voice_studio.video.models import MediaItem, VideoProject


def _probe(path: Path) -> tuple[float, int]:
    r = FFmpegService().run(["-i", str(path)], check=False)
    text = (r.stderr or "") + (r.stdout or "")
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", text)
    dur = 0.0
    if m:
        dur = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    return dur, text.count("Audio:")


def main() -> int:
    out = ROOT / "qa_outputs" / "branding_132"
    out.mkdir(parents=True, exist_ok=True)
    music_src = Path(r"C:\Users\aganz\Downloads\Calima - Full Moon (freetouse.com) (1).mp3")
    data_music = Path.home() / "Documents" / "BMT Voice Studio" / "Music"
    data_music.mkdir(parents=True, exist_ok=True)
    music = data_music / "Calima-Full-Moon.mp3"
    if music_src.is_file():
        shutil.copy2(music_src, music)
        shutil.copy2(music_src, out / "Calima-Full-Moon.mp3")

    music_dur, _ = _probe(music)
    outro_start = max(0.0, music_dur - 10.0 - 0.15) if music_dur >= 21.0 else 0.0

    master = Path(
        r"C:\Users\aganz\Documents\BMT Voice Studio\Exports\Daily\2026\08\BMT_2026_08_14\ENGLISH\BMT_14_AUG_2026_ENGLISH_FINAL.mp3"
    )
    master_dur, _ = _probe(master)
    mixed = out / "real_bmt_2026_08_14_en_mixed.m4a"
    mix_branding_audio(
        master,
        mixed,
        music_path=music,
        intro_sec=10.0,
        outro_sec=10.0,
        master_duration=master_dur,
    )
    mixed_dur, streams = _probe(mixed)

    tone = out / "synthetic_20s.m4a"
    FFmpegService().run(
        ["-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=20", "-c:a", "aac", "-b:a", "128k", str(tone)],
        check=True,
    )
    photo = out / "still.png"
    Image.new("RGB", (1080, 1920), (12, 22, 40)).save(photo)
    project = VideoProject(
        devotional_date="2026-08-15",
        language="en",
        topic="Hope",
        week_focus="Faith",
        month_theme="Grace",
        audio_path=str(tone),
        audio_duration=20.0,
        media_items=[MediaItem(path=str(photo), media_type="image", order=0, width=1080, height=1920)],
        intro_enabled=True,
        outro_enabled=True,
        intro_duration=10.0,
        outro_duration=10.0,
        music_path=str(music),
        show_captions=True,
    )
    video_path = out / "synthetic_40s.mp4"
    plan = build_composition_plan(project, output_path=video_path, temp_dir=out / "render_tmp", job_id="qa132")
    rendered = VideoRenderer().render(project, plan, keep_temp_on_success=True)
    video_dur, video_streams = _probe(rendered)

    report = {
        "music_user_selected_path": str(music),
        "music_not_bundled_in_exe": True,
        "music_duration": music_dur,
        "intro_excerpt": "0.000-10.000",
        "outro_excerpt": f"{outro_start:.3f}-{outro_start + 10.0:.3f}",
        "real_master": str(master),
        "real_master_duration": master_dur,
        "real_mixed_duration": mixed_dur,
        "real_difference": mixed_dur - master_dur,
        "real_audio_streams": streams,
        "synthetic_video": str(rendered),
        "synthetic_video_duration": video_dur,
        "synthetic_expected": 40.0,
        "synthetic_audio_streams": video_streams,
        "caption_shift": "+10.000 (shift_caption_cues in renderer)",
    }
    (out / "qa_real_branding_132.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    ok = (
        abs(mixed_dur - (master_dur + 20.0)) < 1.0
        and abs(video_dur - 40.0) < 0.8
        and streams == 1
        and video_streams == 1
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
