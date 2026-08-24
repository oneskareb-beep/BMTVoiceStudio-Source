"""PyInstaller runtime hook: set Windows AppUserModelID before Qt starts."""

from __future__ import annotations

import sys

if sys.platform == "win32":
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "BelieversBusinessmenNetwork.BMTVoiceStudio.App"
        )
    except Exception:
        pass
