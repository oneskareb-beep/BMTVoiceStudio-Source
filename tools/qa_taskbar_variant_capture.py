"""Launch one diagnostic EXE, capture taskbar / title / Alt+Tab / Explorer."""

from __future__ import annotations

import argparse
import ctypes
import os
import subprocess
import time
from ctypes import wintypes
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageGrab

ROOT = Path(__file__).resolve().parents[1]
user32 = ctypes.windll.user32


def _kill() -> None:
    subprocess.run(["taskkill", "/F", "/IM", "BMTVoiceStudio.exe"], capture_output=True, check=False)
    time.sleep(1.5)


def _enum() -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cb(h, _lp):
        if user32.IsWindowVisible(h):
            n = user32.GetWindowTextLengthW(h)
            buf = ctypes.create_unicode_buffer(n + 2)
            user32.GetWindowTextW(h, buf, n + 2)
            if "BMT Voice Studio" in buf.value:
                found.append((int(h), buf.value))
        return True

    user32.EnumWindows(cb, 0)
    return found


def _annotate(im: Image.Image, text: str) -> Image.Image:
    draw = ImageDraw.Draw(im)
    draw.rectangle((8, 8, min(im.width - 8, 1100), 48), fill=(8, 16, 32))
    try:
        font = ImageFont.truetype("segoeui.ttf", 16)
    except Exception:
        font = ImageFont.load_default()
    draw.text((16, 16), text, fill=(240, 220, 150), font=font)
    return im


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--exe", required=True)
    p.add_argument("--label", required=True)
    args = p.parse_args()
    exe = Path(args.exe)
    out = ROOT / "qa_screenshots" / "taskbar_diag" / args.label
    out.mkdir(parents=True, exist_ok=True)
    if not exe.is_file():
        print("MISSING", exe)
        return 1

    explorer = subprocess.Popen(["explorer", "/select,", str(exe)])
    time.sleep(2.0)
    desk = ImageGrab.grab(all_screens=True)
    _annotate(desk, f"{args.label} File Explorer EXE").save(out / "explorer.png")

    _kill()
    env = os.environ.copy()
    env["BMT_SKIP_LIBRARY_DIALOG"] = "1"
    proc = subprocess.Popen([str(exe)], cwd=str(exe.parent), env=env)
    hwnd = 0
    title = ""
    for _ in range(80):
        wins = _enum()
        if wins:
            hwnd, title = wins[0]
            break
        time.sleep(0.4)
    time.sleep(2.0)
    if hwnd:
        user32.ShowWindow(hwnd, 3)
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.8)
    full = ImageGrab.grab(all_screens=True)
    _annotate(full, f"{args.label} RUNNING TASKBAR (primary)").save(out / "running.png")
    full.crop((0, max(0, full.height - 90), full.width, full.height)).save(out / "taskbar.png")
    if hwnd:
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        full.crop((max(0, rect.left), max(0, rect.top), min(full.width, rect.left + 560), min(full.height, rect.top + 56))).save(
            out / "titlebar.png"
        )
    user32.keybd_event(0x12, 0, 0, 0)
    user32.keybd_event(0x09, 0, 0, 0)
    time.sleep(0.7)
    alt = ImageGrab.grab(all_screens=True)
    _annotate(alt, f"{args.label} Alt+Tab").save(out / "alttab.png")
    user32.keybd_event(0x09, 0, 2, 0)
    user32.keybd_event(0x12, 0, 2, 0)
    (out / "notes.txt").write_text(f"exe={exe}\nhwnd={hwnd}\ntitle={title}\npid={proc.pid}\n", encoding="utf-8")
    print("HWND", hwnd, title, "OUT", out)
    _kill()
    return 0 if hwnd else 2


if __name__ == "__main__":
    raise SystemExit(main())
