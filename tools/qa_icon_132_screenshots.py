"""Launch 1.3.2-dev EXE and capture Windows chrome proof (taskbar is primary)."""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageGrab

ROOT = Path(__file__).resolve().parents[1]
EXE = ROOT / "dist" / "BMTVoiceStudio-1.3.2-dev" / "BMTVoiceStudio.exe"
OUT = ROOT / "qa_screenshots" / "icon_1_3_2_dev"


user32 = ctypes.windll.user32
shell32 = ctypes.windll.shell32
gdi32 = ctypes.windll.gdi32


def _kill_old() -> None:
    subprocess.run(
        ["taskkill", "/F", "/IM", "BMTVoiceStudio.exe"],
        capture_output=True,
        text=True,
        check=False,
    )
    time.sleep(1.2)


def _enum_hwnds() -> list[int]:
    hwnds: list[int] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def _cb(hwnd, _lp):
        if user32.IsWindowVisible(hwnd):
            hwnds.append(int(hwnd))
        return True

    user32.EnumWindows(_cb, 0)
    return hwnds


def _title(hwnd: int) -> str:
    n = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 2)
    user32.GetWindowTextW(hwnd, buf, n + 2)
    return buf.value


def _wait_hwnd(timeout: float = 45.0) -> int:
    deadline = time.time() + timeout
    while time.time() < deadline:
        for hwnd in _enum_hwnds():
            t = _title(hwnd)
            if "BMT Voice Studio" in t or "BMT VOICE" in t.upper():
                return hwnd
        time.sleep(0.4)
    return 0


def _extract_exe_icon(dest: Path) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    big = wintypes.HICON()
    small = wintypes.HICON()
    n = shell32.ExtractIconExW(str(EXE), 0, ctypes.byref(big), ctypes.byref(small), 1)
    if n < 1 or not big.value:
        return False
    hdc = user32.GetDC(0)
    mem = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, 32, 32)
    gdi32.SelectObject(mem, bmp)
    user32.DrawIconEx(mem, 0, 0, big.value, 32, 32, 0, 0, 3)
    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ("biSize", wintypes.DWORD),
            ("biWidth", ctypes.c_long),
            ("biHeight", ctypes.c_long),
            ("biPlanes", wintypes.WORD),
            ("biBitCount", wintypes.WORD),
            ("biCompression", wintypes.DWORD),
            ("biSizeImage", wintypes.DWORD),
            ("biXPelsPerMeter", ctypes.c_long),
            ("biYPelsPerMeter", ctypes.c_long),
            ("biClrUsed", wintypes.DWORD),
            ("biClrImportant", wintypes.DWORD),
        ]

    hdr = BITMAPINFOHEADER()
    hdr.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    hdr.biWidth = 32
    hdr.biHeight = -32
    hdr.biPlanes = 1
    hdr.biBitCount = 32
    buf = (ctypes.c_ubyte * (32 * 32 * 4))()
    gdi32.GetDIBits(mem, bmp, 0, 32, buf, ctypes.byref(hdr), 0)
    Image.frombytes("RGBA", (32, 32), bytes(buf), "raw", "BGRA").save(dest)
    user32.DestroyIcon(big.value)
    if small.value:
        user32.DestroyIcon(small.value)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mem)
    user32.ReleaseDC(0, hdc)
    return dest.is_file()


def _annotate(im: Image.Image, text: str) -> Image.Image:
    draw = ImageDraw.Draw(im)
    draw.rectangle((8, 8, 980, 52), fill=(8, 16, 32, 220))
    try:
        font = ImageFont.truetype("segoeui.ttf", 18)
    except Exception:
        font = ImageFont.load_default()
    draw.text((16, 16), text, fill=(240, 220, 150), font=font)
    return im


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    if not EXE.is_file():
        print("MISSING", EXE)
        return 1

    ico_ok = _extract_exe_icon(OUT / "exe_resource_icon_32.png")
    print("EXE_RESOURCE_ICON", ico_ok, OUT / "exe_resource_icon_32.png")

    explorer = subprocess.Popen(["explorer", "/select,", str(EXE)])
    time.sleep(2.0)
    desk = ImageGrab.grab(all_screens=True)
    _annotate(desk, "1.3.2-dev File Explorer EXE selection (icon in folder)").save(OUT / "explorer_exe.png")

    _kill_old()
    env = os.environ.copy()
    env["BMT_SKIP_LIBRARY_DIALOG"] = "1"
    proc = subprocess.Popen([str(EXE)], cwd=str(EXE.parent), env=env)
    hwnd = _wait_hwnd(50)
    print("HWND", hwnd, "PID", proc.pid, "TITLE", _title(hwnd) if hwnd else "")
    time.sleep(2.5)
    full = ImageGrab.grab(all_screens=True)
    _annotate(full, "1.3.2-dev RUNNING — inspect TASKBAR icon (primary test)").save(OUT / "running_desktop_taskbar.png")
    h = full.height
    taskbar = full.crop((0, max(0, h - 90), full.width, h))
    _annotate(taskbar, "Taskbar crop — BMT 1.3.2-dev should show BBNet, not generic cube").save(
        OUT / "taskbar_crop.png"
    )
    if hwnd:
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        titlebar = full.crop((rect.left, rect.top, min(rect.left + 420, full.width), min(rect.top + 48, full.height)))
        titlebar.save(OUT / "titlebar.png")

    user32.keybd_event(0x12, 0, 0, 0)  # ALT
    user32.keybd_event(0x09, 0, 0, 0)  # TAB
    time.sleep(0.7)
    alt = ImageGrab.grab(all_screens=True)
    _annotate(alt, "Alt+Tab — 1.3.2-dev").save(OUT / "alttab.png")
    user32.keybd_event(0x09, 0, 2, 0)
    user32.keybd_event(0x12, 0, 2, 0)
    time.sleep(0.3)

    (OUT / "notes.txt").write_text(
        f"exe={EXE}\nhwnd={hwnd}\npid={proc.pid}\nexplorer={explorer.pid}\n",
        encoding="utf-8",
    )
    print("WROTE", OUT)
    return 0 if hwnd else 2


if __name__ == "__main__":
    raise SystemExit(main())
