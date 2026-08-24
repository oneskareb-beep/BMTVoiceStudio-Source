"""Windows application icon + AppUserModelID — chrome only, no product-logic changes."""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

from bmt_voice_studio.resources import (
    APP_ICON_FILE,
    WINDOWS_APP_USER_MODEL_ID,
    app_icon_path,
    logo_path,
)

ROOT = Path(__file__).resolve().parents[1]
ICO = ROOT / "bmt_voice_studio" / "resources" / APP_ICON_FILE
REQUIRED_SIZES = {(16, 16), (20, 20), (24, 24), (32, 32), (40, 40), (48, 48), (64, 64), (128, 128), (256, 256)}
PROTECTED_131_SHA256 = "1abd8500897136120cd610049b81210c7eae2ac5e3526995954166b4428dc9a2"


def _ico_sizes(path: Path) -> set[tuple[int, int]]:
    data = path.read_bytes()
    _reserved, itype, count = struct.unpack_from("<HHH", data)
    assert itype == 1
    sizes: set[tuple[int, int]] = set()
    for i in range(count):
        w, h = data[6 + i * 16], data[7 + i * 16]
        sizes.add((w or 256, h or 256))
    return sizes


def test_windows_ico_exists_with_required_sizes():
    assert ICO.is_file()
    assert _ico_sizes(ICO) == REQUIRED_SIZES


def test_app_icon_path_prefers_ico():
    path = app_icon_path()
    assert path is not None
    assert path.name == APP_ICON_FILE
    assert path.suffix.lower() == ".ico"


def test_ui_logo_path_still_png():
    path = logo_path()
    assert path is not None
    assert path.name == "bbnet_logo.png"


def test_app_user_model_id_is_stable_and_unversioned():
    assert WINDOWS_APP_USER_MODEL_ID == "BelieversBusinessmenNetwork.BMTVoiceStudio.App"
    assert "1.3" not in WINDOWS_APP_USER_MODEL_ID
    assert "1.3.1" not in WINDOWS_APP_USER_MODEL_ID


def test_final_spec_embeds_ico():
    spec = (ROOT / "BMTVoiceStudio-1.3.35.spec").read_text(encoding="utf-8")
    assert 'icon="bmt_voice_studio/resources/bmt_voice_studio.ico"' in spec
    assert "bmt_voice_studio/resources/bmt_voice_studio.ico" in spec
    assert "pyi_rth_bmt_appid.py" in spec


def test_pre_icon_release_zip_protected():
    from bmt_voice_studio.release_scan import sha256_file

    protected = ROOT / "release" / "_protected_1.3.1_pre_icon" / "BMTVoiceStudio-1.3.1-Windows-x64-Portable.zip"
    if not protected.is_file():
        pytest.skip("protected 1.3.1 pre-icon zip not present on this machine")
    assert sha256_file(protected) == PROTECTED_131_SHA256


def test_taskbar_hicons_from_packaged_ico():
    from bmt_voice_studio.resources.windows_shell import load_taskbar_hicons

    hbig, hsmall = load_taskbar_hicons(exe=None, ico=ICO, png=None)
    assert hbig
    assert hsmall


def test_load_app_icon_not_null():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    from bmt_voice_studio.resources import load_app_icon

    icon = load_app_icon()
    assert not icon.isNull()
    sizes = {tuple(sz.toTuple()) for sz in icon.availableSizes()}
    assert sizes, "QIcon must expose at least one pixmap size"
    _ = app
