# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller FINAL onedir for BMT Voice Studio 1.3.26. Never writes over 1.3.22."""

from PyInstaller.building.api import COLLECT, EXE, PYZ
from PyInstaller.building.build_main import Analysis
from PyInstaller.utils.hooks import collect_data_files

block_cipher = None

datas = [
    ("samples", "samples"),
    ("bmt_voice_studio/config/source_pipeline_presets.json", "bmt_voice_studio/config"),
    ("bmt_voice_studio/config/production_defaults.json", "bmt_voice_studio/config"),
    ("THIRD_PARTY_NOTICES.txt", "."),
    ("VERSION", "."),
    ("bmt_voice_studio/resources/bbnet_logo.png", "bmt_voice_studio/resources"),
    ("bmt_voice_studio/resources/bmt_voice_studio.ico", "bmt_voice_studio/resources"),
    ("bmt_voice_studio/resources/flags", "bmt_voice_studio/resources/flags"),
    ("assets/bbnet_logo.png", "."),
]
try:
    datas += collect_data_files("edge_tts")
except Exception:
    pass
try:
    datas += collect_data_files("imageio_ffmpeg")
except Exception:
    pass

hiddenimports = [
    "edge_tts",
    "httpx",
    "httpcore",
    "anyio",
    "h11",
    "certifi",
    "imageio_ffmpeg",
    "mutagen",
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtNetwork",
    "bmt_voice_studio.production_batch",
    "bmt_voice_studio.release_smoke",
    "bmt_voice_studio.release_scan",
    "bmt_voice_studio.daily",
    "bmt_voice_studio.daily.pipeline",
    "bmt_voice_studio.daily.message_date",
    "bmt_voice_studio.video",
    "bmt_voice_studio.video.ffmpeg_renderer",
    "bmt_voice_studio.video.branding_audio",
    "bmt_voice_studio.video.encode",
    "bmt_voice_studio.video.title_cards",
    "bmt_voice_studio.video.locked_card",
    "bmt_voice_studio.video.image_io",
    "bmt_voice_studio.video.thumbs",
    "bmt_voice_studio.video.packaged_smoke",
    "bmt_voice_studio.video.captions",
    "bmt_voice_studio.video.batch",
    "bmt_voice_studio.video.history",
    "bmt_voice_studio.video.live_crop",
    "bmt_voice_studio.video.size_estimate",
    "bmt_voice_studio.update",
    "bmt_voice_studio.update.channel",
    "bmt_voice_studio.net",
    "bmt_voice_studio.providers.voice_verify",
    "bmt_voice_studio.ui.dialogs.update",
    "bmt_voice_studio.config.data_root",
    "bmt_voice_studio.resources.windows_shell",
    "bmt_voice_studio.config.migrate_library",
    "bmt_voice_studio.ui.dialogs.data_library",
    "bmt_voice_studio.ui.widgets.logo_preview",
    "bmt_voice_studio.ui.widgets.caption_style_preview",
    "bmt_voice_studio.ui.widgets.music_pad_picker",
    "bmt_voice_studio.ui.widgets.job_progress",
    "bmt_voice_studio.ui.widgets.studio_timeline",
    "bmt_voice_studio.ui.studio_keys",
    "bmt_voice_studio.core.job_progress",
    "bmt_voice_studio.config.french_tts",
    "bmt_voice_studio.providers.edge_ssml",
    "PIL",
    "PIL.Image",
    "PIL.ImageDraw",
    "PIL.ImageFont",
    "PIL.ImageFilter",
    "PIL.ImageOps",
]

a = Analysis(
    ["bmt_voice_studio/app.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=["bmt_voice_studio/runtime_hooks/pyi_rth_bmt_appid.py"],
    excludes=[
        "PySide6.QtWebEngine",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebEngineQuick",
        "PySide6.Qt3DCore",
        "PySide6.Qt3DRender",
        "PySide6.QtCharts",
        "PySide6.QtDataVisualization",
        "tkinter",
        "matplotlib",
        "numpy",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="BMTVoiceStudio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon="bmt_voice_studio/resources/bmt_voice_studio.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="BMTVoiceStudio-1.3.26",
)
