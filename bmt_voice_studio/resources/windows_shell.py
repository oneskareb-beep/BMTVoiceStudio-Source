"""Windows 11 taskbar / HWND icon binding.

The taskbar does not use the in-app PNG header. It uses the window-class
HICON plus AppUserModelID icon registration. A previously registered AppID
with a generic icon stays cached, so the ID must stay versionless but must
not reuse a poisoned identity.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Versionless. ".App" is a new identity so Windows drops the generic-icon cache
# left by earlier 1.3.1 / 1.3.2-dev launches of BelieversBusinessmenNetwork.BMTVoiceStudio.
WINDOWS_APP_USER_MODEL_ID = "BelieversBusinessmenNetwork.BMTVoiceStudio.App"


def current_app_id() -> str:
    return (os.environ.get("BMT_APP_USER_MODEL_ID") or "").strip() or WINDOWS_APP_USER_MODEL_ID


def taskbar_variant() -> str:
    """A = no AppID (portable default test). B = AppID + relaunch icon. empty = production."""
    return (os.environ.get("BMT_TASKBAR_VARIANT") or "").strip().upper()


def app_user_model_id_enabled() -> bool:
    if (os.environ.get("BMT_DISABLE_APP_USER_MODEL_ID") or "").strip().lower() in {"1", "true", "yes"}:
        return False
    if taskbar_variant() == "A":
        return False
    return True


def apply_windows_app_user_model_id() -> bool:
    if sys.platform != "win32" or not app_user_model_id_enabled():
        return False
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID.argtypes = [ctypes.c_wchar_p]
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID.restype = ctypes.HRESULT
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(current_app_id())
        return True
    except Exception:
        return False


def register_windows_shell_identity(*, exe: Path | None, ico: Path | None) -> bool:
    """Write HKCU AppUserModelId IconResource before any HWND exists."""
    if sys.platform != "win32" or not app_user_model_id_enabled():
        return False
    try:
        import winreg

        icon_res = ""
        if exe and exe.is_file():
            icon_res = f"{exe},0"
        elif ico and ico.is_file():
            icon_res = f"{ico},0"
        if not icon_res:
            return False
        app_id = current_app_id()
        key = winreg.CreateKey(
            winreg.HKEY_CURRENT_USER,
            rf"Software\Classes\AppUserModelId\{app_id}",
        )
        winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, "BMT Voice Studio")
        winreg.SetValueEx(key, "IconResource", 0, winreg.REG_SZ, icon_res)
        winreg.CloseKey(key)
        return True
    except Exception:
        return False


def _hicon_from_ico(ico: Path, size: int) -> int:
    import ctypes

    return int(ctypes.windll.user32.LoadImageW(0, str(ico), 1, size, size, 0x0010) or 0)


def _hicon_from_png(png: Path, size: int) -> int:
    try:
        from PIL import Image
    except Exception:
        return 0
    try:
        import ctypes
        from ctypes import wintypes
    except Exception:
        return 0
    try:
        src = Image.open(png).convert("RGBA")
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        fitted = src.copy()
        fitted.thumbnail((size, size), Image.Resampling.LANCZOS)
        canvas.paste(fitted, ((size - fitted.width) // 2, (size - fitted.height) // 2), fitted)

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

        class ICONINFO(ctypes.Structure):
            _fields_ = [
                ("fIcon", wintypes.BOOL),
                ("xHotspot", wintypes.DWORD),
                ("yHotspot", wintypes.DWORD),
                ("hbmMask", wintypes.HBITMAP),
                ("hbmColor", wintypes.HBITMAP),
            ]

        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = size
        bmi.bmiHeader.biHeight = -size
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bits = ctypes.c_void_p()
        hdc = ctypes.windll.user32.GetDC(0)
        ctypes.windll.gdi32.CreateDIBSection.restype = wintypes.HBITMAP
        hbm = ctypes.windll.gdi32.CreateDIBSection(hdc, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
        if not hbm or not bits.value:
            ctypes.windll.user32.ReleaseDC(0, hdc)
            return 0
        raw = canvas.tobytes("raw", "BGRA")
        ctypes.memmove(bits, raw, len(raw))
        hbm_mask = ctypes.windll.gdi32.CreateBitmap(size, size, 1, 1, None)
        info = ICONINFO(True, 0, 0, hbm_mask, hbm)
        hicon = int(ctypes.windll.user32.CreateIconIndirect(ctypes.byref(info)) or 0)
        ctypes.windll.gdi32.DeleteObject(hbm)
        if hbm_mask:
            ctypes.windll.gdi32.DeleteObject(hbm_mask)
        ctypes.windll.user32.ReleaseDC(0, hdc)
        return hicon
    except Exception:
        return 0


def _hicon_from_exe(exe: Path, size: int) -> int:
    import ctypes
    from ctypes import wintypes

    big = wintypes.HICON()
    small = wintypes.HICON()
    ctypes.windll.shell32.ExtractIconExW(str(exe), 0, ctypes.byref(big), ctypes.byref(small), 1)
    handle = int((big.value if size >= 24 else small.value) or big.value or small.value or 0)
    return handle


def load_taskbar_hicons(*, exe: Path | None, ico: Path | None, png: Path | None) -> tuple[int, int]:
    """Prefer the packaged ICO/PNG. Do not trust ExtractIconEx on a running EXE first."""
    hbig = hsmall = 0
    if ico and ico.is_file():
        hbig = _hicon_from_ico(ico, 32)
        hsmall = _hicon_from_ico(ico, 16)
    if (not hbig or not hsmall) and png and png.is_file():
        if not hbig:
            hbig = _hicon_from_png(png, 32)
        if not hsmall:
            hsmall = _hicon_from_png(png, 16)
    if (not hbig or not hsmall) and exe and exe.is_file():
        if not hbig:
            hbig = _hicon_from_exe(exe, 32)
        if not hsmall:
            hsmall = _hicon_from_exe(exe, 16)
    return hbig, hsmall


def apply_hwnd_and_class_icons(hwnd: int, hbig: int, hsmall: int) -> bool:
    if sys.platform != "win32" or not hwnd:
        return False
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    if hbig:
        user32.SendMessageW(hwnd, 0x0080, 1, hbig)
    if hsmall:
        user32.SendMessageW(hwnd, 0x0080, 0, hsmall)
    gclp_hicon = -14
    gclp_hiconsm = -34
    if ctypes.sizeof(ctypes.c_void_p) == 8:
        setter = user32.SetClassLongPtrW
        setter.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
        setter.restype = ctypes.c_void_p
    else:
        setter = user32.SetClassLongW
        setter.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
        setter.restype = ctypes.c_ulong
    if hbig:
        setter(hwnd, gclp_hicon, hbig)
    if hsmall:
        setter(hwnd, gclp_hiconsm, hsmall)
    return bool(hbig or hsmall)


def apply_window_relaunch_identity(hwnd: int, *, exe: Path | None, ico: Path | None) -> bool:
    if sys.platform != "win32" or not hwnd:
        return False
    try:
        import ctypes
        from ctypes import HRESULT, POINTER, Structure, c_ubyte, c_uint16, c_uint32, c_ulong, c_ushort, c_void_p, c_wchar_p

        class GUID(Structure):
            _fields_ = [("Data1", c_uint32), ("Data2", c_uint16), ("Data3", c_uint16), ("Data4", c_ubyte * 8)]

            def __init__(self, text: str = "00000000-0000-0000-0000-000000000000") -> None:
                parts = text.strip("{}").split("-")
                super().__init__()
                self.Data1 = int(parts[0], 16)
                self.Data2 = int(parts[1], 16)
                self.Data3 = int(parts[2], 16)
                rest = parts[3] + parts[4]
                for i in range(8):
                    self.Data4[i] = int(rest[i * 2 : i * 2 + 2], 16)

        class PROPERTYKEY(Structure):
            _fields_ = [("fmtid", GUID), ("pid", c_ulong)]

        class PROPVARIANT(Structure):
            _fields_ = [
                ("vt", c_ushort),
                ("wReserved1", c_ushort),
                ("wReserved2", c_ushort),
                ("wReserved3", c_ushort),
                ("pwszVal", c_wchar_p),
            ]

        ole32 = ctypes.windll.ole32
        ole32.CoInitialize(None)
        store = c_void_p()
        iid = GUID("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99")
        hr = ctypes.windll.shell32.SHGetPropertyStoreForWindow(hwnd, ctypes.byref(iid), ctypes.byref(store))
        if hr != 0 or not store.value:
            return False
        vtbl = ctypes.cast(store, POINTER(POINTER(c_void_p)))[0]
        set_value = ctypes.WINFUNCTYPE(HRESULT, c_void_p, POINTER(PROPERTYKEY), POINTER(PROPVARIANT))(vtbl[6])
        commit = ctypes.WINFUNCTYPE(HRESULT, c_void_p)(vtbl[7])
        release = ctypes.WINFUNCTYPE(c_ulong, c_void_p)(vtbl[2])
        fmtid = GUID("9F4C2852-9D1B-4CBF-8180-3B9D2678C8FF")
        icon_res = f"{exe},0" if exe else (f"{ico},0" if ico else "")
        command = f'"{exe}"' if exe else ""
        kept: list[str] = []
        pairs = [(5, current_app_id()), (4, "BMT Voice Studio")]
        if command:
            pairs.append((2, command))
        if icon_res:
            pairs.append((3, icon_res))
        for pid, value in pairs:
            kept.append(value)
            key = PROPERTYKEY(fmtid, pid)
            pv = PROPVARIANT()
            pv.vt = 31
            pv.pwszVal = value
            set_value(store, ctypes.byref(key), ctypes.byref(pv))
        commit(store)
        release(store)
        _ = kept
        return True
    except Exception:
        return False
