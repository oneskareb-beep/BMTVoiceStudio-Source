"""Probe ASS caption double-stroke rendering with imageio ffmpeg."""

from __future__ import annotations

import subprocess
from pathlib import Path

from bmt_voice_studio.audio.ffmpeg_service import FFmpegService
from bmt_voice_studio.video.captions import hex_to_ass_color

OUT = Path("release/_cap_dup_test")
OUT.mkdir(parents=True, exist_ok=True)
FF = FFmpegService().find()
CUE = "Seek first the kingdom of God"
PRIMARY = hex_to_ass_color("#FFFFFF")
OUTLINE = hex_to_ass_color("#0A3A8C")
BLACK = hex_to_ass_color("#000000")


def write_ass(path: Path, *, scaled: str, font: str, outline_w: int, bold: int = 0, body: str = CUE) -> None:
    path.write_text(
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "WrapStyle: 0\n"
        "PlayResX: 1080\n"
        "PlayResY: 1920\n"
        f"ScaledBorderAndShadow: {scaled}\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,{font},72,{PRIMARY},&H000000FF,{OUTLINE},&H80000000,"
        f"{bold},0,0,0,100,100,0,0,1,{outline_w},0,2,86,86,192,1\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        f"Dialogue: 0,0:00:00.00,0:00:02.00,Default,,0,0,0,,{body}\n",
        encoding="utf-8",
    )


def render(ass: Path, dest: Path, filt: str) -> bool:
    raw = str(ass.resolve()).replace("\\", "/")
    esc = raw.replace(":", r"\:").replace("'", r"\'")
    vf = f"{filt}='{esc}'"
    cmd = [
        FF,
        "-y",
        "-f",
        "lavfi",
        "-i",
        "color=c=0x1a2030:s=1080x1920:d=1:r=1",
        "-vf",
        vf,
        "-frames:v",
        "1",
        "-update",
        "1",
        str(dest),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    ok = proc.returncode == 0 and dest.is_file() and dest.stat().st_size > 1000
    if not ok:
        print("FAIL", dest.name, proc.stderr[-400:])
    else:
        print("OK", dest.name, dest.stat().st_size)
    return ok


def main() -> None:
    cases = [
        ("segoe_scaled_yes_o10", "yes", "Segoe UI", 10, 0, CUE),
        ("segoe_scaled_no_o10", "no", "Segoe UI", 10, 0, CUE),
        ("arial_scaled_no_o4", "no", "Arial", 4, -1, CUE),
        ("arial_scaled_yes_o2", "yes", "Arial", 2, -1, CUE),
        ("arial_bord_tag", "no", "Arial", 0, -1, r"{\bord4\3c&H8C3A0A&}" + CUE),
        ("black_o3", "no", "Arial", 3, -1, CUE),
    ]
    for name, scaled, font, ow, bold, body in cases:
        ass = OUT / f"{name}.ass"
        write_ass(ass, scaled=scaled, font=font, outline_w=ow, bold=bold, body=body)
        render(ass, OUT / f"{name}_ass.png", "ass")
        render(ass, OUT / f"{name}_sub.png", "subtitles")


if __name__ == "__main__":
    main()
