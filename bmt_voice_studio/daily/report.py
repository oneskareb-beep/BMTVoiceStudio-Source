"""Daily production report writers."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from bmt_voice_studio import __version__


def write_reports(root: Path, payload: dict[str, Any]) -> tuple[Path, Path]:
    reports = root / "REPORTS"
    reports.mkdir(parents=True, exist_ok=True)
    json_path = reports / "production.json"
    md_path = reports / "PRODUCTION_REPORT.md"
    data = dict(payload)
    data.setdefault("application_version", __version__)
    data.setdefault("generated_at", datetime.now().isoformat(timespec="seconds"))
    import json

    if json_path.is_file():
        try:
            previous = json.loads(json_path.read_text(encoding="utf-8"))
        except Exception:
            previous = {}
        if isinstance(previous, dict):
            data = _merge_previous_language_blocks(data, previous)
    json_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    md_path.write_text(_markdown(data), encoding="utf-8")
    return md_path, json_path


def _block_has_caption_segments(block: Any) -> bool:
    if not isinstance(block, dict):
        return False
    segs = block.get("segments")
    return isinstance(segs, list) and any(isinstance(s, dict) and (s.get("spoken_text") or s.get("source_text") or s.get("text")) for s in segs)


def _merge_previous_language_blocks(data: dict[str, Any], previous: dict[str, Any]) -> dict[str, Any]:
    """Keep previously generated language caption/audio blocks when this run skipped them."""
    merged = dict(data)
    for key in ("english", "french", "swahili", "portuguese"):
        new_block = merged.get(key)
        old_block = previous.get(key)
        if _block_has_caption_segments(old_block) and not _block_has_caption_segments(new_block):
            merged[key] = old_block
    return merged


def _lang_block(title: str, block: dict[str, Any] | None) -> str:
    if not block:
        return f"## {title}\n\nNot generated.\n"
    if block.get("status") == "NOT_SELECTED" or block.get("selected") is False:
        return (
            f"## {title} -- NOT_SELECTED\n\n"
            f"- selected: false\n"
            f"- status: NOT_SELECTED\n"
            f"- Piper invocations: 0\n\n"
        )
    status = block.get("status") or ("PASS" if block.get("ok") else "FAIL")
    loud = block.get("loudness") or {}
    probe = block.get("mp3_probe") or {}
    lines = [
        f"## {title} -- {status}",
        "",
        f"- selected: {block.get('selected', True)}",
        f"- status: {status}",
        f"- target_locale: {block.get('target_locale', '')}",
        f"- Provider: {block.get('provider', '')}",
        f"- Configured provider: {block.get('configured_provider', block.get('provider', ''))}",
        f"- Actual provider: {block.get('actual_provider', block.get('provider', ''))}",
        f"- Piper invocations: {block.get('piper_invocations', 0)}",
        f"- Male voice: {block.get('male_voice', '')}",
        f"- Female voice: {block.get('female_voice', '')}",
        f"- Configured voice (male/female): {block.get('configured_male_voice', '')} / {block.get('configured_female_voice', '')}",
        f"- Configured voice: {block.get('configured_voice', '')}",
        f"- Actual voice: {block.get('actual_voice', '')}",
        f"- Rate: {block.get('rate', '')}",
        f"- Pitch: {block.get('pitch', '')}",
        f"- Volume: {block.get('volume', '')}",
        f"- Pause: {block.get('pause_ms', '')} ms",
        f"- Low-pass: {block.get('lowpass_hz') or 'NONE'}",
        f"- Mastering: {block.get('mastering', '')}",
        f"- Processing: {block.get('processing_mode', '')}",
        f"- Strict source: {block.get('strict_source_mode', '')}",
        f"- Spoken list marker suppression: {block.get('spoken_list_marker_suppression', '')}",
        f"- Spoken list markers removed: {block.get('spoken_list_markers_removed', '')}",
        f"- Segments: {block.get('segment_count', '')}",
        f"- Duration: {probe.get('duration_sec', '')} s",
        f"- Output files: MP3=`{block.get('final_mp3', '')}` WAV=`{block.get('final_wav', '')}`",
        f"- Retries: {block.get('retry_count', 0)}",
        f"- Fallback events: {block.get('fallback_events', 0)}",
        f"- MP3: `{block.get('final_mp3', '')}`",
        f"- WAV: `{block.get('final_wav', '')}`",
        f"- Codec: {probe.get('codec', '')} / {probe.get('sample_rate', '')} Hz / {probe.get('channels', '')}",
        f"- Bitrate: {probe.get('bitrate_kbps', '')} kbps",
        f"- Loudness: {loud.get('input_i', '')} LUFS",
        f"- True peak: {loud.get('input_tp', '')} dBTP",
        f"- Errors: {block.get('errors') or []}",
        "",
    ]
    audit = block.get("voice_audit") or []
    if audit:
        lines.append("")
        lines.append("### Voice audit")
        for row in audit:
            idx = row.get("index", "")
            role = row.get("role", "")
            cfg = row.get("configured_voice", "")
            act = row.get("actual_voice", "")
            ap = row.get("actual_provider", "")
            lines.append(f"- {int(idx):02d} {role} — {ap} · configured: {cfg} · actual: {act}")
    lines.extend(["", ""])
    return "\n".join(lines)


def _markdown(data: dict[str, Any]) -> str:
    overall = data.get("status", "")
    selected = data.get("selected_languages") or []
    return "\n".join(
        [
            "# Daily BMT Production Report",
            "",
            f"- Date: {data.get('date', '')}",
            f"- Generated: {data.get('generated_at', '')}",
            f"- Application: BMT Voice Studio {data.get('application_version', '')}",
            f"- Selected languages: {selected}",
            f"- Pause: {data.get('pause_ms', '')} ms",
            f"- MP3 bitrate: {data.get('mp3_bitrate', '')} kbps",
            f"- Target LUFS: {data.get('target_lufs', '')}",
            f"- Folder: `{data.get('folder', '')}`",
            f"- Overall: **{overall}**",
            "",
            _lang_block("English", data.get("english")),
            _lang_block("French", data.get("french")),
            _lang_block("Swahili", data.get("swahili")),
            _lang_block("Portuguese", data.get("portuguese")),
        ]
    )
