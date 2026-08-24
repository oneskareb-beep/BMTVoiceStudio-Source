"""Live Windows chrome proof: window title, taskbar, Explorer EXE icon."""

from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

from PIL import Image, ImageDraw, ImageGrab

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "dist" / "BMTVoiceStudio-1.3.1"
OUT = ROOT / "qa_outputs" / "windows_icon_1.3.1"
FRESH = Path(os.environ.get("TEMP", ".")) / "BMTVS-IconProof-131"
user32 = ctypes.windll.user32
WM_GETICON = 0x007F
ICON_SMALL2 = 2
ICON_BIG = 1
GCLP_HICON = -14
SRCCOPY = 0x00CC0020


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


def _enum_windows() -> list[tuple[int, str, int]]:
    results: list[tuple[int, str, int]] = []
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

    def _cb(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value or ""
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        results.append((int(hwnd), title, int(pid.value)))
        return True

    user32.EnumWindows(WNDENUMPROC(_cb), 0)
    return results


def _hicon_to_png(hicon: int, dest: Path) -> bool:
    if not hicon:
        return False
    ico = ctypes.windll.user32
    class ICONINFO(ctypes.Structure):
        _fields_ = [
            ("fIcon", wintypes.BOOL),
            ("xHotspot", wintypes.DWORD),
            ("yHotspot", wintypes.DWORD),
            ("hbmMask", wintypes.HBITMAP),
            ("hbmColor", wintypes.HBITMAP),
        ]

    info = ICONINFO()
    if not ico.GetIconInfo(hicon, ctypes.byref(info)):
        return False
    # Draw icon onto a 64x64 bitmap via PrintWindow-less DrawIconEx
    hdc = ctypes.windll.gdi32.CreateCompatibleDC(0)
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

    class BITMAPINFO(ctypes.Structure):
        _fields_ = [("bmiHeader", BITMAPINFOHEADER)]

    size = 64
    bmi = BITMAPINFO()
    bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth = size
    bmi.bmiHeader.biHeight = -size
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    bits = ctypes.c_void_p()
    hbmp = ctypes.windll.gdi32.CreateDIBSection(hdc, ctypes.byref(bmi), 0, ctypes.byref(bits), 0, 0)
    old = ctypes.windll.gdi32.SelectObject(hdc, hbmp)
    ctypes.windll.gdi32.PatBlt(hdc, 0, 0, size, size, 0x00000042)  # BLACKNESS
    user32.DrawIconEx(hdc, 0, 0, hicon, size, size, 0, 0, 0x0003)
    buf = ctypes.string_at(bits, size * size * 4)
    im = Image.frombytes("RGBA", (size, size), buf, "raw", "BGRA")
    im.save(dest)
    ctypes.windll.gdi32.SelectObject(hdc, old)
    ctypes.windll.gdi32.DeleteObject(hbmp)
    ctypes.windll.gdi32.DeleteDC(hdc)
    if info.hbmColor:
        ctypes.windll.gdi32.DeleteObject(info.hbmColor)
    if info.hbmMask:
        ctypes.windll.gdi32.DeleteObject(info.hbmMask)
    return dest.is_file()


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    if FRESH.exists():
        shutil.rmtree(FRESH, ignore_errors=True)
    shutil.copytree(SRC, FRESH)
    exe = FRESH / "BMTVoiceStudio.exe"
    env = os.environ.copy()
    env["BMT_SKIP_LIBRARY_DIALOG"] = "1"
    env["BMT_SKIP_RECOVERY"] = "1"
    env.pop("QT_QPA_PLATFORM", None)
    proc = subprocess.Popen([str(exe)], cwd=str(FRESH), env=env)
    hwnd = 0
    title = ""
    for _ in range(40):
        time.sleep(0.5)
        for h, t, pid in _enum_windows():
            if pid == proc.pid and "BMT" in t:
                hwnd = h
                title = t
                break
        if hwnd:
            break
    print("PID", proc.pid, "HWND", hwnd, "TITLE", title)
    (OUT / "live_window.txt").write_text(f"pid={proc.pid}\nhwnd={hwnd}\ntitle={title}\nexe={exe}\n", encoding="utf-8")
    if hwnd:
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        user32.SetForegroundWindow(hwnd)
        time.sleep(1)
        hicon = user32.SendMessageW(hwnd, WM_GETICON, ICON_BIG, 0) or user32.SendMessageW(hwnd, WM_GETICON, ICON_SMALL2, 0)
        if not hicon:
            if hasattr(user32, "GetClassLongPtrW"):
                hicon = user32.GetClassLongPtrW(hwnd, GCLP_HICON)
            else:
                hicon = user32.GetClassLongW(hwnd, GCLP_HICON)
        print("HICON", hicon)
        _hicon_to_png(int(hicon), OUT / "live_window_hicon.png")
        rc = RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rc))
        shot = ImageGrab.grab(all_screens=True)
        shot.save(OUT / "desktop_live.png")
        win = shot.crop((max(rc.left, 0), max(rc.top, 0), min(rc.right, shot.width), min(rc.top + 80, shot.height)))
        win.save(OUT / "titlebar_crop.png")
        bar = shot.crop((0, shot.height - 72, shot.width, shot.height))
        bar.save(OUT / "taskbar_live.png")
        cx0, cx1 = max(0, shot.width // 2 - 460), min(shot.width, shot.width // 2 + 460)
        center = shot.crop((cx0, shot.height - 72, cx1, shot.height))
        center.resize((center.size[0] * 3, center.size[1] * 3), Image.Resampling.NEAREST).save(OUT / "taskbar_live_3x.png")
    # Explorer view of the EXE
    subprocess.Popen(["explorer.exe", f"/select,{exe}"])
    time.sleep(2)
    ImageGrab.grab(all_screens=True).save(OUT / "explorer_select.png")
    print("OUT", OUT)
    return 0 if hwnd else 1


if __name__ == "__main__":
    raise SystemExit(main())
