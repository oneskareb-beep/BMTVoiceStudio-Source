"""Tests for M3U parsing and audio validation."""

from bmt_voice_studio.m3u.parser import (
    detect_hls,
    parse_m3u_content,
    parse_url_list,
    validate_audio_magic,
)


def test_simple_m3u():
    content = """#EXTM3U
#EXTINF:10,Track One
https://cdn.example.com/a.mp3
#EXTINF:12,Track Two
https://cdn.example.com/b.wav
"""
    result = parse_m3u_content(content)
    assert not result.is_hls
    assert len(result.items) == 2
    assert result.items[0].title == "Track One"
    assert result.items[1].source.endswith("b.wav")


def test_url_list():
    result = parse_url_list("https://a.com/1.mp3\n\n# comment\nhttps://a.com/2.mp3\n")
    assert len(result.items) == 2
    assert result.items[0].index == 1


def test_hls_media_detection():
    content = """#EXTM3U
#EXT-X-TARGETDURATION:10
#EXT-X-MEDIA-SEQUENCE:0
#EXTINF:9.0,
seg0.ts
#EXTINF:9.0,
seg1.ts
"""
    is_hls, is_master = detect_hls(content)
    assert is_hls
    assert not is_master
    result = parse_m3u_content(content)
    assert result.is_hls


def test_hls_master_detection():
    content = """#EXTM3U
#EXT-X-STREAM-INF:BANDWIDTH=128000
audio.m3u8
"""
    is_hls, is_master = detect_hls(content)
    assert is_hls and is_master


def test_reject_html_as_audio():
    ok, reason = validate_audio_magic(b"<!DOCTYPE html><html>error</html>")
    assert not ok
    assert "HTML" in reason


def test_accept_mp3_magic():
    ok, kind = validate_audio_magic(b"ID3" + b"\x00" * 64)
    assert ok
    assert kind == "mp3"


def test_accept_wav_magic():
    data = b"RIFF" + b"\x00\x00\x00\x00" + b"WAVE" + b"\x00" * 32
    ok, kind = validate_audio_magic(data)
    assert ok
    assert kind == "wav"
