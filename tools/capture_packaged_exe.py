"""Launch packaged EXE and capture screenshots proving simplified UI."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "qa_screenshots" / "final_release"
SIZES = [(1920, 1080), (1600, 900), (1366, 768)]


def _find_exe() -> Path:
    for c in (
        ROOT / "release" / "BMTVoiceStudio-1.2.0-Windows-x64-Portable" / "BMTVoiceStudio" / "BMTVoiceStudio.exe",
        Path(r"C:\BMT_RELEASE_TEST\BMTVoiceStudio\BMTVoiceStudio.exe"),
        ROOT / "dist" / "BMTVoiceStudio" / "BMTVoiceStudio.exe",
    ):
        if c.exists():
            return c.resolve()
    raise FileNotFoundError("No packaged EXE found")


def _prepare_settings() -> None:
    from bmt_voice_studio.config.paths import daily_v11_welcome_marker, first_run_marker
    from bmt_voice_studio.config.settings import get_settings, save_settings

    first_run_marker().parent.mkdir(parents=True, exist_ok=True)
    first_run_marker().write_text("ok", encoding="utf-8")
    daily_v11_welcome_marker().write_text("ok", encoding="utf-8")
    s = get_settings()
    s.first_run_complete = True
    s.daily_v11_welcome_seen = True
    save_settings(s)


def _bmt_pids() -> list[int]:
    import ctypes
    from ctypes import wintypes

    # Use CreateToolhelp32Snapshot
    TH32CS_SNAPPROCESS = 0x00000002

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260),
        ]

    kernel32 = ctypes.windll.kernel32
    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    entry = PROCESSENTRY32W()
    entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
    pids: list[int] = []
    if kernel32.Process32FirstW(snap, ctypes.byref(entry)):
        while True:
            name = entry.szExeFile.lower()
            if "bmtvoicestudio" in name:
                pids.append(int(entry.th32ProcessID))
            if not kernel32.Process32NextW(snap, ctypes.byref(entry)):
                break
    kernel32.CloseHandle(snap)
    return pids


def _enum_windows(pids: set[int]) -> list[tuple[int, str, int]]:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    found: list[tuple[int, str, int]] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        proc_id = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(proc_id))
        if proc_id.value not in pids:
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        found.append((int(hwnd), buf.value or "", int(proc_id.value)))
        return True

    user32.EnumWindows(callback, 0)
    return found


def _capture_hwnd(hwnd: int, dest: Path) -> None:
    import ctypes
    from ctypes import wintypes

    from PIL import Image

    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32

    class RECT(ctypes.Structure):
        _fields_ = [
            ("left", wintypes.LONG),
            ("top", wintypes.LONG),
            ("right", wintypes.LONG),
            ("bottom", wintypes.LONG),
        ]

    rect = RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    w = max(1, rect.right - rect.left)
    h = max(1, rect.bottom - rect.top)
    hwnd_dc = user32.GetWindowDC(hwnd)
    mem_dc = gdi32.CreateCompatibleDC(hwnd_dc)
    bmp = gdi32.CreateCompatibleBitmap(hwnd_dc, w, h)
    old = gdi32.SelectObject(mem_dc, bmp)
    if not user32.PrintWindow(hwnd, mem_dc, 2):
        screen_dc = user32.GetDC(0)
        gdi32.BitBlt(mem_dc, 0, 0, w, h, screen_dc, rect.left, rect.top, 0x00CC0020)
        user32.ReleaseDC(0, screen_dc)

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ("biSize", wintypes.DWORD),
            ("biWidth", wintypes.LONG),
            ("biHeight", wintypes.LONG),
            ("biPlanes", wintypes.WORD),
            ("biBitCount", wintypes.WORD),
            ("biCompression", wintypes.DWORD),
            ("biSizeImage", wintypes.DWORD),
            ("biXPelsPerMeter", wintypes.LONG),
            ("biYPelsPerMeter", wintypes.LONG),
            ("biClrUsed", wintypes.DWORD),
            ("biClrImportant", wintypes.DWORD),
        ]

    bmi = BITMAPINFOHEADER()
    bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.biWidth = w
    bmi.biHeight = -h
    bmi.biPlanes = 1
    bmi.biBitCount = 32
    bmi.biCompression = 0
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mem_dc, bmp, 0, h, buf, ctypes.byref(bmi), 0)
    img = Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1)
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(dest)
    gdi32.SelectObject(mem_dc, old)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mem_dc)
    user32.ReleaseDC(hwnd, hwnd_dc)


def _process_image_path(pid: int) -> str:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(0x1000, False, pid)
    buf = ctypes.create_unicode_buffer(1024)
    size = wintypes.DWORD(1024)
    path = ""
    if handle:
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            path = buf.value
        kernel32.CloseHandle(handle)
    return path


def main() -> int:
    exe = _find_exe()
    OUT.mkdir(parents=True, exist_ok=True)
    _prepare_settings()
    print("LAUNCHING", exe)

    # Kill any prior instances so we capture the fresh build only.
    subprocess.run(["taskkill", "/F", "/IM", "BMTVoiceStudio.exe"], capture_output=True)
    time.sleep(1)

    proc = subprocess.Popen([str(exe)], cwd=str(exe.parent))
    hwnd = None
    win_pid = None
    log: list[str] = []
    for i in range(60):
        time.sleep(0.5)
        pids = set(_bmt_pids())
        wins = _enum_windows(pids)
        log.append(f"t={i*0.5:.1f}s pids={sorted(pids)} wins={wins}")
        for h, title, pid in wins:
            if "BMT" in title or "Voice" in title or "Daily" in title:
                hwnd, win_pid = h, pid
                break
        if hwnd:
            break
        if wins:
            hwnd, win_pid = wins[0][0], wins[0][2]
            break

    (OUT / "window_enum.log").write_text("\n".join(log), encoding="utf-8")
    if hwnd is None:
        subprocess.run(["taskkill", "/F", "/IM", "BMTVoiceStudio.exe"], capture_output=True)
        raise SystemExit("Window not found. See window_enum.log")

    import ctypes

    user32 = ctypes.windll.user32
    user32.ShowWindow(hwnd, 9)
    user32.SetForegroundWindow(hwnd)
    time.sleep(1.5)

    pe = _process_image_path(win_pid or proc.pid) or str(exe)
    print("PROCESS_EXE", pe)
    print("WINDOW_TITLE_PID", win_pid, "hwnd", hwnd)
    (OUT / "process_exe.txt").write_text(pe + "\n", encoding="utf-8")
    (OUT / "exe_path.txt").write_text(
        f"launched={exe}\nprocess={pe}\nmtime={time.ctime(exe.stat().st_mtime)}\n",
        encoding="utf-8",
    )

    for w, h in SIZES:
        user32.MoveWindow(hwnd, 20, 20, w, h, True)
        time.sleep(1.2)
        dest = OUT / f"daily_bmt_{w}x{h}.png"
        _capture_hwnd(hwnd, dest)
        print("WROTE", dest, dest.stat().st_size)

    subprocess.run(["taskkill", "/F", "/IM", "BMTVoiceStudio.exe"], capture_output=True)
    print("DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
