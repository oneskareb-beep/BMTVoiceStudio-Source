"""Generate cloud fallback package from canonical pipeline configuration."""

from __future__ import annotations

import json
import shutil
import textwrap
from pathlib import Path

from bmt_voice_studio.config.pipeline_config import config_path, get_canonical_preset


def _notebook_cells(preset_id: str) -> dict:
    entry = get_canonical_preset(preset_id)
    pipe = entry["pipeline"]
    name = entry["name"]
    return {
        "preset_id": preset_id,
        "name": name,
        "male_voice": entry["male_voice"],
        "female_voice": entry["female_voice"],
        "rate": entry["rate"],
        "pitch": entry["pitch"],
        "volume": entry["volume"],
        "pause_ms": pipe["pause_ms"],
        "lowpass_hz": pipe.get("lowpass_hz"),
        "mp3_bitrate_kbps": pipe.get("mp3_bitrate_kbps"),
        "export_wav": pipe.get("export_wav", False),
    }


def _build_script(cfg: dict) -> str:
    lowpass_block = ""
    if cfg["lowpass_hz"]:
        lowpass_block = textwrap.dedent(
            f"""
            from pydub.effects import low_pass_filter
            final_audio = low_pass_filter(final_audio, cutoff={cfg["lowpass_hz"]})
            """
        )
    wav_block = ""
    if cfg["export_wav"]:
        wav_block = textwrap.dedent(
            """
            final_audio.export(
                "final_output.wav",
                format="wav",
                parameters=["-ac", "1", "-ar", "44100"],
            )
            """
        )
    mp3_args = ""
    if cfg["mp3_bitrate_kbps"]:
        mp3_args = f', bitrate="{cfg["mp3_bitrate_kbps"]}k"'

    return textwrap.dedent(
        f'''\
        # Auto-generated from BMT Voice Studio canonical configuration
        # Preset: {cfg["name"]}

        !pip install -q edge-tts pydub

        import asyncio
        import re
        from pydub import AudioSegment
        import edge_tts

        text = r"""
        PASTE SOURCE TEXT HERE
        """

        female_voice = "{cfg["female_voice"]}"
        male_voice = "{cfg["male_voice"]}"

        pattern = r"\\{{(.*?)\\}}"
        parts = re.split(pattern, text, flags=re.DOTALL)
        segments = []
        for i, part in enumerate(parts):
            part = part.strip()
            if not part:
                continue
            role = "female" if i % 2 else "male"
            segments.append((role, part))

        async def speak(text, voice, filename):
            communicate = edge_tts.Communicate(
                text=text,
                voice=voice,
                rate="{cfg["rate"]}",
                pitch="{cfg["pitch"]}",
                volume="{cfg["volume"]}",
            )
            await communicate.save(filename)

        async def build_audio():
            files_list = []
            for i, (role, sentence) in enumerate(segments):
                filename = f"part_{{i}}.mp3"
                voice = female_voice if role == "female" else male_voice
                print(f"Generating {{filename}} ({{role}}) — {{voice}}")
                await speak(sentence, voice, filename)
                files_list.append(filename)

            final_audio = AudioSegment.empty()
            pause = AudioSegment.silent(duration={cfg["pause_ms"]})
            for f in files_list:
                final_audio += AudioSegment.from_mp3(f)
                final_audio += pause
        {lowpass_block}
        {wav_block}
            final_audio.export("final_output.mp3", format="mp3"{mp3_args})
            for f in files_list:
                import os
                os.remove(f)
            print("SUCCESS — final_output files created")

        await build_audio()
        '''
    )


def export_cloud_fallback_package(dest_dir: Path) -> Path:
    """Write cloud fallback package; returns destination folder."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(config_path(), dest_dir / "source_pipeline_presets.json")

    requirements = "edge-tts>=6.1.9\npydub>=0.25.1\n"
    (dest_dir / "requirements.txt").write_text(requirements, encoding="utf-8")

    readme = textwrap.dedent(
        """\
        # BMT Cloud Fallback Package

        This package mirrors the same canonical pipeline configuration used by
        BMT Voice Studio local production. Use only when local Edge TTS access
        fails and you need an alternate network environment.

        ## Contents
        - `source_pipeline_presets.json` — canonical preset values
        - `BMT_ENGLISH_pipeline.py` / `BMT_FRENCH_pipeline.py` — runnable scripts
        - `requirements.txt` — Python dependencies

        Normal daily production does not require this package.
        """
    )
    (dest_dir / "README.md").write_text(readme, encoding="utf-8")

    manifest = {"presets": {}}
    for preset_id in ("bmt_english", "bmt_french"):
        cfg = _notebook_cells(preset_id)
        script_name = f"{cfg['name'].replace(' ', '_')}_pipeline.py"
        (dest_dir / script_name).write_text(_build_script(cfg), encoding="utf-8")
        manifest["presets"][preset_id] = cfg

    (dest_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return dest_dir
