"""Diagnostic Variant A: no explicit AppUserModelID."""

from __future__ import annotations

import os

os.environ["BMT_TASKBAR_VARIANT"] = "A"
os.environ["BMT_DISABLE_APP_USER_MODEL_ID"] = "1"
