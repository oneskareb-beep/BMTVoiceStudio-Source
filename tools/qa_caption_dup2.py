"""More ASS variants: outline 0, shadow, fontsdir, force_style."""

from __future__ import annotations

import subprocess
from pathlib import Path

from bmt_voice_studio.audio.ffmpeg_service import FFmpegService
from bmt_voice_studio.video.captions import hex_to_ass_color

OUT = Path("release/_cap_dup_test2")
OUT.mkdir(parents=True, exist_ok=True)
FF = FFmpegService().find()
CUE = "Seek first the kingdom of God"


def render(ass: Path, dest: Path, vf: str) -> None:
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
    print(dest.name, "OK" if proc.returncode == 0 and dest.is_file() else "FAIL", dest.stat().st_size if dest.is_file() else 0)


def write(path: Path, style: str, body: str = CUE) -> None:
    path.write_text(
        "[Script Info]\nScriptType: v4.00+\nWrapStyle: 0\nPlayResX: 1080\nPlayResY: 1920\n"
        "ScaledBorderAndShadow: no\n\n[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"{style}\n\n[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        f"Dialogue: 0,0:00:00.00,0:00:02.00,Default,,0,0,0,,{body}\n",
        encoding="utf-8",
    )


def main() -> None:
    p = hex_to_ass_color("#FFFFFF")
    o = hex_to_ass_color("#000000")
    cases = {
        "no_outline": f"Style: Default,Arial,72,{p},&H000000FF,{o},&H00000000,0,0,0,0,100,100,0,0,1,0,0,2,86,86,192,1",
        "outline3_black": f"Style: Default,Arial,72,{p},&H000000FF,{o},&H00000000,0,0,0,0,100,100,0,0,1,3,0,2,86,86,192,1",
        "outline3_bold0": f"Style: Default,Arial,72,{p},&H000000FF,{o},&H00000000,0,0,0,0,100,100,0,0,1,3,0,2,86,86,192,1",
        "two_layer": f"Style: Default,Arial,72,{p},&H000000FF,{o},&H00000000,0,0,0,0,100,100,0,0,1,0,0,2,86,86,192,1",
    }
    for name, style in cases.items():
        ass = OUT / f"{name}.ass"
        body = CUE
        if name == "two_layer":
            # classic clean burn: outline-only then fill
            write(
                ass,
                style,
                body="",
            )
            ass.write_text(
                ass.read_text(encoding="utf-8").replace(
                    "Dialogue: 0,0:00:00.00,0:00:02.00,Default,,0,0,0,,\n",
                    "Dialogue: 0,0:00:00.00,0:00:02.00,Default,,0,0,0,,"
                    + r"{\alpha&HFF&\3a&H00&\bord4\shad0}"
                    + CUE
                    + "\n"
                    + "Dialogue: 1,0:00:00.00,0:00:02.00,Default,,0,0,0,,"
                    + r"{\bord0\shad0}"
                    + CUE
                    + "\n",
                ),
                encoding="utf-8",
            )
        else:
            write(ass, style, body)
        raw = str(ass.resolve()).replace("\\", "/")
        esc = raw.replace(":", r"\:").replace("'", r"\'")
        render(ass, OUT / f"{name}.png", f"ass='{esc}'")

    # force_style via subtitles filter
    ass = OUT / "plain.ass"
    write(ass, cases["no_outline"])
    raw = str(ass.resolve()).replace("\\", "/")
    esc = raw.replace(":", r"\:").replace("'", r"\'")
    render(
        ass,
        OUT / "force_style.png",
        f"subtitles='{esc}':force_style='Outline=3,Shadow=0,BorderStyle=1,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000'",
    )


if __name__ == "__main__":
    main()
