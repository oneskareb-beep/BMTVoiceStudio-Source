"""Build a Windows-compatible multi-resolution ICO from the official BBNet logo.

Small sizes use 32-bit BMP/DIB (what the taskbar prefers). 256px uses PNG.
"""

from __future__ import annotations

import struct
from io import BytesIO
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "bmt_voice_studio" / "resources" / "bbnet_logo.png"
DEST = ROOT / "bmt_voice_studio" / "resources" / "bmt_voice_studio.ico"
SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def fit_square(im: Image.Image, size: int) -> Image.Image:
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    fitted = im.copy()
    # Tiny sizes: crop to the denser center so BBNet stays readable.
    if size <= 24:
        w, h = fitted.size
        side = min(w, h)
        left = (w - side) // 2
        top = max(0, (h - side) // 2 - h // 20)
        fitted = fitted.crop((left, top, left + side, top + side))
    fitted.thumbnail((size, size), Image.Resampling.LANCZOS)
    x = (size - fitted.width) // 2
    y = (size - fitted.height) // 2
    canvas.paste(fitted, (x, y), fitted)
    return canvas


def _png_bytes(im: Image.Image) -> bytes:
    buf = BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def _bmp_dib_bytes(im: Image.Image) -> bytes:
    """32-bit ICO DIB: BITMAPINFOHEADER + BGRA XOR + 1-bit AND mask."""
    im = im.convert("RGBA")
    w, h = im.size
    flipped = im.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    raw = flipped.tobytes()
    bgra = bytearray()
    for i in range(0, len(raw), 4):
        r, g, b, a = raw[i : i + 4]
        bgra += bytes((b, g, r, a))
    row_and = ((w + 31) // 32) * 4
    and_mask = bytes(row_and * h)
    header = struct.pack("<IIIHHIIIIII", 40, w, h * 2, 1, 32, 0, len(bgra), 0, 0, 0, 0)
    return header + bytes(bgra) + and_mask


def write_ico(path: Path, images: list[Image.Image]) -> None:
    payloads: list[bytes] = []
    for im in images:
        if im.size[0] >= 256:
            payloads.append(_png_bytes(im))
        else:
            payloads.append(_bmp_dib_bytes(im))
    count = len(images)
    offset = 6 + 16 * count
    entries = bytearray()
    blob = bytearray()
    for im, payload in zip(images, payloads, strict=True):
        w, h = im.size
        entries += struct.pack(
            "<BBBBHHII",
            0 if w >= 256 else w,
            0 if h >= 256 else h,
            0,
            0,
            1,
            32,
            len(payload),
            offset,
        )
        blob += payload
        offset += len(payload)
    path.write_bytes(struct.pack("<HHH", 0, 1, count) + entries + blob)


def ico_sizes(path: Path) -> list[tuple[int, int]]:
    data = path.read_bytes()
    _reserved, itype, count = struct.unpack_from("<HHH", data)
    if itype != 1:
        raise ValueError(f"not an ICO: type={itype}")
    sizes: list[tuple[int, int]] = []
    for i in range(count):
        w, h = data[6 + i * 16], data[7 + i * 16]
        sizes.append((w or 256, h or 256))
    return sizes


def main() -> int:
    if not SOURCE.is_file():
        raise SystemExit(f"logo missing: {SOURCE}")
    src = Image.open(SOURCE).convert("RGBA")
    images = [fit_square(src, size) for size in SIZES]
    write_ico(DEST, images)
    found = ico_sizes(DEST)
    print("SOURCE", SOURCE, src.size, src.mode)
    print("ICO", DEST, DEST.stat().st_size)
    print("SIZES", found)
    if set(found) != {(s, s) for s in SIZES}:
        raise SystemExit(f"ICO sizes mismatch: {found}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
