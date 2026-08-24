"""Media strip + video live preview stills."""

from __future__ import annotations

from pathlib import Path

from bmt_voice_studio.video.live_crop import _frame_source_item, render_live_crop_still
from bmt_voice_studio.video.models import MediaItem
from bmt_voice_studio.video.reorder import reorder_items


def test_reorder_items_moves_selected():
    items = [MediaItem(path=f"a{i}.png", order=i) for i in range(3)]
    moved = reorder_items(items, 0, 2)
    assert [Path(i.path).stem for i in moved] == ["a1", "a2", "a0"]
    assert [i.order for i in moved] == [0, 1, 2]


def test_live_crop_renders_video_via_thumbnail(tmp_path, monkeypatch):
    from PIL import Image

    thumb = tmp_path / "thumb.jpg"
    Image.new("RGB", (160, 160), (10, 80, 160)).save(thumb, "JPEG")
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"not-a-real-mp4")

    monkeypatch.setattr(
        "bmt_voice_studio.video.thumbs.extract_thumbnail",
        lambda *_a, **_k: thumb,
    )
    item = MediaItem(path=str(video), media_type="video", width=640, height=360, duration=3.0)
    src = _frame_source_item(item)
    assert src is not None
    assert src.media_type == "image"
    assert Path(src.path) == thumb

    out = render_live_crop_still(item, tmp_path / "live.png")
    assert out is not None
    assert out.is_file()
    assert out.stat().st_size > 32


def test_media_strip_keeps_add_and_shows_all(tmp_path):
    from PySide6.QtWidgets import QApplication

    from bmt_voice_studio.ui.widgets.video_media_widget import VideoMediaStrip
    from PIL import Image

    app = QApplication.instance() or QApplication([])
    p1 = tmp_path / "one.png"
    p2 = tmp_path / "two.png"
    Image.new("RGB", (80, 120), (20, 20, 20)).save(p1)
    Image.new("RGB", (80, 120), (80, 20, 20)).save(p2)

    strip = VideoMediaStrip()
    assert strip.btn_add.text() == "Add media"
    strip.add_items([MediaItem(path=str(p1), media_type="image", width=80, height=120)])
    assert len(strip.items()) == 1
    assert strip.btn_add.isEnabled()
    assert not strip.list.isHidden()
    strip.add_items([MediaItem(path=str(p2), media_type="image", width=80, height=120)])
    assert len(strip.items()) == 2
    assert strip.list.count() == 2
    strip.select_index(1)
    strip._move_left()
    assert Path(strip.items()[0].path).name == "two.png"
    strip.close()
    assert app is not None
