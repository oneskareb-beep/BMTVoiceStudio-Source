"""Launch a uniquely named EXE copy and capture title bar + taskbar + Explorer."""

from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

from PIL import Image, ImageGrab

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "dist" / "BMTVoiceStudio-1.3.1"
OUT = ROOT / "qa_outputs" / "windows_icon_1.3.1"
FRESH = Path(os.environ.get("TEMP", ".")) / f"BMTIconProof_{os.getpid()}"
user32 = ctypes.windll.user32
WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
WM_GETICON = 0x007F
ICON_BIG = 1
ICON_SMALL2 = 2
GCLP_HICON = -14


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


def _windows_for_pid(pid: int) -> list[tuple[int, bool, str]]:
    found: list[tuple[int, bool, str]] = []

    def cb(hwnd, _lparam):
        wpid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
        if wpid.value == pid:
            n = user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            found.append((int(hwnd), bool(user32.IsWindowVisible(hwnd)), buf.value))
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return found


def _hicon_png(hicon: int, dest: Path) -> None:
    if not hicon:
        return
    class ICONINFO(ctypes.Structure):
        _fields_ = [
            ("fIcon", wintypes.BOOL),
            ("xHotspot", wintypes.DWORD),
            ("yHotspot", wintypes.DWORD),
            ("hbmMask", wintypes.HBITMAP),
            ("hbmColor", wintypes.HBITMAP),
        ]

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

    info = ICONINFO()
    if not user32.GetIconInfo(hicon, ctypes.byref(info)):
        return
    hdc = ctypes.windll.gdi32.CreateCompatibleDC(0)
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
    ctypes.windll.gdi32.PatBlt(hdc, 0, 0, size, size, 0x00000042)
    user32.DrawIconEx(hdc, 0, 0, hicon, size, size, 0, 0, 0x0003)
    buf = ctypes.string_at(bits, size * size * 4)
    Image.frombytes("RGBA", (size, size), buf, "raw", "BGRA").save(dest)
    ctypes.windll.gdi32.SelectObject(hdc, old)
    ctypes.windll.gdi32.DeleteObject(hbmp)
    ctypes.windll.gdi32.DeleteDC(hdc)
    try:
        if info.hbmColor:
            ctypes.windll.gdi32.DeleteObject(info.hbmColor)
        if info.hbmMask:
            ctypes.windll.gdi32.DeleteObject(info.hbmMask)
    except Exception:
        pass


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    OUT.mkdir(parents=True, exist_ok=True)
    print("copy", SRC, "->", FRESH, flush=True)
    shutil.copytree(SRC, FRESH)
    exe = FRESH / "BMTIconProof.exe"
    (FRESH / "BMTVoiceStudio.exe").rename(exe)
    print("exe", exe, flush=True)

    env = os.environ.copy()
    env["BMT_SKIP_LIBRARY_DIALOG"] = "1"
    env["BMT_SKIP_RECOVERY"] = "1"
    # Unique AppID so this proof run is not grouped with a stale taskbar pin cache.
    env["BMT_APP_USER_MODEL_ID"] = "BelieversBusinessmenNetwork.BMTVoiceStudio.IconProof"
    env.pop("QT_QPA_PLATFORM", None)
    proc = subprocess.Popen([str(exe)], cwd=str(FRESH), env=env)
    print("pid", proc.pid, flush=True)

    hwnd = 0
    title = ""
    for i in range(90):
        time.sleep(1)
        vis = [w for w in _windows_for_pid(proc.pid) if w[1] and w[2]]
        if vis:
            hwnd, _, title = vis[0]
            print(f"window {i+1}s {hwnd:#x} {title!r}", flush=True)
            break
        if i in (8, 20, 40) or proc.poll() is not None:
            print(f"wait {i+1}s exit={proc.poll()} wins={_windows_for_pid(proc.pid)}", flush=True)
        if proc.poll() is not None:
            break

    (OUT / "live_window.txt").write_text(
        f"pid={proc.pid}\nhwnd={hwnd}\ntitle={title}\nexe={exe}\n", encoding="utf-8"
    )
    if not hwnd:
        print("NO_WINDOW", flush=True)
        return 1

    user32.ShowWindow(hwnd, 9)
    user32.SetForegroundWindow(hwnd)
    time.sleep(1.2)
    rc = RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rc))
    shot = ImageGrab.grab(all_screens=True)
    shot.save(OUT / "desktop_iconproof.png")
    left = max(int(rc.left), 0)
    top = max(int(rc.top), 0)
    right = min(int(rc.right), shot.width)
    bottom = min(top + 72, shot.height)
    if right > left and bottom > top:
        shot.crop((left, top, right, bottom)).save(OUT / "titlebar_crop.png")
    w, h = shot.size
    shot.crop((0, h - 80, w, h)).save(OUT / "taskbar_iconproof.png")
    cx0, cx1 = max(0, w // 2 - 500), min(w, w // 2 + 500)
    shot.crop((cx0, h - 80, cx1, h)).resize(( (cx1 - cx0) * 3, 240), Image.Resampling.NEAREST).save(
        OUT / "taskbar_iconproof_3x.png"
    )
    try:
        hicon = user32.SendMessageW(hwnd, WM_GETICON, ICON_BIG, 0) or user32.SendMessageW(
            hwnd, WM_GETICON, ICON_SMALL2, 0
        )
        if not hicon:
            getter = getattr(user32, "GetClassLongPtrW", user32.GetClassLongW)
            hicon = getter(hwnd, GCLP_HICON)
        print("hicon", hicon, flush=True)
        _hicon_png(int(hicon or 0), OUT / "live_window_hicon.png")
    except Exception as exc:
        print("hicon_skip", exc, flush=True)

    # Explorer: unique folder, then try to foreground it
    subprocess.Popen(["explorer.exe", str(FRESH)])
    time.sleep(2.5)

    def focus_explorer(_hwnd, _lparam):
        n = user32.GetWindowTextLengthW(_hwnd)
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(_hwnd, buf, n + 1)
        if user32.IsWindowVisible(_hwnd) and "BMTIconProof" in (buf.value or ""):
            user32.ShowWindow(_hwnd, 9)
            user32.SetForegroundWindow(_hwnd)
        return True

    user32.EnumWindows(WNDENUMPROC(focus_explorer), 0)
    time.sleep(1)
    ImageGrab.grab(all_screens=True).save(OUT / "explorer_iconproof.png")
    print("OUT", OUT, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
