"""Brand assets — BBNet logo and icons."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtWidgets import QLabel

from bmt_voice_studio.resources.windows_shell import (
    WINDOWS_APP_USER_MODEL_ID,
    apply_hwnd_and_class_icons,
    apply_window_relaunch_identity,
    apply_windows_app_user_model_id,
    load_taskbar_hicons,
    register_windows_shell_identity,
)

# Stable Windows taskbar / jump-list identity. Do not include a version number.
APP_ICON_FILE = "bmt_voice_studio.ico"
_APP_ICON_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)

# Language card flag files (real PNG icons — not emoji / regional letter codes).
LANGUAGE_FLAG_FILES = {
    "en": "flag_en.png",  # England (St George's Cross)
    "fr": "flag_fr.png",  # France
    "sw": "flag_sw.png",  # Congo / DRC (product target)
    "pt": "flag_pt.png",  # Portugal
}


def _resource_root_candidates() -> list[Path]:
    here = Path(__file__).resolve().parent
    roots = [here, here.parent.parent / "assets"]
    if getattr(sys, "frozen", False):
        meipass = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        roots.extend(
            [
                meipass / "bmt_voice_studio" / "resources",
                meipass / "resources",
                meipass,
                Path(sys.executable).parent / "_internal" / "bmt_voice_studio" / "resources",
                Path(sys.executable).parent / "_internal",
                Path(sys.executable).parent,
            ]
        )
    return roots


def _resource_candidates(filename: str = "bbnet_logo.png") -> list[Path]:
    return [root / filename for root in _resource_root_candidates()]


def _first_existing(filename: str) -> Path | None:
    for root in _resource_root_candidates():
        path = root / filename
        if path.exists():
            return path
    return None


def logo_path(product: str | None = None) -> Path | None:
    from bmt_voice_studio.config.product import HHR_LOGO_FILE, is_hhr

    names = [HHR_LOGO_FILE, "bbnet_logo.png"] if is_hhr(product) else ["bbnet_logo.png"]
    for name in names:
        for path in _resource_candidates(name):
            if path.exists():
                return path
    return None


def app_icon_path() -> Path | None:
    """Packaged-resource-safe Windows chrome icon (ICO), falling back to the PNG logo."""
    return _first_existing(APP_ICON_FILE) or logo_path()


def _frozen_exe_path() -> Path | None:
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable)
        if exe.suffix.lower() == ".exe" and exe.is_file():
            return exe
    return None


def prepare_windows_taskbar_identity() -> bool:
    """Register IconResource, then set AppUserModelID, before QApplication."""
    exe = _frozen_exe_path()
    ico = _first_existing(APP_ICON_FILE)
    register_windows_shell_identity(exe=exe, ico=ico)
    return apply_windows_app_user_model_id()


def apply_win32_hwnd_icon(widget) -> bool:
    """Bind BBNet into HWND + window-class HICON (what Windows 11 taskbar reads)."""
    if sys.platform != "win32" or widget is None:
        return False
    try:
        from bmt_voice_studio.resources.windows_shell import taskbar_variant

        if taskbar_variant() == "A":
            return False
        hwnd = int(widget.winId())
        if not hwnd:
            return False
        exe = _frozen_exe_path()
        ico = _first_existing(APP_ICON_FILE)
        png = logo_path()
        hbig, hsmall = load_taskbar_hicons(exe=exe, ico=ico, png=png)
        widget._win32_icon_handles = (hbig, hsmall)
        apply_hwnd_and_class_icons(hwnd, hbig, hsmall)
        # Relaunch icon must be the EXE resource, not a loose filesystem ICO.
        apply_window_relaunch_identity(hwnd, exe=exe, ico=None if exe else ico)
        return bool(hbig or hsmall)
    except Exception:
        return False


def flag_path(language_id: str) -> Path | None:
    filename = LANGUAGE_FLAG_FILES.get((language_id or "").lower())
    if not filename:
        return None
    for root in _resource_root_candidates():
        path = root / "flags" / filename
        if path.exists():
            return path
        path = root / filename
        if path.exists():
            return path
    return None


def load_logo_pixmap(
    max_width: int | None = None,
    max_height: int | None = None,
    product: str | None = None,
) -> QPixmap | None:
    path = logo_path(product)
    if not path:
        return None
    pix = QPixmap(str(path))
    if pix.isNull():
        return None
    if max_width or max_height:
        pix = pix.scaled(
            max_width or pix.width(),
            max_height or pix.height(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    return pix


def load_flag_pixmap(
    language_id: str,
    *,
    max_width: int = 40,
    max_height: int = 28,
) -> QPixmap | None:
    path = flag_path(language_id)
    if not path:
        return None
    pix = QPixmap(str(path))
    if pix.isNull():
        return None
    return pix.scaled(
        max_width,
        max_height,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


def _qpixmap_from_pil(frame) -> QPixmap | None:
    rgba = frame.convert("RGBA")
    qimg = QImage(
        rgba.tobytes("raw", "RGBA"),
        rgba.width,
        rgba.height,
        QImage.Format.Format_RGBA8888,
    ).copy()
    pix = QPixmap.fromImage(qimg)
    return None if pix.isNull() else pix


def _pixmaps_from_ico(path: Path) -> list[QPixmap]:
    """Decode ICO frames ourselves so frozen Qt does not depend on an ICO plugin."""
    try:
        from PIL.IcoImagePlugin import IcoFile
    except Exception:
        return []
    try:
        ico = IcoFile(path)
        pixmaps: list[QPixmap] = []
        for size in sorted(ico.sizes()):
            pix = _qpixmap_from_pil(ico.getimage(size))
            if pix is not None:
                pixmaps.append(pix)
        return pixmaps
    except Exception:
        return []


def load_app_icon() -> QIcon:
    """Build a QIcon with real pixmaps. QIcon(filename).isNull() is not enough on Windows."""
    icon = QIcon()
    ico = _first_existing(APP_ICON_FILE)
    if ico:
        for pix in _pixmaps_from_ico(ico):
            icon.addPixmap(pix)
        if icon.availableSizes():
            return icon
    path = logo_path()
    if not path:
        return icon
    pix = QPixmap(str(path))
    if pix.isNull():
        return icon
    for size in _APP_ICON_SIZES:
        icon.addPixmap(
            pix.scaled(
                size,
                size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
    return icon


def apply_logo_label(
    label: QLabel,
    *,
    max_width: int = 180,
    max_height: int = 120,
    product: str | None = None,
) -> None:
    from bmt_voice_studio.config.product import get_product, is_hhr

    pix = load_logo_pixmap(max_width=max_width, max_height=max_height, product=product)
    if pix:
        label.setPixmap(pix)
        label.setText("")
        profile = get_product(product)
        label.setToolTip(f"{profile.title} — {profile.tagline}")
        return
    label.setPixmap(QPixmap())
    label.setText("HHR" if is_hhr(product) else "BBNet")
    label.setObjectName("appTitle")


def logo_label(
    *,
    max_width: int = 180,
    max_height: int = 120,
    parent=None,
    product: str | None = None,
) -> QLabel:
    label = QLabel(parent)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setObjectName("brandLogo")
    label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    label.setStyleSheet("background: transparent; border: none;")
    apply_logo_label(label, max_width=max_width, max_height=max_height, product=product)
    return label
