"""Video Maker page — daily workflow, crop, preview, BMT CLASSIC + NATURE."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from PySide6.QtCore import QThreadPool, QTimer, Qt, Signal, QSize
from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSlider,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from bmt_voice_studio.config.settings import get_settings, remember_recent_path, save_settings
from bmt_voice_studio.daily.naming import display_date, freeze_devotional_date
from bmt_voice_studio.core.job_progress import batch_job_percent
from bmt_voice_studio.resources import logo_path as packaged_logo_path
from bmt_voice_studio.ui.theme import SPACE, set_badge_state
from bmt_voice_studio.ui.studio_keys import bind_shortcut
from bmt_voice_studio.ui.widgets.common import (
    card,
    ellipsize_path,
    icon_button,
    labeled_field,
    meta_label,
    show_error,
    status_badge,
    value_label,
    wrap_in_scroll,
)
from bmt_voice_studio.ui.widgets.logo_preview import LogoPreviewPicker
from bmt_voice_studio.ui.widgets.caption_style_preview import CaptionStylePreview
from bmt_voice_studio.ui.widgets.music_pad_picker import MusicPadPicker
from bmt_voice_studio.ui.widgets.studio_timeline import SEG_INTRO, SEG_MEDIA, SEG_OUTRO, StudioTimeline
from bmt_voice_studio.ui.widgets.video_media_widget import VideoMediaStrip
from bmt_voice_studio.ui.widgets.video_preview_player import VideoPreviewPlayer
from bmt_voice_studio.video.bundled_media import (
    BUNDLED_CLIP_COUNT,
    default_media_items,
    media_uses_template_defaults,
    merge_saved_layout,
)
from bmt_voice_studio.video.captions import CAPTION_ALL, CAPTION_BODY, CAPTION_BODY_VERSE
from bmt_voice_studio.video.batch import (
    batch_completion_summary,
    build_queue,
    cancel_pending,
    failed_languages,
    filter_selected_ready,
    isolate_failure,
    projects_for_batch,
    retry_failed,
)
from bmt_voice_studio.video.encode import RENDER_SPEED_FASTER, RENDER_SPEED_STANDARD
from bmt_voice_studio.video.composition import build_composition_plan, parse_timecode, validate_project_for_render
from bmt_voice_studio.video.discovery import (
    format_duration,
    language_label,
    language_tracks_for_day,
    metadata_for_language,
    todays_audio_status,
)
from bmt_voice_studio.video.errors import MediaValidationError, VideoMakerError
from bmt_voice_studio.video.geometry import ZOOM_MAX, ZOOM_MIN, clamp_crop, clamp_trim, clamp_zoom
from bmt_voice_studio.video.history import load_video_history, upsert_video_entry
from bmt_voice_studio.video.image_io import pad_rgb_for_template, suggest_smart_frame, zoom_toward_point
from bmt_voice_studio.video.live_crop import click_offset_to_crop, drag_delta_to_crop, render_live_crop_still
from bmt_voice_studio.video.media_probe import probe_audio_duration, probe_media
from bmt_voice_studio.video.models import (
    LANGUAGE_LABELS,
    PROFILE_STANDARD,
    PROFILE_WHATSAPP,
    QUEUE_COMPLETE,
    QUEUE_FAILED,
    QUEUE_PREPARING,
    QUEUE_RENDERING,
    QUEUE_WAITING,
    TEMPLATE_BMT_CLASSIC,
    TEMPLATE_BMT_MINIMAL,
    TEMPLATE_BMT_NATURE,
    TEMPLATE_LABELS,
    BrandingToggles,
    FitMode,
    LanguageTrack,
    TextStyle,
    VideoProject,
    language_still_code,
    output_profile_for,
)
from bmt_voice_studio.video.paths import video_output_path, video_project_dir, video_temp_root
from bmt_voice_studio.video.project_store import load_project, load_project_for, save_project
from bmt_voice_studio.video.size_estimate import estimate_project_mb
from bmt_voice_studio.video.title_cards import render_preview_still, render_template_chip
from bmt_voice_studio.workers.video_render import VideoRenderSignals, VideoRenderWorker

MEDIA_DIALOG_FILTER = (
    "PNG images (*.png);;"
    "JPEG images (*.jpg *.jpeg);;"
    "Photos including transparent (*.png *.webp *.gif *.tif *.tiff *.bmp);;"
    "Videos (*.mp4 *.mov *.m4v *.avi *.mkv);;"
    "All media (*.png *.jpg *.jpeg *.webp *.gif *.bmp *.tif *.tiff *.mp4 *.mov *.m4v *.avi *.mkv);;"
    "All files (*.*)"
)
LOGO_DIALOG_FILTER = "PNG with transparency (*.png);;Images (*.png *.webp *.gif *.jpg *.jpeg);;All files (*.*)"


class VideoMakerPage(QWidget):
    status_message = Signal(str)
    job_progress = Signal(int, str)
    job_busy = Signal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._busy = False
        self._preview_job = False
        self._worker: VideoRenderWorker | None = None
        self._signals = VideoRenderSignals()
        self._last_output = ""
        self._last_preview = ""
        self._suppress = False
        self._daily_page = None
        self._preview_path: Path | None = None
        self._template_id = TEMPLATE_BMT_CLASSIC
        self._audio_path = ""
        self._audio_duration = 0.0
        self._tracks: list[LanguageTrack] = []
        self._queue = []
        self._queue_index = -1
        self._batch_projects: list[VideoProject] = []
        self._batch_errors: list[tuple[str, str, str]] = []
        self._crop_undo: list[tuple[int, float, float, float]] = []
        self._crop_undoing = False
        self._crop_drag_armed = True
        self._crop_drag_idle = QTimer(self)
        self._crop_drag_idle.setSingleShot(True)
        self._crop_drag_idle.setInterval(450)
        self._crop_drag_idle.timeout.connect(lambda: setattr(self, "_crop_drag_armed", True))
        self._build()
        self._wire()
        QTimer.singleShot(250, self._restore)

    def bind_daily_page(self, page) -> None:
        self._daily_page = page

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header_bar = QWidget()
        header = QHBoxLayout(header_bar)
        header.setContentsMargins(SPACE.page_margin, SPACE.sm, SPACE.page_margin, SPACE.sm)
        header.setSpacing(SPACE.md)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        title = QLabel("Video")
        title.setObjectName("pageTitle")
        subtitle = QLabel("Preview in the center · bin on the left · inspector on the right")
        subtitle.setObjectName("appSubtitle")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        header.addLayout(titles, 1)
        self.btn_generate = QPushButton("Generate selected videos")
        self.btn_generate.setObjectName("primaryButton")
        self.btn_generate.setMinimumHeight(40)
        self.btn_generate.setMaximumHeight(42)
        self.btn_generate.setToolTip("Generate portrait videos for the selected languages · Ctrl+Enter")
        header.addWidget(self.btn_generate)
        header_bar.setObjectName("pageHeader")
        header_bar.setAutoFillBackground(True)
        outer.addWidget(header_bar)

        today_hdr, today_l = card("Today's video", "")
        top_meta = QHBoxLayout()
        self.lbl_today_date = value_label("—")
        self.lbl_today_lang = value_label("—")
        self.lbl_today_lang.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        top_meta.addWidget(self.lbl_today_date, 1)
        top_meta.addWidget(self.lbl_today_lang, 1)
        today_l.addLayout(top_meta)
        self.lbl_today_topic = QLabel("—")
        self.lbl_today_topic.setObjectName("topicValue")
        self.lbl_today_topic.setWordWrap(True)
        today_l.addWidget(self.lbl_today_topic)
        today_l.addWidget(meta_label("Audio"))
        self.lbl_today_audio = value_label("—")
        today_l.addWidget(self.lbl_today_audio)
        today_l.addWidget(meta_label("Duration"))
        self.lbl_today_dur = value_label("—")
        today_l.addWidget(self.lbl_today_dur)

        audio_card, audio_l = card("Audio / language", "Use Daily Audio already produced for this date.")
        self._audio_rows: dict[str, dict] = {}
        audio_grid = QGridLayout()
        audio_grid.setContentsMargins(0, 0, 0, 0)
        audio_grid.setSpacing(4)
        for i, (lang_id, label) in enumerate(LANGUAGE_LABELS.items()):
            row_frame = QFrame()
            row_frame.setObjectName("audioRow")
            row = QHBoxLayout(row_frame)
            row.setContentsMargins(4, 2, 2, 2)
            row.setSpacing(4)
            name = QLabel(lang_id.upper())
            name.setObjectName("valueLabel")
            name.setToolTip(label)
            name.setMinimumWidth(0)
            status = status_badge("None", "waiting")
            status.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
            file_lbl = QLabel("")
            file_lbl.setObjectName("metaLabel")
            file_lbl.hide()
            dur_lbl = QLabel("")
            dur_lbl.setObjectName("metaLabel")
            dur_lbl.hide()
            use_btn = icon_button(f"Use {label} Daily Audio", "play")
            use_btn.setEnabled(False)
            use_btn.clicked.connect(lambda _=False, lid=lang_id: self.use_todays_audio(lid))
            row.addWidget(name)
            row.addWidget(status, 1)
            row.addWidget(use_btn)
            audio_grid.addWidget(row_frame, i // 2, i % 2)
            self._audio_rows[lang_id] = {
                "status": status,
                "file": file_lbl,
                "dur": dur_lbl,
                "use": use_btn,
                "frame": row_frame,
            }
        audio_l.addLayout(audio_grid)
        ext_row = QHBoxLayout()
        ext_row.setContentsMargins(0, 0, 0, 0)
        ext_row.setSpacing(4)
        self.btn_external = icon_button("Choose external audio", "open")
        ext_hint = QLabel("External audio")
        ext_hint.setObjectName("metaLabel")
        ext_hint.setMinimumWidth(0)
        ext_row.addWidget(self.btn_external)
        ext_row.addWidget(ext_hint, 1)
        audio_l.addLayout(ext_row)

        langs, langs_l = card("Languages", "One visual project, each language's Daily Audio.")
        # Rebuild title row with compact Select all ready action.
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        # card() already added a title label; replace last title widget's sibling row:
        self.btn_select_ready = QPushButton("Select all ready")
        self.btn_select_ready.setObjectName("tertiaryButton")
        self.btn_select_ready.setToolTip("Select every language that has ready Daily Audio")
        title_row.addStretch(1)
        title_row.addWidget(self.btn_select_ready)
        langs_l.insertLayout(1, title_row)
        self._lang_checks: dict[str, QCheckBox] = {}
        self._lang_meta_lbl: dict[str, QLabel] = {}
        for lang_id, label in LANGUAGE_LABELS.items():
            row = QHBoxLayout()
            chk = QCheckBox(label)
            chk.setEnabled(False)
            meta = QLabel("Not generated")
            meta.setObjectName("appSubtitle")
            row.addWidget(chk)
            row.addWidget(meta, 1)
            langs_l.addLayout(row)
            self._lang_checks[lang_id] = chk
            self._lang_meta_lbl[lang_id] = meta
            chk.toggled.connect(self._on_lang_toggles)

        meta, meta_l = card("Metadata", "Filled from today's audio. Editing here does not change the source script.")
        self.lbl_date = QLabel("—")
        self.cmb_language = QComboBox()
        for lid, label in LANGUAGE_LABELS.items():
            self.cmb_language.addItem(label, lid)
        row1 = QHBoxLayout()
        row1.addWidget(labeled_field("Date", self.lbl_date), 1)
        row1.addWidget(labeled_field("Language", self.cmb_language), 1)
        meta_l.addLayout(row1)
        self.ed_topic = QLineEdit()
        self.ed_topic.setPlaceholderText("Topic")
        self.ed_title = QLineEdit()
        self.ed_title.setPlaceholderText("Devotional title")
        meta_l.addWidget(labeled_field("Topic", self.ed_topic))
        meta_l.addWidget(labeled_field("Title", self.ed_title))
        meta_row = QHBoxLayout()
        self.ed_week = QLineEdit()
        self.ed_week.setPlaceholderText("Week focus")
        self.ed_month = QLineEdit()
        self.ed_month.setPlaceholderText("Month theme")
        meta_row.addWidget(labeled_field("Week Focus", self.ed_week), 1)
        meta_row.addWidget(labeled_field("Month Theme", self.ed_month), 1)
        meta_l.addLayout(meta_row)
        self.ed_verse = QLineEdit()
        self.ed_verse.setPlaceholderText("Memory verse")
        meta_l.addWidget(labeled_field("Memory Verse", self.ed_verse))

        media_card, media_l = card(
            "Media",
            f"{BUNDLED_CLIP_COUNT} bundled 16:9 clips per template — ready by default. "
            "Use Paysage for meditation landscape stills (middle 2/4). Reorder here; replace in Preferences.",
        )
        self.media = VideoMediaStrip()
        self.media.set_locked_defaults(True)
        media_l.addWidget(self.media)
        self.btn_paysage = QPushButton("Paysage (meditation)")
        self.btn_paysage.setToolTip(
            "Load eng/fra/port meditation landscape stills in the middle 2/4 of the frame "
            "(1/4 empty top + 1/4 empty bottom)."
        )
        self.btn_paysage.setObjectName("secondaryButton")
        media_l.addWidget(self.btn_paysage)

        crop, crop_l = card("Media position", "Drag the preview to reframe. Scroll to zoom. Click a point to center it.")
        self.btn_fill = icon_button("Fill — cover the 9:16 frame", "fill", checkable=True)
        self.btn_fit = icon_button("Fit — show the whole photo with letterbox", "fit", checkable=True)
        self.btn_band = icon_button(
            "Band — middle 2/4 (1/4 top + 1/4 bottom empty) for paysage stills",
            "fit",
            checkable=True,
        )
        self.btn_smart = icon_button("Smart Frame — auto fill with a slight zoom", "smart")
        self.btn_fill.setChecked(True)
        self._fit_group = QButtonGroup(self)
        self._fit_group.setExclusive(True)
        self._fit_group.addButton(self.btn_fill)
        self._fit_group.addButton(self.btn_fit)
        self._fit_group.addButton(self.btn_band)
        self.btn_up = icon_button("Up", "up")
        self.btn_down = icon_button("Down", "down")
        self.btn_nudge_left = icon_button("Left", "left")
        self.btn_nudge_right = icon_button("Right", "right")
        self.btn_reset_crop = icon_button("Reset", "reset")
        tools = QHBoxLayout()
        tools.setContentsMargins(0, 0, 0, 0)
        tools.setSpacing(2)
        for b in (
            self.btn_fill,
            self.btn_fit,
            self.btn_band,
            self.btn_smart,
            self.btn_up,
            self.btn_down,
            self.btn_nudge_left,
            self.btn_nudge_right,
            self.btn_reset_crop,
        ):
            tools.addWidget(b)
        tools.addStretch(1)
        crop_l.addLayout(tools)
        self.sld_pos_x = QSlider(Qt.Orientation.Horizontal)
        self.sld_pos_y = QSlider(Qt.Orientation.Horizontal)
        for sld in (self.sld_pos_x, self.sld_pos_y):
            sld.setRange(-100, 100)
            sld.setValue(0)
        crop_l.addWidget(labeled_field("Horizontal", self.sld_pos_x))
        crop_l.addWidget(labeled_field("Vertical", self.sld_pos_y))
        zoom_row = QHBoxLayout()
        zoom_row.setSpacing(4)
        zoom_row.addWidget(meta_label("ZOOM"))
        self.btn_zoom_out = icon_button("Zoom out", "zoom_out")
        self.btn_zoom_in = icon_button("Zoom in", "zoom_in")
        self.sld_zoom = QSlider(Qt.Orientation.Horizontal)
        self.sld_zoom.setRange(int(round(ZOOM_MIN * 100)), int(round(ZOOM_MAX * 100)))
        self.sld_zoom.setValue(100)
        self.sld_zoom.setPageStep(5)
        self.sld_zoom.setSingleStep(1)
        self.sld_zoom.setToolTip(
            "Zoom out until a landscape clip sits fully in 9:16. 100% fills the frame. "
            "Scroll the preview to zoom toward the pointer."
        )
        self.lbl_zoom = QLabel("100%")
        zoom_row.addWidget(self.btn_zoom_out)
        zoom_row.addWidget(self.sld_zoom, 1)
        zoom_row.addWidget(self.btn_zoom_in)
        zoom_row.addWidget(self.lbl_zoom)
        crop_l.addLayout(zoom_row)
        self.chk_overlay = QCheckBox("Overlay transparent image on clips under it")
        self.chk_overlay.setToolTip("Detected PNG/GIF transparency is placed over the photo or video under it.")
        self.chk_overlay.setMinimumWidth(0)
        crop_l.addWidget(self.chk_overlay)
        trim_row = QHBoxLayout()
        self.sp_trim_start = QDoubleSpinBox()
        self.sp_trim_end = QDoubleSpinBox()
        for sp in (self.sp_trim_start, self.sp_trim_end):
            sp.setRange(0.0, 3600.0)
            sp.setDecimals(2)
            sp.setSuffix(" s")
        trim_row.addWidget(labeled_field("Start Trim", self.sp_trim_start), 1)
        trim_row.addWidget(labeled_field("End Trim", self.sp_trim_end), 1)
        self.sld_trim_start = QSlider(Qt.Orientation.Horizontal)
        self.sld_trim_end = QSlider(Qt.Orientation.Horizontal)
        self.sld_trim_start.setRange(0, 1000)
        self.sld_trim_end.setRange(0, 1000)
        self.lbl_trim = QLabel("Start: 00:00   End: 00:00   Duration: 00:00")
        self.lbl_trim.setObjectName("appSubtitle")
        self.lbl_trim.setWordWrap(True)
        self.lbl_trim.setMinimumWidth(0)
        crop_l.addWidget(self.sld_trim_start)
        crop_l.addWidget(self.sld_trim_end)
        crop_l.addWidget(self.lbl_trim)
        crop_l.addLayout(trim_row)
        self._crop_card = crop

        tmpl, tmpl_l = card("Template", "Changing template keeps media and metadata.")
        chips = QHBoxLayout()
        chips.setContentsMargins(0, 0, 0, 0)
        chips.setSpacing(6)
        self.btn_classic = self._template_chip("CLASSIC", TEMPLATE_BMT_CLASSIC, "Warm classic titles")
        self.btn_nature = self._template_chip("NATURE", TEMPLATE_BMT_NATURE, "Outdoor atmosphere")
        self.btn_minimal = self._template_chip("MINIMAL", TEMPLATE_BMT_MINIMAL, "Clean and quiet")
        for b in (self.btn_classic, self.btn_nature, self.btn_minimal):
            chips.addWidget(b)
        chips.addStretch(1)
        tmpl_l.addLayout(chips)
        self.btn_classic.setChecked(True)
        self.lbl_template = QLabel("Selected: BMT CLASSIC")
        self.lbl_template.setObjectName("taskLabel")
        self.lbl_template.setWordWrap(True)
        tmpl_l.addWidget(self.lbl_template)

        brand, brand_l = card("Branding", "")
        self.chk_logo = QCheckBox("Logo")
        self.chk_date = QCheckBox("Date")
        self.chk_topic = QCheckBox("Topic")
        self.chk_week = QCheckBox("Week Focus")
        self.chk_month = QCheckBox("Month Theme")
        self.chk_lt_topic = QCheckBox("Show Topic")
        self.chk_lt_date = QCheckBox("Show Date")
        for chk in (
            self.chk_logo,
            self.chk_date,
            self.chk_topic,
            self.chk_week,
            self.chk_month,
            self.chk_lt_topic,
            self.chk_lt_date,
        ):
            chk.setChecked(True)
        for chk in (self.chk_logo, self.chk_date, self.chk_topic, self.chk_week, self.chk_month):
            brand_l.addWidget(chk)
        brand_l.addWidget(QLabel("BMT CLEAN LOWER THIRD"))
        brand_l.addWidget(self.chk_lt_topic)
        brand_l.addWidget(self.chk_lt_date)
        self.chk_captions = QCheckBox("Show Captions")
        self.chk_captions.setChecked(False)
        brand_l.addWidget(QLabel("Captions: BMT CLEAN CAPTIONS"))
        brand_l.addWidget(self.chk_captions)
        self.cmb_caption_content = QComboBox()
        self.cmb_caption_content.addItem("Body Only", CAPTION_BODY)
        self.cmb_caption_content.addItem("Body + Memory Verse", CAPTION_BODY_VERSE)
        self.cmb_caption_content.addItem("All Spoken Content", CAPTION_ALL)
        self.cmb_caption_content.setCurrentIndex(1)
        brand_l.addWidget(labeled_field("Caption Content", self.cmb_caption_content))
        self.logo_picker = LogoPreviewPicker()
        brand_l.addWidget(self.logo_picker)
        self.cmb_recent_logos = QComboBox()
        self.cmb_recent_logos.setPlaceholderText("Recent logos")
        self.cmb_recent_logos.setToolTip("Jump back to a logo used recently")
        brand_l.addWidget(self.cmb_recent_logos)
        brand_l.addWidget(QLabel("Branded intro / outro"))
        self.chk_intro = QCheckBox("Branded intro — 10 sec")
        self.chk_outro = QCheckBox("Branded outro — 10 sec")
        self.chk_intro.setChecked(True)
        self.chk_outro.setChecked(True)
        brand_l.addWidget(self.chk_intro)
        brand_l.addWidget(self.chk_outro)
        self.music_picker = MusicPadPicker()
        brand_l.addWidget(self.music_picker)
        self.cmb_recent_music = QComboBox()
        self.cmb_recent_music.setPlaceholderText("Recent music")
        self.cmb_recent_music.setToolTip("Jump back to music used recently")
        brand_l.addWidget(self.cmb_recent_music)
        self._music_path = ""

        typography, typo_l = card(
            "Text & captions",
            "Two sentences at a time, timed to the voice. Soft orange letters with a dark blue outline.",
        )
        self.caption_style = CaptionStylePreview()
        settings = get_settings()
        self.caption_style.set_style(
            TextStyle(
                font_size=int(getattr(settings, "caption_font_size", 64) or 64),
                text_color=str(getattr(settings, "caption_text_color", "#E89430") or "#E89430"),
                stroke_color=str(getattr(settings, "caption_stroke_color", "#0A204A") or "#0A204A"),
                stroke_width=int(getattr(settings, "caption_stroke_width", 5) or 5),
            )
        )
        typo_l.addWidget(self.caption_style)
        self._text_card = typography

        compose, compose_l = card("Composition", "")
        compose_l.addWidget(meta_label("Status"))
        self.lbl_compose = QLabel("Ready")
        self.lbl_compose.setObjectName("valueLabel")
        self.lbl_compose.setWordWrap(True)
        compose_l.addWidget(self.lbl_compose)
        self.btn_compose = QPushButton("Auto compose")
        self.btn_compose.setObjectName("secondaryButton")
        compose_l.addWidget(self.btn_compose)
        compose.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)

        preview, preview_l = card(
            "Preview",
            "Drag to reframe. Scroll to zoom.",
        )
        self.preview_player = VideoPreviewPlayer()
        self.preview = self.preview_player.still
        self.lbl_preview_state = self.preview_player.lbl_state
        preview_l.addWidget(self.preview_player)
        self.timeline = StudioTimeline()
        preview_l.addWidget(self.timeline)
        self.btn_preview = QPushButton("Quick preview")
        self.btn_preview.setObjectName("secondaryButton")
        self.btn_preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_play_preview = self.preview_player.btn_system
        preview_l.addWidget(self.btn_preview)
        self.ed_preview_start = QLineEdit("00:00")
        self.ed_preview_start.setPlaceholderText("mm:ss")
        self.sp_preview_dur = QDoubleSpinBox()
        self.sp_preview_dur.setRange(8.0, 20.0)
        self.sp_preview_dur.setValue(12.0)
        self.sp_preview_dur.setSuffix(" s")
        preview_l.addWidget(labeled_field("Start", self.ed_preview_start))
        preview_l.addWidget(labeled_field("Duration", self.sp_preview_dur))
        self.btn_custom_preview = QPushButton("Custom preview")
        self.btn_custom_preview.setObjectName("tertiaryButton")
        self.btn_custom_preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        preview_l.addWidget(self.btn_custom_preview)

        queue_card, queue_l = card("Render progress", "One language at a time")
        self.lbl_queue = QLabel("Waiting")
        self.lbl_queue.setWordWrap(True)
        self.lbl_queue.setObjectName("appSubtitle")
        queue_l.addWidget(self.lbl_queue)
        self.btn_retry_failed = QPushButton("Retry Failed")
        self.btn_retry_failed.setObjectName("tertiaryButton")
        self.btn_retry_failed.setEnabled(False)
        queue_l.addWidget(self.btn_retry_failed)
        self.lbl_batch_summary = QLabel("")
        self.lbl_batch_summary.setWordWrap(True)
        self.lbl_batch_summary.setObjectName("taskLabel")
        queue_l.addWidget(self.lbl_batch_summary)
        self._summary_btns: dict[str, QPushButton] = {}
        self.summary_btns_host = QWidget()
        self.summary_btns_l = QVBoxLayout(self.summary_btns_host)
        self.summary_btns_l.setContentsMargins(0, 0, 0, 0)
        queue_l.addWidget(self.summary_btns_host)

        # Collapsible history (session state in self._history_expanded)
        self._history_expanded = False
        self._history_paths: list[str] = []
        hist_bar = QFrame()
        hist_bar.setObjectName("histCollapseBar")
        hist_bar_l = QHBoxLayout(hist_bar)
        hist_bar_l.setContentsMargins(14, 8, 14, 8)
        hist_bar_l.setSpacing(10)
        self.lbl_hist_title = QLabel("Video history")
        self.lbl_hist_title.setObjectName("cardTitle")
        self.lbl_hist_count = QLabel("0")
        self.lbl_hist_count.setObjectName("metaLabel")
        self.btn_hist_toggle = QPushButton("Expand")
        self.btn_hist_toggle.setObjectName("tertiaryButton")
        hist_bar_l.addWidget(self.lbl_hist_title)
        hist_bar_l.addWidget(self.lbl_hist_count)
        hist_bar_l.addStretch(1)
        hist_bar_l.addWidget(self.btn_hist_toggle)

        hist_body = QWidget()
        hist_l = QVBoxLayout(hist_body)
        hist_l.setContentsMargins(0, SPACE.sm, 0, 0)
        hist_l.setSpacing(SPACE.sm)
        self.tbl_history = QTableWidget(0, 8)
        self.tbl_history.setHorizontalHeaderLabels(
            ["Date", "Language", "Template", "Quality", "Duration", "Size", "Status", "Output"]
        )
        self.tbl_history.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tbl_history.setAlternatingRowColors(True)
        self.tbl_history.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl_history.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tbl_history.verticalHeader().setVisible(False)
        self.tbl_history.setShowGrid(False)
        self.tbl_history.setMaximumHeight(220)
        hist_l.addWidget(self.tbl_history)
        hist_btns = QHBoxLayout()
        self.btn_open_hist = QPushButton("Open video")
        self.btn_open_hist_folder = QPushButton("Open folder")
        for b in (self.btn_open_hist, self.btn_open_hist_folder):
            b.setObjectName("tertiaryButton")
            hist_btns.addWidget(b)
        hist_btns.addStretch(1)
        hist_l.addLayout(hist_btns)
        hist_body.hide()
        self._hist_bar = hist_bar
        self._hist_body = hist_body

        output, output_l = card("Output", "")
        self.cmb_quality = QComboBox()
        self.cmb_quality.addItem("Standard 1080p", PROFILE_STANDARD)
        self.cmb_quality.addItem("WhatsApp Optimized", PROFILE_WHATSAPP)
        output_l.addWidget(labeled_field("Quality", self.cmb_quality))
        self.cmb_render_speed = QComboBox()
        self.cmb_render_speed.addItem("Standard", RENDER_SPEED_STANDARD)
        self.cmb_render_speed.addItem("Faster", RENDER_SPEED_FASTER)
        self.cmb_render_speed.setToolTip("Faster may reduce encode quality slightly")
        output_l.addWidget(labeled_field("Render Speed", self.cmb_render_speed))
        output_l.addWidget(meta_label("Estimated size"))
        self.lbl_size = value_label("—")
        output_l.addWidget(self.lbl_size)
        output_l.addWidget(meta_label("Output Folder"))
        self.lbl_out_path = value_label("Saved under Documents when generated.")
        self.lbl_out_path.setToolTip("Full path appears here after generation")
        output_l.addWidget(self.lbl_out_path)
        self.lbl_stage = QLabel("Waiting")
        self.lbl_stage.setObjectName("taskLabel")
        self.lbl_stage.setWordWrap(True)
        output_l.addWidget(self.lbl_stage)
        self.progress = QProgressBar()
        self.progress.setValue(0)
        self.progress.setRange(0, 100)
        self.progress.setFormat("%p%")
        self.progress.setTextVisible(True)
        output_l.addWidget(self.progress)
        btns = QHBoxLayout()
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setObjectName("dangerButton")
        self.btn_cancel.setEnabled(False)
        self.btn_open = QPushButton("Open folder")
        self.btn_open.setObjectName("secondaryButton")
        self.btn_open.setToolTip("Open the video output folder")
        self.btn_open_video = QPushButton("Open video")
        self.btn_open_video.setObjectName("secondaryButton")
        self.btn_open_video.setToolTip("Open the last generated video file")
        self.btn_open_video.setEnabled(False)
        btns.addWidget(self.btn_cancel)
        btns.addWidget(self.btn_open)
        output_l.addLayout(btns)
        output_l.addWidget(self.btn_open_video)

        left = QWidget()
        left.setMinimumWidth(0)
        left_l = QVBoxLayout(left)
        left_l.setContentsMargins(0, 0, 0, 0)
        left_l.setSpacing(SPACE.md)
        left_l.addWidget(today_hdr)
        left_l.addWidget(audio_card)
        left_l.addWidget(langs)
        left_l.addWidget(media_card)
        left_l.addWidget(meta)

        center = QWidget()
        center.setMinimumWidth(0)
        center_l = QVBoxLayout(center)
        center_l.setContentsMargins(0, 0, 0, 0)
        center_l.setSpacing(SPACE.md)
        center_l.addWidget(preview)
        center_l.addStretch(1)

        right = QWidget()
        right.setMinimumWidth(0)
        right_l = QVBoxLayout(right)
        right_l.setContentsMargins(0, 0, 8, 0)
        right_l.setSpacing(SPACE.md)
        right_l.addWidget(crop)
        right_l.addWidget(tmpl)
        right_l.addWidget(brand)
        right_l.addWidget(self._text_card)
        right_l.addWidget(compose)
        right_l.addWidget(queue_card)
        right_l.addWidget(output)
        right_l.addStretch(1)

        split = QHBoxLayout()
        split.setContentsMargins(SPACE.page_margin, SPACE.md, SPACE.page_margin, SPACE.sm)
        split.setSpacing(SPACE.column_gutter)
        left_scroll = wrap_in_scroll(left)
        left_scroll.setMinimumWidth(200)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        center_scroll = wrap_in_scroll(center)
        center_scroll.setMinimumWidth(220)
        center_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        right_scroll = wrap_in_scroll(right)
        right_scroll.setMinimumWidth(240)
        right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        split.addWidget(left_scroll, 2)
        split.addWidget(center_scroll, 3)
        split.addWidget(right_scroll, 2)
        content = QWidget()
        content.setLayout(split)
        outer.addWidget(content, 1)

        hist_wrap = QWidget()
        hist_wrap_l = QVBoxLayout(hist_wrap)
        hist_wrap_l.setContentsMargins(SPACE.page_margin, 0, SPACE.page_margin, SPACE.md)
        hist_wrap_l.setSpacing(SPACE.xs)
        hist_wrap_l.addWidget(hist_bar)
        hist_wrap_l.addWidget(hist_body)
        outer.addWidget(hist_wrap)

    def _wire(self) -> None:
        self.cmb_language.currentIndexChanged.connect(self._on_language)
        self.btn_external.clicked.connect(self._choose_external_audio)
        self.btn_select_ready.clicked.connect(self._select_all_ready)
        self.media.request_add.connect(self._add_media)
        self.media.request_replace.connect(self._replace_media)
        self.media.changed.connect(self._on_changed)
        self.media.selected_changed.connect(self._load_crop_panel)
        self.media.files_dropped.connect(self._add_media_paths)
        self.logo_picker.choose_requested.connect(self._choose_logo)
        self.logo_picker.packaged_requested.connect(self._use_packaged_logo)
        self.music_picker.choose_requested.connect(self._choose_music)
        self.music_picker.changed.connect(self._on_changed)
        self.cmb_recent_logos.currentIndexChanged.connect(self._on_recent_logo)
        self.cmb_recent_music.currentIndexChanged.connect(self._on_recent_music)
        self.timeline.segment_clicked.connect(self._on_timeline_segment)
        self.chk_intro.toggled.connect(self._on_intro_outro_toggled)
        self.chk_outro.toggled.connect(self._on_intro_outro_toggled)
        self.btn_compose.clicked.connect(self._auto_compose)
        self.btn_preview.clicked.connect(self._preview_video)
        self.btn_custom_preview.clicked.connect(self._custom_preview)
        self.preview_player.fallback_requested.connect(self._open_path)
        self.preview_player.crop_dragged.connect(self._on_crop_drag)
        self.preview_player.crop_clicked.connect(self._on_crop_click)
        self.preview_player.zoom_wheeled.connect(self._on_preview_zoom)
        self.preview_player.media_index_dropped.connect(self._on_media_dropped_on_preview)
        self.preview_player.files_dropped.connect(self._add_media_paths)
        self.btn_play_preview.clicked.connect(self._play_preview)
        self.btn_generate.clicked.connect(self.generate)
        self.btn_cancel.clicked.connect(self._cancel)
        self.btn_open.clicked.connect(self._open_output)
        self.btn_open_video.clicked.connect(self._open_last_video)
        self.btn_retry_failed.clicked.connect(self._retry_failed)
        self.btn_open_hist.clicked.connect(self._open_hist_file)
        self.btn_open_hist_folder.clicked.connect(self._open_hist_folder)
        self.btn_hist_toggle.clicked.connect(self._toggle_history)
        self.btn_classic.clicked.connect(lambda: self._set_template(TEMPLATE_BMT_CLASSIC))
        self.btn_nature.clicked.connect(lambda: self._set_template(TEMPLATE_BMT_NATURE))
        self.btn_minimal.clicked.connect(lambda: self._set_template(TEMPLATE_BMT_MINIMAL))
        self.btn_fill.clicked.connect(lambda: self._set_fit(FitMode.FILL.value))
        self.btn_fit.clicked.connect(lambda: self._set_fit(FitMode.FIT.value))
        self.btn_band.clicked.connect(lambda: self._set_fit(FitMode.BAND.value))
        self.btn_paysage.clicked.connect(self._use_meditation_paysage)
        self.btn_smart.clicked.connect(self._smart_frame)
        self.btn_up.clicked.connect(lambda: self._nudge(0, -0.06))
        self.btn_down.clicked.connect(lambda: self._nudge(0, 0.06))
        self.btn_nudge_left.clicked.connect(lambda: self._nudge(-0.06, 0))
        self.btn_nudge_right.clicked.connect(lambda: self._nudge(0.06, 0))
        self.btn_reset_crop.clicked.connect(self._reset_crop)
        self.sld_zoom.valueChanged.connect(self._on_zoom_live)
        self.sld_pos_x.sliderPressed.connect(self._push_crop_undo)
        self.sld_pos_y.sliderPressed.connect(self._push_crop_undo)
        self.sld_zoom.sliderPressed.connect(self._push_crop_undo)
        self.sld_zoom.sliderReleased.connect(self._on_zoom_commit)
        self.btn_zoom_in.clicked.connect(lambda: self._nudge_zoom(5))
        self.btn_zoom_out.clicked.connect(lambda: self._nudge_zoom(-5))
        self.sld_pos_x.valueChanged.connect(self._on_pos_sliders)
        self.sld_pos_y.valueChanged.connect(self._on_pos_sliders)
        self.chk_overlay.toggled.connect(self._on_overlay_toggled)
        self.sp_trim_start.valueChanged.connect(self._on_trim)
        self.sp_trim_end.valueChanged.connect(self._on_trim)
        self.sld_trim_start.sliderReleased.connect(self._on_trim_sliders)
        self.sld_trim_end.sliderReleased.connect(self._on_trim_sliders)
        self.cmb_quality.currentIndexChanged.connect(self._on_changed)
        self.cmb_render_speed.currentIndexChanged.connect(self._on_changed)
        self.cmb_caption_content.currentIndexChanged.connect(self._on_changed)
        self.caption_style.changed.connect(self._on_text_style_changed)
        for w in (
            self.ed_topic,
            self.ed_week,
            self.ed_month,
            self.ed_title,
            self.ed_verse,
            self.chk_logo,
            self.chk_date,
            self.chk_topic,
            self.chk_week,
            self.chk_month,
            self.chk_lt_topic,
            self.chk_lt_date,
        ):
            if hasattr(w, "textChanged"):
                w.textChanged.connect(self._on_changed)
            if hasattr(w, "toggled"):
                w.toggled.connect(self._on_changed)
        self.chk_captions.toggled.connect(self._on_changed)
        self._signals.progress.connect(self._on_progress)
        self._signals.language_progress.connect(self._on_lang_progress)
        self._signals.finished.connect(self._on_done)
        self._signals.error.connect(self._on_error)
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(900)
        self._save_timer.timeout.connect(self._autosave)
        bind_shortcut(self, "Ctrl+Return", self.generate)
        bind_shortcut(self, "Ctrl+Enter", self.generate)
        bind_shortcut(self, "Space", self._space_play_preview, idle_only=True)
        bind_shortcut(self, "Ctrl+Z", self._undo_crop, idle_only=True)
        self._populate_recent_combos()

    def current_date(self) -> date:
        if self._daily_page is not None and hasattr(self._daily_page, "selected_date"):
            try:
                return freeze_devotional_date(self._daily_page.selected_date())
            except Exception:
                pass
        return date.today()

    def _language_id(self) -> str:
        return str(self.cmb_language.currentData() or "en")

    def _logo_path(self) -> str:
        settings = get_settings()
        if settings.video_logo_path and Path(settings.video_logo_path).is_file():
            return settings.video_logo_path
        packaged = packaged_logo_path()
        return str(packaged) if packaged else ""

    def collect_project(self) -> VideoProject:
        audio = self._selected_audio_path()
        duration = self._audio_duration
        if audio and Path(audio).is_file() and duration <= 0.4:
            try:
                duration = probe_audio_duration(audio)
            except Exception:
                duration = 0.0
        d = self.current_date()
        profile = output_profile_for(str(self.cmb_quality.currentData() or PROFILE_STANDARD))
        selected = [lid for lid, chk in self._lang_checks.items() if chk.isChecked()]
        if not selected:
            selected = [self._language_id()]
        current = self._language_id()
        for track in self._tracks:
            if track.language == current:
                track.audio_path = audio
                track.audio_duration = duration
                track.topic = self.ed_topic.text().strip()
                track.week_focus = self.ed_week.text().strip()
                track.month_theme = self.ed_month.text().strip()
                track.title = self.ed_title.text().strip()
                track.memory_verse = self.ed_verse.text().strip()
                track.ready = bool(audio and Path(audio).is_file())
                track.metadata_complete = bool(track.topic)
                track.selected = True
            track.selected = track.language in selected
        project = VideoProject(
            devotional_date=d.isoformat(),
            language=self._language_id(),
            audio_path=audio,
            audio_duration=duration,
            topic=self.ed_topic.text().strip(),
            week_focus=self.ed_week.text().strip(),
            month_theme=self.ed_month.text().strip(),
            title=self.ed_title.text().strip(),
            memory_verse=self.ed_verse.text().strip(),
            logo_path=self._logo_path(),
            media_items=self.media.items(),
            template_id=self._template_id,
            output_profile=profile,
            languages=list(self._tracks),
            selected_languages=selected,
            show_captions=self.chk_captions.isChecked(),
            skip_caption_header=str(self.cmb_caption_content.currentData() or CAPTION_BODY_VERSE) != CAPTION_ALL,
            caption_content=str(self.cmb_caption_content.currentData() or CAPTION_BODY_VERSE),
            text_style=self.caption_style.style(),
            render_speed=str(self.cmb_render_speed.currentData() or RENDER_SPEED_STANDARD),
            preview_start=self._parse_preview_start(),
            preview_duration=float(self.sp_preview_dur.value()),
            intro_enabled=self.chk_intro.isChecked(),
            outro_enabled=self.chk_outro.isChecked(),
            intro_duration=10.0 if self.chk_intro.isChecked() else 0.0,
            outro_duration=10.0 if self.chk_outro.isChecked() else 0.0,
            music_path=str(self.music_picker.music_path() or getattr(self, "_music_path", "") or ""),
            music_intro_start=float(self.music_picker.intro_start()),
            music_outro_start=float(self.music_picker.outro_start()),
            branding=BrandingToggles(
                logo=self.chk_logo.isChecked(),
                date=self.chk_date.isChecked(),
                topic=self.chk_topic.isChecked(),
                week_focus=self.chk_week.isChecked(),
                month_theme=self.chk_month.isChecked(),
                lower_third_topic=self.chk_lt_topic.isChecked(),
                lower_third_date=self.chk_lt_date.isChecked(),
                captions=self.chk_captions.isChecked(),
            ),
        )
        # Sylvestre: FR/PT topic + date must appear on the locked card like English.
        if not project.topic.strip():
            self._load_metadata(project.language, overwrite=True)
            project.topic = self.ed_topic.text().strip()
            project.week_focus = self.ed_week.text().strip() or project.week_focus
            project.month_theme = self.ed_month.text().strip() or project.month_theme
            project.title = self.ed_title.text().strip() or project.title
            project.memory_verse = self.ed_verse.text().strip() or project.memory_verse
        from bmt_voice_studio.video.branding_audio import resolve_music_path

        soft = resolve_music_path(project.music_path)
        if soft is not None:
            project.music_path = str(soft)
        project.ensure_tracks()
        return project

    def _selected_audio_path(self) -> str:
        return str(getattr(self, "_audio_path", "") or "")

    def apply_project(self, project: VideoProject) -> None:
        self._suppress = True
        try:
            idx = self.cmb_language.findData(project.language)
            if idx >= 0:
                self.cmb_language.setCurrentIndex(idx)
            self.ed_topic.setText(project.topic)
            self.ed_week.setText(project.week_focus)
            self.ed_month.setText(project.month_theme)
            self.ed_title.setText(project.title)
            self.ed_verse.setText(project.memory_verse)
            # Backfill empty FR/PT/EN topics from today's script so branding matches English.
            if not (project.topic or "").strip():
                self._load_metadata(project.language or self._language_id(), overwrite=False)
            self.chk_logo.setChecked(project.branding.logo)
            self.chk_date.setChecked(project.branding.date)
            self.chk_topic.setChecked(project.branding.topic)
            self.chk_week.setChecked(project.branding.week_focus)
            self.chk_month.setChecked(project.branding.month_theme)
            self.chk_lt_topic.setChecked(project.branding.lower_third_topic)
            self.chk_lt_date.setChecked(project.branding.lower_third_date)
            self.chk_captions.setChecked(bool(project.show_captions or project.branding.captions))
            self.chk_intro.setChecked(bool(getattr(project, "intro_enabled", True)))
            self.chk_outro.setChecked(bool(getattr(project, "outro_enabled", True)))
            self._music_path = str(getattr(project, "music_path", "") or "")
            self.music_picker.set_music(
                self._music_path,
                intro_start=float(getattr(project, "music_intro_start", 0.0) or 0.0),
                outro_start=float(getattr(project, "music_outro_start", -1.0)),
                intro_enabled=self.chk_intro.isChecked(),
                outro_enabled=self.chk_outro.isChecked(),
            )
            self.logo_picker.set_logo_path(self._logo_path())
            skip = bool(getattr(project, "skip_caption_header", True))
            mode = str(getattr(project, "caption_content", "") or "")
            if not mode:
                mode = CAPTION_ALL if not skip else CAPTION_BODY_VERSE
            si = self.cmb_caption_content.findData(mode)
            if si < 0:
                si = 1 if skip else 2
            self.cmb_caption_content.setCurrentIndex(si)
            self.caption_style.set_style(getattr(project, "text_style", None))
            rs = self.cmb_render_speed.findData(getattr(project, "render_speed", RENDER_SPEED_STANDARD) or RENDER_SPEED_STANDARD)
            if rs >= 0:
                self.cmb_render_speed.setCurrentIndex(rs)
            self._set_template(project.template_id, persist=False)
            qidx = self.cmb_quality.findData(project.output_profile.id)
            if qidx >= 0:
                self.cmb_quality.setCurrentIndex(qidx)
            self.media.set_items(project.media_items)
            self._ensure_default_media(force_layout=bool(project.media_items))
            self._audio_path = project.audio_path
            self._audio_duration = float(project.audio_duration or 0.0)
            self._refresh_date_label()
            self._refresh_todays_audio()
            selected = [str(x).lower() for x in (project.selected_languages or []) if str(x).strip()]
            if selected:
                for lid, chk in self._lang_checks.items():
                    chk.blockSignals(True)
                    chk.setChecked(lid in selected)
                    chk.blockSignals(False)
            if getattr(project, "languages", None):
                self._tracks = list(project.languages)
            self._refresh_header()
            self._load_crop_panel()
            self._sync_generate_label()
            if not (getattr(project, "music_path", "") or "").strip() or not Path(
                getattr(project, "music_path", "") or ""
            ).is_file():
                self._ensure_default_music()
        finally:
            self._suppress = False

    def _restore(self) -> None:
        d = self.current_date()
        slot = load_project_for(d.isoformat(), self._language_id())
        if slot is None:
            last = load_project()
            if last.devotional_date == d.isoformat() and last.language == self._language_id():
                slot = last
        if slot and (slot.audio_path or slot.media_items or slot.topic):
            self.apply_project(slot)
            self._refresh_todays_audio()
            if not slot.audio_path:
                self.use_todays_audio(self._language_id())
            return
        self._refresh_date_label()
        self._refresh_todays_audio()
        self.use_todays_audio(self._language_id())
        self.logo_picker.set_logo_path(self._logo_path())
        self._ensure_default_media()
        self._ensure_default_music()

    def _ensure_default_music(self) -> None:
        """Sylvestre soft bed is the default when no music file is selected."""
        from bmt_voice_studio.video.branding_audio import resolve_music_path

        current = getattr(self, "_music_path", "") or ""
        if current and Path(current).is_file():
            return
        soft = resolve_music_path(None)
        if soft is None:
            return
        self._music_path = str(soft)
        self.music_picker.set_music(
            self._music_path,
            intro_start=0.0,
            outro_start=-1.0,
            intro_enabled=self.chk_intro.isChecked(),
            outro_enabled=self.chk_outro.isChecked(),
        )

    def _ensure_default_media(self, *, force_layout: bool = False) -> None:
        """Load five bundled clips for the active template (merge saved crop if provided)."""
        tid = getattr(self, "_template_id", TEMPLATE_BMT_CLASSIC)
        current = self.media.items()
        if force_layout and current:
            items = merge_saved_layout(current, tid)
        elif not current or not media_uses_template_defaults(current, tid):
            if current and not media_uses_template_defaults(current, tid):
                items = merge_saved_layout(current, tid)
            else:
                items = default_media_items(tid)
        else:
            items = current
        if items:
            self.media.set_items(items)
        self.media.set_locked_defaults(True)

    def _refresh_date_label(self) -> None:
        self.lbl_date.setText(display_date(self.current_date()))

    def _refresh_todays_audio(self) -> None:
        rows = todays_audio_status(self.current_date())
        for row in rows:
            widgets = self._audio_rows.get(row["language"])
            if not widgets:
                continue
            status_text = str(row["status"] or "Not generated")
            state = "ready" if row["ready"] else ("missing" if "missing" in status_text.lower() else "waiting")
            widgets["status"].setText("Ready" if row["ready"] else "None")
            widgets["status"].setToolTip(status_text)
            set_badge_state(widgets["status"], state)
            if row["ready"]:
                widgets["file"].setText(str(row["name"] or ""))
                widgets["file"].setToolTip(str(row.get("path") or row["name"] or ""))
                widgets["dur"].setText(row["duration_label"] if row["duration_label"] != "—" else "")
                widgets["use"].setEnabled(True)
            else:
                widgets["file"].setText("")
                widgets["file"].setToolTip("")
                widgets["dur"].setText("")
                widgets["use"].setEnabled(False)
        self._tracks = language_tracks_for_day(self.current_date())
        for track in self._tracks:
            chk = self._lang_checks.get(track.language)
            lbl = self._lang_meta_lbl.get(track.language)
            if chk is None:
                continue
            chk.setEnabled(track.ready)
            if not track.ready:
                if lbl:
                    lbl.setText("None")
                continue
            if lbl:
                lbl.setText("Ready" if track.metadata_complete else "Metadata incomplete")
            if track.language == self._language_id() and not chk.isChecked():
                chk.blockSignals(True)
                chk.setChecked(True)
                chk.blockSignals(False)
        self._sync_generate_label()
        self._refresh_history_table()
        self._mark_audio_selected(self._language_id())

    def _refresh_header(self) -> None:
        d = self.current_date()
        self.lbl_today_date.setText(display_date(d))
        self.lbl_today_lang.setText(language_label(self._language_id()))
        audio = self._selected_audio_path()
        name = Path(audio).name if audio else "—"
        self.lbl_today_audio.setText(name)
        self.lbl_today_audio.setToolTip(str(audio) if audio else "")
        dur = self._audio_duration
        if (not dur) and audio and Path(audio).is_file():
            try:
                dur = probe_audio_duration(audio)
                self._audio_duration = dur
            except Exception:
                dur = 0.0
        self.lbl_today_dur.setText(format_duration(dur))
        topic = self.ed_topic.text().strip() or "—"
        self.lbl_today_topic.setText(topic)
        self._refresh_output_hint()
        self._refresh_timeline()

    def _on_language(self) -> None:
        if self._suppress:
            return
        slot = load_project_for(self.current_date().isoformat(), self._language_id())
        if slot and (slot.audio_path or slot.media_items):
            self.apply_project(slot)
            # Always refresh topic/week/month for FR/PT like English when fields are empty.
            if not self.ed_topic.text().strip():
                self._load_metadata(self._language_id(), overwrite=True)
            self._on_changed()
            return
        self.use_todays_audio(self._language_id())
        self._on_changed()

    def _use_meditation_paysage(self) -> None:
        """Sylvestre: person-in-landscape stills, middle 2/4, eng/fra/port by language."""
        from bmt_voice_studio.video.meditation_paysage import default_paysage_items

        items = default_paysage_items(self._language_id())
        if not items:
            show_error(self, "Paysage", "Meditation paysage stills were not found in the app resources.")
            return
        self.media.set_locked_defaults(False)
        self.media.set_items(items)
        self.btn_band.setChecked(True)
        self._load_crop_panel()
        self._refresh_timeline()
        self.status_message.emit(
            f"Paysage loaded ({language_still_code(self._language_id())}) — middle 2/4 band"
        )
        self._on_changed()

    def _load_metadata(self, language: str, *, overwrite: bool = True) -> None:
        d = self.current_date()
        live = ""
        page = self._daily_page
        if page is not None:
            mapping = {"en": "en_edit", "fr": "fr_edit", "sw": "sw_edit", "pt": "pt_edit"}
            edit = getattr(page, mapping.get(language, "en_edit"), None)
            if edit is not None:
                live = edit.toPlainText()
        meta = metadata_for_language(d, language, live_text=live)
        if overwrite or not self.ed_topic.text().strip():
            if meta.get("topic"):
                self.ed_topic.setText(meta["topic"])
        if overwrite or not self.ed_week.text().strip():
            if meta.get("week_focus"):
                self.ed_week.setText(meta["week_focus"])
        if overwrite or not self.ed_month.text().strip():
            if meta.get("month_theme"):
                self.ed_month.setText(meta["month_theme"])
        if overwrite or not self.ed_title.text().strip():
            if meta.get("title"):
                self.ed_title.setText(meta["title"])
        if overwrite or not self.ed_verse.text().strip():
            if meta.get("memory_verse"):
                self.ed_verse.setText(meta["memory_verse"])

    def use_todays_audio(self, language: str | None = None) -> None:
        lang = (language or self._language_id()).strip().lower()
        idx = self.cmb_language.findData(lang)
        if idx >= 0 and self.cmb_language.currentIndex() != idx:
            self._suppress = True
            self.cmb_language.setCurrentIndex(idx)
            self._suppress = False
        self._refresh_todays_audio()
        rows = {r["language"]: r for r in todays_audio_status(self.current_date())}
        row = rows.get(lang) or {}
        if row.get("ready") and row.get("path"):
            self._audio_path = str(row["path"])
            try:
                self._audio_duration = float(row.get("duration") or 0.0) or probe_audio_duration(self._audio_path)
            except Exception:
                self._audio_duration = 0.0
            self._load_metadata(lang, overwrite=True)
            self.status_message.emit(f"Using {language_label(lang)} audio")
        else:
            self.status_message.emit("No generated audio for this language yet")
        self._refresh_header()
        self._mark_audio_selected(lang)
        self._on_changed()

    def _mark_audio_selected(self, language: str) -> None:
        lang = (language or "").strip().lower()
        for lid, widgets in self._audio_rows.items():
            frame = widgets.get("frame")
            if frame is None:
                continue
            frame.setProperty("selected", "true" if lid == lang else "false")
            frame.style().unpolish(frame)
            frame.style().polish(frame)

    def _template_chip(self, short: str, template_id: str, hint: str) -> QToolButton:
        btn = QToolButton()
        btn.setObjectName("templateChip")
        btn.setCheckable(True)
        btn.setAutoRaise(False)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        btn.setText(short)
        btn.setToolTip(f"{TEMPLATE_LABELS.get(template_id, short)} — {hint}")
        try:
            frame = render_template_chip(template_id)
            data = frame.convert("RGBA").tobytes("raw", "RGBA")
            qimg = QImage(data, frame.width, frame.height, QImage.Format.Format_RGBA8888)
            btn.setIcon(QIcon(QPixmap.fromImage(qimg.copy())))
        except Exception:
            pass
        btn.setIconSize(QSize(40, 72))
        btn.setFixedSize(68, 112)
        return btn

    def _choose_external_audio(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose External Audio",
            str(Path.home()),
            "Audio (*.mp3 *.wav)",
        )
        if not path:
            return
        try:
            self._audio_duration = probe_audio_duration(path)
        except MediaValidationError as exc:
            show_error(self, "Audio", exc.message)
            return
        self._audio_path = path
        self._refresh_header()
        self._on_changed()

    def _set_template(self, template_id: str, persist: bool = True) -> None:
        tid = template_id if template_id in TEMPLATE_LABELS else TEMPLATE_BMT_CLASSIC
        previous = getattr(self, "_template_id", TEMPLATE_BMT_CLASSIC)
        self._template_id = tid
        self.btn_classic.setChecked(tid == TEMPLATE_BMT_CLASSIC)
        self.btn_nature.setChecked(tid == TEMPLATE_BMT_NATURE)
        if hasattr(self, "btn_minimal"):
            self.btn_minimal.setChecked(tid == TEMPLATE_BMT_MINIMAL)
        self.lbl_template.setText(f"Selected: {TEMPLATE_LABELS.get(tid, 'BMT CLASSIC')}")
        if tid != previous and (
            not self.media.items() or media_uses_template_defaults(self.media.items(), previous)
        ):
            self.media.set_items(default_media_items(tid))
            self._load_crop_panel()
        if persist and not self._suppress:
            self._on_changed()

    def _add_media_blocked(self) -> None:
        show_error(
            self,
            "Media",
            "Video clips are bundled with each template.",
            "Open Preferences → Default video clips to replace a bundled clip.",
        )

    def _add_media(self) -> None:
        self._add_media_blocked()

    def _add_media_paths(self, paths) -> None:
        if paths:
            self._add_media_blocked()

    def _replace_media(self, index: int) -> None:
        self._add_media_blocked()

    def _choose_logo(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose Logo",
            str(Path.home()),
            LOGO_DIALOG_FILTER,
        )
        if not path:
            return
        settings = get_settings()
        settings.video_logo_path = path
        save_settings(settings)
        remember_recent_path("video_recent_logos", path)
        self.logo_picker.set_logo_path(path)
        self._populate_recent_combos()
        self._on_changed()

    def _use_packaged_logo(self) -> None:
        settings = get_settings()
        settings.video_logo_path = ""
        save_settings(settings)
        packaged = packaged_logo_path()
        self.logo_picker.set_logo_path(str(packaged) if packaged else "")
        self._on_changed()

    def _refresh_music_label(self) -> None:
        self.music_picker.set_music(
            getattr(self, "_music_path", "") or "",
            intro_start=self.music_picker.intro_start(),
            outro_start=self.music_picker.outro_start(),
            intro_enabled=self.chk_intro.isChecked(),
            outro_enabled=self.chk_outro.isChecked(),
        )

    def _on_intro_outro_toggled(self) -> None:
        self.music_picker.set_pads_enabled(self.chk_intro.isChecked(), self.chk_outro.isChecked())
        self._on_changed()

    def _choose_music(self) -> None:
        start = str(Path(self._music_path).parent) if self._music_path else str(Path.home())
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose Intro / Outro Music",
            start,
            "Audio (*.mp3 *.wav *.m4a)",
        )
        if not path:
            return
        self._music_path = path
        remember_recent_path("video_recent_music", path)
        self.music_picker.set_music(
            path,
            intro_enabled=self.chk_intro.isChecked(),
            outro_enabled=self.chk_outro.isChecked(),
            reset_windows=True,
        )
        self._populate_recent_combos()
        self._on_changed()

    def _load_crop_panel(self) -> None:
        item = self.media.selected_item()
        self._suppress = True
        try:
            enabled = item is not None
            for w in (
                self.btn_fill,
                self.btn_fit,
                self.btn_band,
                self.btn_smart,
                self.btn_up,
                self.btn_down,
                self.btn_nudge_left,
                self.btn_nudge_right,
                self.btn_reset_crop,
                self.sld_zoom,
                self.btn_zoom_in,
                self.btn_zoom_out,
                self.sld_pos_x,
                self.sld_pos_y,
                self.chk_overlay,
                self.sp_trim_start,
                self.sp_trim_end,
                self.sld_trim_start,
                self.sld_trim_end,
            ):
                w.setEnabled(enabled)
            if not item:
                return
            mode = (item.fit_mode or FitMode.FILL.value).lower()
            self.btn_fill.setChecked(mode == FitMode.FILL.value or mode == FitMode.AUTO.value)
            self.btn_fit.setChecked(mode == FitMode.FIT.value)
            self.btn_band.setChecked(mode == FitMode.BAND.value)
            if mode not in {FitMode.FIT.value, FitMode.BAND.value}:
                self.btn_fill.setChecked(True)
            self.sld_zoom.setValue(int(round(clamp_zoom(item.zoom) * 100)))
            self.lbl_zoom.setText(f"{self.sld_zoom.value()}%")
            cx, cy = clamp_crop(item.crop_x, item.crop_y)
            self.sld_pos_x.setValue(int(round(cx * 100)))
            self.sld_pos_y.setValue(int(round(cy * 100)))
            self.chk_overlay.setChecked(bool(getattr(item, "overlay", False)))
            start, end = clamp_trim(item.trim_start, item.trim_end, item.duration)
            self.sp_trim_start.setValue(start)
            self.sp_trim_end.setValue(end)
            video = item.media_type == "video"
            self.sp_trim_start.setEnabled(video)
            self.sp_trim_end.setEnabled(video)
            self.sld_trim_start.setEnabled(video)
            self.sld_trim_end.setEnabled(video)
            self._sync_trim_sliders(item)
        finally:
            self._suppress = False
            self._refresh_live_crop()

    def _set_fit(self, mode: str) -> None:
        if self._suppress:
            return
        self._push_crop_undo()
        self.media.update_selected(fit_mode=mode)
        self._refresh_live_crop()

    def _nudge(self, dx: float, dy: float) -> None:
        item = self.media.selected_item()
        if not item:
            return
        self._push_crop_undo()
        mods = QApplication.keyboardModifiers()
        scale = 0.3 if mods & Qt.KeyboardModifier.ShiftModifier else 1.0
        cx, cy = clamp_crop(item.crop_x + dx * scale, item.crop_y + dy * scale)
        self.media.update_selected(crop_x=cx, crop_y=cy)
        self._sync_pos_sliders(cx, cy)
        self._refresh_live_crop()

    def _reset_crop(self) -> None:
        self._push_crop_undo()
        self.sld_zoom.setValue(100)
        self.media.update_selected(crop_x=0.0, crop_y=0.0, zoom=1.0, trim_start=0.0, trim_end=0.0)
        self._load_crop_panel()

    def _smart_frame(self) -> None:
        item = self.media.selected_item()
        if not item:
            return
        self._push_crop_undo()
        mode, zoom, cx, cy = suggest_smart_frame(item.width, item.height)
        self.media.update_selected(fit_mode=mode, zoom=zoom, crop_x=cx, crop_y=cy)
        self._load_crop_panel()

    def _on_overlay_toggled(self, checked: bool) -> None:
        if self._suppress:
            return
        self.media.update_selected(overlay=bool(checked))

    def _on_media_dropped_on_preview(self, index: int) -> None:
        self.media.select_index(index)
        item = self.media.selected_item()
        if item and item.media_type == "image" and not getattr(item, "overlay", False):
            self._smart_frame()
        else:
            self._load_crop_panel()
        self.preview_player.show_still()

    def _nudge_zoom(self, delta_pct: int) -> None:
        self.sld_zoom.setValue(self.sld_zoom.value() + int(delta_pct))
        self._on_zoom_commit()

    def _on_zoom_live(self, value: int) -> None:
        self.lbl_zoom.setText(f"{int(value)}%")
        if self._suppress:
            return
        self.media.update_selected(zoom=clamp_zoom(value / 100.0))
        self._refresh_live_crop()

    def _on_zoom_commit(self) -> None:
        if self._suppress:
            return
        self.media.update_selected(zoom=clamp_zoom(self.sld_zoom.value() / 100.0))
        self._refresh_live_crop()

    def _on_pos_sliders(self) -> None:
        if self._suppress:
            return
        cx, cy = clamp_crop(self.sld_pos_x.value() / 100.0, self.sld_pos_y.value() / 100.0)
        self.media.update_selected(crop_x=cx, crop_y=cy)
        self._refresh_live_crop()

    def _sync_pos_sliders(self, cx: float, cy: float) -> None:
        self._suppress = True
        try:
            self.sld_pos_x.setValue(int(round(cx * 100)))
            self.sld_pos_y.setValue(int(round(cy * 100)))
        finally:
            self._suppress = False

    def _on_trim(self) -> None:
        if self._suppress:
            return
        item = self.media.selected_item()
        if not item:
            return
        start, end = clamp_trim(self.sp_trim_start.value(), self.sp_trim_end.value(), item.duration)
        self.media.update_selected(trim_start=start, trim_end=end)
        self._sync_trim_sliders(item)

    def _on_trim_sliders(self) -> None:
        if self._suppress:
            return
        item = self.media.selected_item()
        if not item or item.duration <= 0:
            return
        dur = float(item.duration)
        start = (self.sld_trim_start.value() / 1000.0) * dur
        end = (self.sld_trim_end.value() / 1000.0) * dur
        if end >= dur - 0.04:
            end = 0.0
        start, end = clamp_trim(start, end, dur)
        self._suppress = True
        try:
            self.sp_trim_start.setValue(start)
            self.sp_trim_end.setValue(end)
        finally:
            self._suppress = False
        self.media.update_selected(trim_start=start, trim_end=end)
        self._sync_trim_labels(start, end, dur)

    def _auto_compose(self) -> None:
        project = self.collect_project()
        try:
            validate_project_for_render(project)
            plan = build_composition_plan(project, job_id="preview")
            n = len(plan.scenes)
            self.lbl_compose.setText(
                f"{n} scenes · intro {plan.intro_duration:.1f}s · "
                f"crossfade {plan.crossfade_seconds:.2f}s · "
                f"master audio {plan.audio_duration:.1f}s"
            )
            self.status_message.emit("Timeline composed")
        except VideoMakerError as exc:
            self.lbl_compose.setText(exc.message)
            show_error(self, "Auto Compose", exc.message)

    def _still_preview(self) -> None:
        project = self.collect_project()
        from bmt_voice_studio.config.paths import cache_dir

        dest = cache_dir() / "video_preview_frame.png"
        media = ""
        item = self.media.selected_item()
        if item and item.exists():
            if item.media_type == "image":
                media = item.path
            elif item.media_type == "video":
                from bmt_voice_studio.video.thumbs import extract_thumbnail

                thumb = extract_thumbnail(
                    item.path,
                    media_type=item.media_type,
                    rotation=int(getattr(item, "rotation", 0) or 0),
                    square=False,
                )
                if thumb:
                    media = str(thumb)
        try:
            render_preview_still(project, dest, media_path=media)
            pix = QPixmap(str(dest))
            if not pix.isNull():
                self.preview_player.set_still(pix)
            self._preview_path = dest
            self._refresh_live_crop()
        except Exception:
            self._refresh_live_crop()

    def _preview_video(self) -> None:
        if self._busy:
            return
        project = self.collect_project()
        try:
            validate_project_for_render(project)
        except VideoMakerError as exc:
            show_error(self, "Preview", exc.message)
            return
        self._still_preview()
        self._busy = True
        self._preview_job = True
        self.music_picker.stop_preview()
        self.job_busy.emit(True)
        self.job_progress.emit(0, "Rendering 12-second preview…")
        self.btn_generate.setEnabled(False)
        self.btn_preview.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.progress.setValue(0)
        self.lbl_stage.setText("Preparing")
        self.lbl_preview_state.setText("Rendering 12-second preview…")
        self._worker = VideoRenderWorker(
            project,
            self._signals,
            preview=True,
            preview_start=self._parse_preview_start(),
        )
        QThreadPool.globalInstance().start(self._worker)

    def _custom_preview(self) -> None:
        self._preview_video()

    def _play_preview(self) -> None:
        path = self._last_preview
        if path and Path(path).is_file():
            os.startfile(path)  # noqa: S606
            return
        show_error(self, "Preview", "Generate a 12-second preview first.")

    def generate(self) -> None:
        if self._busy:
            return
        project = self.collect_project()
        from bmt_voice_studio.video.branding_audio import default_soft_music_path, resolve_music_path

        # Sylvestre: soft bed always under the video when intro/outro branding is on.
        if project.intro_enabled or project.outro_enabled:
            resolved = resolve_music_path(project.music_path)
            if resolved is not None:
                project.music_path = str(resolved)
                self._music_path = str(resolved)
                self.music_picker.set_music(
                    self._music_path,
                    intro_start=float(getattr(project, "music_intro_start", 0.0) or 0.0),
                    outro_start=float(getattr(project, "music_outro_start", -1.0)),
                    intro_enabled=project.intro_enabled,
                    outro_enabled=project.outro_enabled,
                )
            elif not (project.music_path and Path(project.music_path).is_file()):
                soft = default_soft_music_path()
                self.status_message.emit(
                    "Intro/outro music is missing. Branding will render silently."
                    if soft is None
                    else "Using packaged soft background music."
                )
                self._refresh_music_label()
        ready = [t.language for t in self._tracks if t.ready]
        selected = filter_selected_ready(project.selected_languages, ready) or [project.language]
        if any(not t.ready for t in self._tracks if t.language in selected):
            show_error(self, "Generate Video", "A selected language has no generated Daily Audio.")
            return
        incomplete = [t for t in self._tracks if t.language in selected and not t.metadata_complete]
        if incomplete:
            names = ", ".join(language_label(t.language) for t in incomplete)
            self.status_message.emit(f"Metadata incomplete: {names}")
        self._batch_projects = projects_for_batch(project, selected)
        self._batch_errors = []
        if not self._batch_projects:
            try:
                validate_project_for_render(project)
            except VideoMakerError as exc:
                show_error(self, "Generate Video", exc.message)
                return
            self._batch_projects = [project]
        for p in self._batch_projects:
            try:
                validate_project_for_render(p)
            except VideoMakerError as exc:
                show_error(self, "Generate Video", f"{language_label(p.language)}: {exc.message}")
                return
        self._queue = build_queue([p.language for p in self._batch_projects], [p.language for p in self._batch_projects])
        self._queue_index = 0
        self._busy = True
        self._preview_job = False
        self.music_picker.stop_preview()
        self.job_busy.emit(True)
        self.job_progress.emit(0, "Preparing video…")
        self.btn_generate.setEnabled(False)
        self.btn_preview.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self._refresh_queue_label()
        self._start_queue_item()

    def _cancel(self) -> None:
        if self._worker:
            self._worker.cancel()
        self._queue = cancel_pending(self._queue)
        self.lbl_stage.setText("Cancelling...")
        self._refresh_queue_label()

    def _on_progress(self, pct: int, msg: str) -> None:
        piece = max(0, min(100, int(pct)))
        text = msg or "Working…"
        if self._preview_job:
            overall = piece
        else:
            n = max(1, len(self._batch_projects) or 1)
            overall = batch_job_percent(self._queue_index, n, piece)
            if 0 <= self._queue_index < len(self._batch_projects):
                text = f"{language_label(self._batch_projects[self._queue_index].language)} · {text}"
        self.progress.setValue(overall)
        hint = text if len(text) <= 40 else text[:37] + "…"
        self.progress.setFormat(f"{overall}%  {hint}")
        self.lbl_stage.setText(f"{text}  {overall}%")
        self.job_progress.emit(overall, text)
        self.status_message.emit(text)

    def _finish_job_strip(self, message: str, *, ok: bool = True) -> None:
        self.job_progress.emit(100 if ok else self.progress.value(), message)
        self.job_busy.emit(False)

    def _on_done(self, result: object) -> None:
        self.progress.setValue(100)
        payload = result if isinstance(result, dict) else {}
        out = str(payload.get("output") or "")
        if payload.get("preview"):
            self._busy = False
            self.btn_generate.setEnabled(True)
            self.btn_preview.setEnabled(True)
            self.btn_cancel.setEnabled(False)
            self._last_preview = out
            self.lbl_stage.setText("Preview ready")
            self.lbl_preview_state.setText("Preview ready — 12 seconds")
            self.btn_play_preview.setEnabled(bool(out and Path(out).is_file()))
            if out:
                self.preview_player.load(out)
            self.status_message.emit("Preview ready — 12 seconds")
            self._finish_job_strip("Preview ready")
            return
        lang = str(payload.get("language") or self._language_id())
        for item in self._queue:
            if item.language == lang:
                item.status = QUEUE_COMPLETE
                item.percent = 100
                item.output = out
                item.metrics = payload.get("metrics") or {}
        self._record_history(payload)
        self._last_output = out
        if hasattr(self, "btn_open_video"):
            self.btn_open_video.setEnabled(bool(out and Path(out).is_file()))
        self.lbl_stage.setText(f"{language_label(lang)} complete")
        self.lbl_out_path.setText(out)
        self._queue_index += 1
        self._refresh_queue_label()
        self._refresh_history_table()
        if self._queue_index < len(self._batch_projects):
            self._start_queue_item()
            return
        self._busy = False
        self.btn_generate.setEnabled(True)
        self.btn_preview.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.progress.setValue(100)
        self.status_message.emit("Selected videos generated")
        self.btn_retry_failed.setEnabled(bool(failed_languages(self._queue)))
        self._show_batch_summary()
        self._finish_job_strip("Selected videos generated")

    def _on_error(self, human: str, technical: str) -> None:
        self.lbl_stage.setText(human)
        if human.lower().startswith("video rendering was cancelled"):
            self._busy = False
            self.btn_generate.setEnabled(True)
            self.btn_preview.setEnabled(True)
            self.btn_cancel.setEnabled(False)
            self._queue = cancel_pending(self._queue)
            self.status_message.emit("Cancelled")
            self._refresh_queue_label()
            self._finish_job_strip("Cancelled", ok=False)
            return
        lang = self._batch_projects[self._queue_index].language if 0 <= self._queue_index < len(self._batch_projects) else self._language_id()
        isolate_failure(self._queue, lang, human)
        self._refresh_queue_label()
        self.btn_retry_failed.setEnabled(True)
        if not self._preview_job:
            self._batch_errors.append((lang, human, technical))
            self._queue_index += 1
            if self._queue_index < len(self._batch_projects):
                self._busy = True
                self.btn_generate.setEnabled(False)
                self.btn_preview.setEnabled(False)
                self.btn_cancel.setEnabled(True)
                self._start_queue_item()
                return
            self._busy = False
            self.btn_generate.setEnabled(True)
            self.btn_preview.setEnabled(True)
            self.btn_cancel.setEnabled(False)
            names = ", ".join(language_label(x[0]) for x in self._batch_errors)
            show_error(self, "Generate Video", f"Some languages failed: {names}", human)
            self._show_batch_summary()
            self._finish_job_strip("Video generation finished with errors", ok=False)
            return
        self._busy = False
        self.btn_generate.setEnabled(True)
        self.btn_preview.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        show_error(self, "Preview", human, technical)
        self._finish_job_strip(human, ok=False)

    def _open_output(self) -> None:
        folder: Path | None = None
        if self._last_output:
            folder = Path(self._last_output).parent
        else:
            try:
                folder = video_project_dir(self.current_date(), self._language_id())
            except Exception:
                folder = None
        if folder and folder.exists():
            os.startfile(folder)  # noqa: S606
        else:
            show_error(self, "Output", "No video output folder yet. Generate a video first.")

    def _refresh_output_hint(self) -> None:
        try:
            profile_id = str(self.cmb_quality.currentData() or PROFILE_STANDARD)
            path = video_output_path(self.current_date(), self._language_id(), profile_id=profile_id)
            full = str(path)
            self.lbl_out_path.setText(ellipsize_path(full, keep=40))
            self.lbl_out_path.setToolTip(full)
            mb = estimate_project_mb(self.collect_project(), preview_path=self._last_preview)
            self.lbl_size.setText(f"~{mb:.0f} MB")
        except Exception:
            pass

    def _on_text_style_changed(self) -> None:
        if self._suppress:
            return
        style = self.caption_style.style()
        try:
            settings = get_settings()
            settings.caption_font_size = style.font_size
            settings.caption_text_color = style.text_color
            settings.caption_stroke_color = style.stroke_color
            settings.caption_stroke_width = style.stroke_width
            save_settings()
        except Exception:
            pass
        sample = (self.ed_verse.text() or self.ed_topic.text() or "").strip()
        self.caption_style.set_sample(sample)
        self._on_changed()
        self._still_preview()

    def _on_changed(self, *_args) -> None:
        if self._suppress:
            return
        self._refresh_header()
        self._save_timer.start()

    def _autosave(self) -> None:
        if self._busy:
            return
        try:
            save_project(self.collect_project())
        except Exception:
            pass

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._refresh_date_label()
        self._refresh_todays_audio()
        self._refresh_header()

    def _parse_preview_start(self) -> float:
        return parse_timecode(self.ed_preview_start.text())

    def _sync_generate_label(self) -> None:
        n = sum(1 for chk in self._lang_checks.values() if chk.isChecked())
        if n >= 2:
            self.btn_generate.setText("Generate selected videos")
        else:
            self.btn_generate.setText("Generate video")

    def _on_lang_toggles(self) -> None:
        if self._suppress:
            return
        self._sync_generate_label()
        self._on_changed()

    def _select_all_ready(self) -> None:
        for track in self._tracks:
            chk = self._lang_checks.get(track.language)
            if chk is None:
                continue
            chk.blockSignals(True)
            chk.setChecked(bool(track.ready))
            chk.blockSignals(False)
        self._sync_generate_label()
        self._on_changed()

    def _fmt_mmss(self, seconds: float) -> str:
        total = max(0, int(round(float(seconds or 0))))
        return f"{total // 60:02d}:{total % 60:02d}"

    def _sync_trim_labels(self, start: float, end: float, duration: float) -> None:
        end_t = end if end > 0 else duration
        used = max(0.0, end_t - start)
        self.lbl_trim.setText(
            f"Start: {self._fmt_mmss(start)}   End: {self._fmt_mmss(end_t)}   Duration: {self._fmt_mmss(used)}"
        )

    def _sync_trim_sliders(self, item) -> None:
        dur = max(0.05, float(item.duration or 0.0))
        start, end = clamp_trim(item.trim_start, item.trim_end, dur)
        end_t = end if end > 0 else dur
        self._suppress = True
        try:
            self.sld_trim_start.setValue(int(round(1000 * start / dur)))
            self.sld_trim_end.setValue(int(round(1000 * end_t / dur)))
        finally:
            self._suppress = False
        self._sync_trim_labels(start, end, dur)

    def _refresh_live_crop(self) -> None:
        item = self.media.selected_item()
        if not item:
            return
        from dataclasses import replace

        preview = replace(
            item,
            zoom=clamp_zoom(self.sld_zoom.value() / 100.0),
            crop_x=self.sld_pos_x.value() / 100.0 if hasattr(self, "sld_pos_x") else item.crop_x,
            crop_y=self.sld_pos_y.value() / 100.0 if hasattr(self, "sld_pos_y") else item.crop_y,
            fit_mode=(
                FitMode.BAND.value
                if self.btn_band.isChecked()
                else FitMode.FIT.value
                if self.btn_fit.isChecked()
                else FitMode.FILL.value
            ),
        )
        dest = video_temp_root() / "live_crop.png"
        underlay = None
        if getattr(item, "overlay", False):
            underlay = next(
                (
                    other
                    for other in self.media.items()
                    if other is not item and not getattr(other, "overlay", False) and other.exists()
                ),
                None,
            )
        result = render_live_crop_still(
            preview,
            dest,
            background=pad_rgb_for_template(self._template_id),
            underlay=underlay,
        )
        if result:
            pix = QPixmap(str(result))
            if not pix.isNull():
                self.preview_player.set_still(pix)

    def _on_crop_drag(self, dx: float, dy: float) -> None:
        item = self.media.selected_item()
        if not item:
            return
        if self._crop_drag_armed:
            self._push_crop_undo()
            self._crop_drag_armed = False
        self._crop_drag_idle.start()
        ddx, ddy = drag_delta_to_crop(dx, dy, max(1, self.preview.width()), max(1, self.preview.height()))
        cx, cy = clamp_crop(item.crop_x - ddx, item.crop_y - ddy)
        self.media.update_selected(crop_x=cx, crop_y=cy)
        self._sync_pos_sliders(cx, cy)
        self._refresh_live_crop()

    def _on_crop_click(self, px: float, py: float) -> None:
        item = self.media.selected_item()
        if not item:
            return
        self._push_crop_undo()
        nx, ny = click_offset_to_crop(px, py, max(1, self.preview.width()), max(1, self.preview.height()))
        cx, cy = clamp_crop(item.crop_x + nx, item.crop_y + ny)
        self.media.update_selected(crop_x=cx, crop_y=cy)
        self._sync_pos_sliders(cx, cy)
        self._refresh_live_crop()

    def _on_preview_zoom(self, delta: int, px: float, py: float) -> None:
        item = self.media.selected_item()
        if not item:
            return
        self._push_crop_undo()
        step = 0.06 if delta > 0 else -0.06
        nx, ny = click_offset_to_crop(px, py, max(1, self.preview.width()), max(1, self.preview.height()))
        cx, cy, zoom = zoom_toward_point(item.crop_x, item.crop_y, item.zoom, item.zoom + step, nx, ny)
        self.media.update_selected(crop_x=cx, crop_y=cy, zoom=zoom)
        self._suppress = True
        try:
            self.sld_zoom.setValue(int(round(zoom * 100)))
            self.lbl_zoom.setText(f"{self.sld_zoom.value()}%")
            self.sld_pos_x.setValue(int(round(cx * 100)))
            self.sld_pos_y.setValue(int(round(cy * 100)))
        finally:
            self._suppress = False
        self._refresh_live_crop()

    def _open_path(self, path: str = "") -> None:
        target = path or self._last_preview
        if target and Path(target).is_file():
            os.startfile(target)  # noqa: S606
            return
        show_error(self, "Preview", "Generate a 12-second preview first.")

    def _start_queue_item(self) -> None:
        if self._queue_index < 0 or self._queue_index >= len(self._batch_projects):
            return
        project = self._batch_projects[self._queue_index]
        lang = project.language
        for item in self._queue:
            if item.language == lang and item.status != QUEUE_COMPLETE:
                item.status = QUEUE_PREPARING
                item.percent = 0
                item.message = QUEUE_PREPARING
        self.progress.setValue(0)
        self.lbl_stage.setText(f"{language_label(lang)}  {QUEUE_PREPARING}")
        self._refresh_queue_label()
        self._worker = VideoRenderWorker(project, self._signals, preview=False, language=lang)
        QThreadPool.globalInstance().start(self._worker)

    def _on_lang_progress(self, language: str, pct: int, stage: str) -> None:
        for item in self._queue:
            if item.language == language:
                item.percent = int(pct)
                item.status = stage or item.status
                item.message = stage
        self._refresh_queue_label()

    def _refresh_queue_label(self) -> None:
        if not self._queue:
            self.lbl_queue.setText("Waiting")
            return
        lines = []
        for item in self._queue:
            extra = f" {item.percent}%" if item.status in {QUEUE_RENDERING, QUEUE_PREPARING} else ""
            lines.append(f"{item.label}\n{item.status}{extra}")
        self.lbl_queue.setText("\n\n".join(lines))

    def _show_batch_summary(self) -> None:
        summary = batch_completion_summary(self._queue)
        self.lbl_batch_summary.setText(summary["headline"])
        while self.summary_btns_l.count():
            item = self.summary_btns_l.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._summary_btns.clear()
        for row in summary["rows"]:
            line = QHBoxLayout()
            mark = "✓" if row["ok"] else "✗"
            lbl = QLabel(f"{row['label']}\n{mark} {'Open Video' if row['ok'] else 'Failed'}")
            lbl.setWordWrap(True)
            btn = QPushButton("Open Video" if row["ok"] else "—")
            btn.setObjectName("tertiaryButton")
            btn.setEnabled(bool(row["ok"] and row.get("output")))
            out = str(row.get("output") or "")
            btn.clicked.connect(lambda _=False, p=out: self._open_path(p))
            line.addWidget(lbl, 1)
            line.addWidget(btn)
            wrap = QWidget()
            wrap.setLayout(line)
            self.summary_btns_l.addWidget(wrap)
            self._summary_btns[row["language"]] = btn
        self.btn_retry_failed.setEnabled(bool(summary["failed"]))
        self.btn_summary_folder = QPushButton("OPEN OUTPUT FOLDER")
        self.btn_summary_folder.setObjectName("secondaryButton")
        self.btn_summary_folder.clicked.connect(self._open_output)
        self.summary_btns_l.addWidget(self.btn_summary_folder)

    def _record_history(self, payload: dict) -> None:
        if payload.get("preview"):
            return
        metrics = payload.get("metrics") or {}
        out = str(payload.get("output") or "")
        from bmt_voice_studio.video.history import is_preview_output

        if is_preview_output(out):
            return
        lang = str(payload.get("language") or self._language_id())
        size = int(metrics.get("output_bytes") or 0)
        if not size and out and Path(out).is_file():
            size = Path(out).stat().st_size
        upsert_video_entry(
            {
                "date": self.current_date().isoformat(),
                "language": lang,
                "template": TEMPLATE_LABELS.get(self._template_id, self._template_id),
                "quality": str(self.cmb_quality.currentText() or ""),
                "duration": format_duration(metrics.get("video_duration") or self._audio_duration),
                "size": f"{size / (1024 * 1024):.1f} MB" if size else "—",
                "status": QUEUE_COMPLETE,
                "output": out,
                "elapsed_sec": metrics.get("elapsed_sec"),
                "speed": metrics.get("speed"),
            }
        )

    def _toggle_history(self) -> None:
        self._history_expanded = not self._history_expanded
        self._hist_body.setVisible(self._history_expanded)
        self.btn_hist_toggle.setText("Collapse" if self._history_expanded else "Expand")

    def _refresh_timeline(self) -> None:
        if not hasattr(self, "timeline"):
            return
        self.timeline.set_segments(
            intro=self.chk_intro.isChecked(),
            outro=self.chk_outro.isChecked(),
            media_seconds=self._audio_duration or 20.0,
        )

    def _on_timeline_segment(self, kind: str) -> None:
        if kind == SEG_INTRO:
            self.chk_intro.setChecked(True)
            self.music_picker.setFocus(Qt.FocusReason.ShortcutFocusReason)
        elif kind == SEG_OUTRO:
            self.chk_outro.setChecked(True)
            self.music_picker.setFocus(Qt.FocusReason.ShortcutFocusReason)
        elif kind == SEG_MEDIA and self.media.items():
            idx = self.media.selected_index()
            if idx < 0:
                self.media.select_index(0)

    def _fill_recent_combo(self, combo: QComboBox, paths: list[str]) -> None:
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("Recent…", "")
        for path in paths:
            if path and Path(path).is_file():
                combo.addItem(Path(path).name, path)
        combo.setCurrentIndex(0)
        combo.blockSignals(False)

    def _populate_recent_combos(self) -> None:
        settings = get_settings()
        self._fill_recent_combo(self.cmb_recent_logos, list(settings.video_recent_logos or []))
        self._fill_recent_combo(self.cmb_recent_music, list(settings.video_recent_music or []))

    def _on_recent_logo(self, index: int) -> None:
        path = str(self.cmb_recent_logos.itemData(index) or "")
        if not path or not Path(path).is_file():
            return
        settings = get_settings()
        settings.video_logo_path = path
        save_settings(settings)
        self.logo_picker.set_logo_path(path)
        self._on_changed()

    def _on_recent_music(self, index: int) -> None:
        path = str(self.cmb_recent_music.itemData(index) or "")
        if not path or not Path(path).is_file():
            return
        self._music_path = path
        self.music_picker.set_music(
            path,
            intro_enabled=self.chk_intro.isChecked(),
            outro_enabled=self.chk_outro.isChecked(),
            reset_windows=False,
        )
        self._on_changed()

    def _space_play_preview(self) -> None:
        if self.preview_player._path:
            self.preview_player.play()
            return
        self._play_preview()

    def _push_crop_undo(self) -> None:
        if self._crop_undoing:
            return
        item = self.media.selected_item()
        if not item:
            return
        snap = (self.media.selected_index(), float(item.crop_x), float(item.crop_y), float(item.zoom))
        if self._crop_undo and self._crop_undo[-1] == snap:
            return
        self._crop_undo.append(snap)
        self._crop_undo = self._crop_undo[-30:]

    def _undo_crop(self) -> None:
        if not self._crop_undo:
            return
        idx, crop_x, crop_y, zoom = self._crop_undo.pop()
        self._crop_undoing = True
        try:
            if idx >= 0:
                self.media.select_index(idx)
            self.media.update_selected(crop_x=crop_x, crop_y=crop_y, zoom=zoom)
            self._load_crop_panel()
        finally:
            self._crop_undoing = False

    @staticmethod
    def _display_duration(raw) -> str:
        text = str(raw or "").strip()
        if not text or text == "—":
            return "—"
        if ":" in text and "s" not in text.lower():
            return text
        cleaned = text.lower().rstrip("s").strip()
        try:
            return format_duration(float(cleaned))
        except (TypeError, ValueError):
            return text

    @staticmethod
    def _display_status(raw) -> str:
        text = str(raw or "").strip()
        if not text:
            return "—"
        key = text.lower()
        mapping = {
            "complete": "Complete",
            "completed": "Complete",
            "done": "Complete",
            "rendering": "Rendering",
            "failed": "Failed",
            "error": "Failed",
            "waiting": "Waiting",
        }
        return mapping.get(key, text[:1].upper() + text[1:] if text else "—")

    def _refresh_history_table(self) -> None:
        rows = load_video_history()
        shown = rows[:80]
        self._history_paths = []
        self.tbl_history.setRowCount(len(shown))
        self.lbl_hist_count.setText(str(len(rows)))
        for r, entry in enumerate(shown):
            out_path = str(entry.get("output") or "")
            self._history_paths.append(out_path)
            values = [
                str(entry.get("date") or ""),
                language_label(str(entry.get("language") or "")),
                str(entry.get("template") or ""),
                str(entry.get("quality") or ""),
                self._display_duration(entry.get("duration")),
                str(entry.get("size") or "—"),
                self._display_status(entry.get("status")),
                Path(out_path).name if out_path else "—",
            ]
            for c, val in enumerate(values):
                item = QTableWidgetItem(val)
                if c == 7 and out_path:
                    item.setData(Qt.ItemDataRole.UserRole, out_path)
                    item.setToolTip(out_path)
                self.tbl_history.setItem(r, c, item)
        self.btn_open_video.setEnabled(bool(self._last_output and Path(self._last_output).is_file()))

    def _selected_history_output(self) -> str:
        row = self.tbl_history.currentRow()
        if row < 0:
            return self._last_output
        item = self.tbl_history.item(row, 7)
        if item is not None:
            stored = item.data(Qt.ItemDataRole.UserRole)
            if stored:
                return str(stored)
        if 0 <= row < len(self._history_paths):
            return self._history_paths[row]
        return self._last_output

    def _open_last_video(self) -> None:
        path = self._last_output
        if path and Path(path).is_file():
            os.startfile(path)  # noqa: S606
            return
        show_error(self, "Output", "No generated video file is ready yet.")

    def _open_hist_file(self) -> None:
        path = self._selected_history_output()
        if path and Path(path).is_file():
            os.startfile(path)  # noqa: S606
            return
        show_error(self, "Video History", "Select a completed video first.")

    def _open_hist_folder(self) -> None:
        path = self._selected_history_output()
        folder = Path(path).parent if path else None
        if folder and folder.exists():
            os.startfile(folder)  # noqa: S606
            return
        self._open_output()

    def _retry_failed(self) -> None:
        if self._busy:
            return
        langs = failed_languages(self._queue)
        if not langs:
            return
        retry_failed(self._queue)
        base = self.collect_project()
        self._batch_projects = projects_for_batch(base, langs)
        if not self._batch_projects:
            return
        self._batch_errors = []
        self._queue_index = 0
        self._busy = True
        self._preview_job = False
        self.btn_generate.setEnabled(False)
        self.btn_preview.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.btn_retry_failed.setEnabled(False)
        self._refresh_queue_label()
        self._start_queue_item()
