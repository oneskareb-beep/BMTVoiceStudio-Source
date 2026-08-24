"""Inspect PE icon resources in the current 1.3.2 FINAL EXE. Does not modify it."""

from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXE = ROOT / "dist" / "BMTVoiceStudio-1.3.2" / "BMTVoiceStudio.exe"
OUT = ROOT / "qa_outputs" / "taskbar_diag"
SOURCE_ICO = ROOT / "bmt_voice_studio" / "resources" / "bmt_voice_studio.ico"


def _extract_via_win32(exe: Path, dest_dir: Path) -> dict:
    import ctypes
    from ctypes import wintypes

    from PIL import Image

    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    shell32 = ctypes.windll.shell32
    count = int(shell32.ExtractIconExW(str(exe), -1, None, None, 0))
    previews = []
    for index in range(max(0, count)):
        big = wintypes.HICON()
        small = wintypes.HICON()
        shell32.ExtractIconExW(str(exe), index, ctypes.byref(big), ctypes.byref(small), 1)
        for label, handle, size in (("big", int(big.value or 0), 32), ("small", int(small.value or 0), 16)):
            if not handle:
                continue
            hdc = user32.GetDC(0)
            mem = gdi32.CreateCompatibleDC(hdc)
            bmp = gdi32.CreateCompatibleBitmap(hdc, size, size)
            gdi32.SelectObject(mem, bmp)
            user32.DrawIconEx(mem, 0, 0, handle, size, size, 0, 0, 3)

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
            hdr.biWidth = size
            hdr.biHeight = -size
            hdr.biPlanes = 1
            hdr.biBitCount = 32
            buf = (ctypes.c_ubyte * (size * size * 4))()
            gdi32.GetDIBits(mem, bmp, 0, size, buf, ctypes.byref(hdr), 0)
            path = dest_dir / f"exe_extract_{index}_{label}_{size}.png"
            Image.frombytes("RGBA", (size, size), bytes(buf), "raw", "BGRA").save(path)
            previews.append(str(path))
            user32.DestroyIcon(handle)
            gdi32.DeleteObject(bmp)
            gdi32.DeleteDC(mem)
            user32.ReleaseDC(0, hdc)
    return {"extract_icon_ex_count": count, "previews": previews}


def _pe_icon_resources(exe: Path) -> dict:
    import pefile

    pe = pefile.PE(str(exe))
    groups = []
    icons = []
    if not hasattr(pe, "DIRECTORY_ENTRY_RESOURCE"):
        return {"has_resource_directory": False}
    for entry in pe.DIRECTORY_ENTRY_RESOURCE.entries:
        name = getattr(entry, "id", None)
        if name == pefile.RESOURCE_TYPE["RT_GROUP_ICON"]:
            for res in getattr(entry, "directory", type("d", (), {"entries": []})).entries:
                for item in getattr(res, "directory", type("d", (), {"entries": []})).entries:
                    data = pe.get_data(item.data.struct.OffsetToData, item.data.struct.Size)
                    # GRPICONDIR
                    if len(data) >= 6:
                        _r, itype, count = struct.unpack_from("<HHH", data)
                        sizes = []
                        for i in range(count):
                            off = 6 + i * 14
                            if off + 14 <= len(data):
                                w, h, _cc, _res, planes, bits, nbytes, ordinal = struct.unpack_from("<BBBBHHIH", data, off)
                                sizes.append({"w": w or 256, "h": h or 256, "bits": bits, "bytes": nbytes, "ordinal": ordinal})
                        groups.append({"id": getattr(res, "id", None), "count": count, "sizes": sizes})
        if name == pefile.RESOURCE_TYPE["RT_ICON"]:
            for res in getattr(entry, "directory", type("d", (), {"entries": []})).entries:
                for item in getattr(res, "directory", type("d", (), {"entries": []})).entries:
                    icons.append(
                        {
                            "id": getattr(res, "id", None),
                            "size_bytes": item.data.struct.Size,
                        }
                    )
    pe.close()
    all_sizes = { (s["w"], s["h"]) for g in groups for s in g["sizes"] }
    return {
        "has_resource_directory": True,
        "group_icon_count": len(groups),
        "rt_icon_count": len(icons),
        "groups": groups,
        "icon_images": icons,
        "declared_sizes": sorted(all_sizes),
        "has_256": (256, 256) in all_sizes,
    }


def _looks_like_bbnet(png_path: Path) -> dict:
    from PIL import Image

    im = Image.open(png_path).convert("RGBA")
    pixels = list(im.getdata())
    n = max(1, len(pixels))
    gold = sum(1 for r, g, b, a in pixels if a > 40 and r > 140 and g > 90 and b < 120)
    blue = sum(1 for r, g, b, a in pixels if a > 40 and b > 80 and b > r)
    return {
        "path": str(png_path),
        "size": list(im.size),
        "gold_ratio": round(gold / n, 4),
        "blue_ratio": round(blue / n, 4),
        "likely_bbnet": (gold / n) > 0.02 and (blue / n) > 0.02,
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    report: dict = {
        "exe": str(EXE),
        "exe_exists": EXE.is_file(),
        "source_ico_exists": SOURCE_ICO.is_file(),
        "source_ico_bytes": SOURCE_ICO.stat().st_size if SOURCE_ICO.is_file() else 0,
    }
    if not EXE.is_file():
        (OUT / "exe_icon_inspect.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print("MISSING", EXE)
        return 1
    report["exe_bytes"] = EXE.stat().st_size
    report["pe"] = _pe_icon_resources(EXE)
    report["win32"] = _extract_via_win32(EXE, OUT)
    colors = []
    for preview in report["win32"].get("previews", []):
        colors.append(_looks_like_bbnet(Path(preview)))
    report["bbnet_color_check"] = colors
    (OUT / "exe_icon_inspect.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
