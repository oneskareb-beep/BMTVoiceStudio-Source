"""Diagnostic Variant B: explicit AppUserModelID + relaunch icon on the EXE."""

from __future__ import annotations

import os
import sys

os.environ["BMT_TASKBAR_VARIANT"] = "B"
os.environ["BMT_APP_USER_MODEL_ID"] = "BelieversBusinessmenNetwork.BMTVoiceStudio.TaskbarTestB"

if sys.platform == "win32":
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            os.environ["BMT_APP_USER_MODEL_ID"]
        )
    except Exception:
        pass
