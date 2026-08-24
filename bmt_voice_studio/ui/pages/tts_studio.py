"""TTS Studio page — script editor, segments, generate, preview."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from bmt_voice_studio.config.presets import list_presets
from bmt_voice_studio.config.settings import get_settings
from bmt_voice_studio.core.models import Segment, Speaker
from bmt_voice_studio.core.parser import parse_speaker_script
from bmt_voice_studio.projects.project import ProjectData, ProjectService
from bmt_voice_studio.ui.widgets.common import (
    AudioPlayerBar,
    ScrollPage,
    SegmentFailDialog,
    card,
    labeled_field,
    show_error,
    wrap_in_scroll,
)
from bmt_voice_studio.workers.generation import GenerationController


class TTSStudioPage(QWidget):
    status_message = Signal(str)
    project_changed = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.project = ProjectService().new_project()
        self.segments: list[Segment] = []
        self._gen = GenerationController()
        self._raw_preview_path = ""
        self._mastered_path = ""
        self._building_ui()
        self._wire()
        self.apply_preset(self.project.preset_id)

    def _building_ui(self) -> None:
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        inner = ScrollPage()
        root = QVBoxLayout(inner)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(18)

        header = QHBoxLayout()
        header.setSpacing(12)
        titles = QVBoxLayout()
        title = QLabel("TTS Studio")
        title.setObjectName("pageTitle")
        sub = QLabel("Advanced workspace  ·  Outside braces = Male  ·  {Inside} = Female")
        sub.setObjectName("appSubtitle")
        titles.addWidget(title)
        titles.addWidget(sub)
        header.addLayout(titles, 1)
        self.btn_new = QPushButton("New")
        self.btn_new.setObjectName("tertiaryButton")
        self.btn_save = QPushButton("Save Project")
        self.btn_save.setObjectName("secondaryButton")
        self.btn_open = QPushButton("Open")
        self.btn_open.setObjectName("secondaryButton")
        header.addWidget(self.btn_new)
        header.addWidget(self.btn_open)
        header.addWidget(self.btn_save)
        root.addLayout(header)

        voice_card, voice_l = card("Voice setup", "Presets, voices, rate and pitch")
        voice_l.setSpacing(12)
        self.preset = QComboBox()
        for p in list_presets():
            self.preset.addItem(p.name, p.id)
        self.provider = QComboBox()
        self.provider.addItem("Edge TTS (Online)", "edge")
        self.provider.addItem("Piper (Offline)", "piper")
        self.male = QComboBox()
        self.male.setEditable(True)
        self.male.setMinimumWidth(0)
        self.female = QComboBox()
        self.female.setEditable(True)
        self.female.setMinimumWidth(0)
        self.rate = QComboBox()
        for r in ("-20%", "-15%", "-10%", "-8%", "-5%", "+0%", "+5%", "+10%"):
            self.rate.addItem(r)
        self.pitch = QComboBox()
        for p in ("-6Hz", "-3Hz", "-2Hz", "-1Hz", "+0Hz", "+1Hz", "+2Hz", "+3Hz"):
            self.pitch.addItem(p)
        self.pause = QComboBox()
        for ms in (100, 250, 450, 750, 1000):
            self.pause.addItem(f"{ms} ms", ms)
        self.bitrate = QComboBox()
        for br in (96, 128, 192, 256, 320):
            self.bitrate.addItem(f"MP3 {br} kbps", br)
        for box in (self.preset, self.provider, self.male, self.female, self.rate, self.pitch, self.pause, self.bitrate):
            box.setMinimumWidth(0)
            box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        row1 = QHBoxLayout()
        row1.setSpacing(16)
        row1.addWidget(labeled_field("Preset", self.preset), 1)
        row1.addWidget(labeled_field("Provider", self.provider), 1)
        voice_l.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(16)
        row2.addWidget(labeled_field("Male voice", self.male), 1)
        row2.addWidget(labeled_field("Female voice", self.female), 1)
        voice_l.addLayout(row2)

        row3 = QHBoxLayout()
        row3.setSpacing(16)
        row3.addWidget(labeled_field("Rate", self.rate), 1)
        row3.addWidget(labeled_field("Pitch", self.pitch), 1)
        row3.addWidget(labeled_field("Pause", self.pause), 1)
        row3.addWidget(labeled_field("Output", self.bitrate), 1)
        voice_l.addLayout(row3)

        master_row = QHBoxLayout()
        master_row.setSpacing(20)
        self.chk_norm = QCheckBox("Normalize loudness (−16 LUFS)")
        self.chk_norm.setChecked(True)
        self.chk_limit = QCheckBox("Peak limiter")
        self.chk_limit.setChecked(True)
        self.chk_silence = QCheckBox("Remove excessive silence")
        master_row.addWidget(self.chk_norm)
        master_row.addWidget(self.chk_limit)
        master_row.addWidget(self.chk_silence)
        master_row.addStretch(1)
        voice_l.addLayout(master_row)
        voice_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        root.addWidget(voice_card)

        work = QWidget()
        work.setMinimumHeight(460)
        work.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        work_l = QHBoxLayout(work)
        work_l.setContentsMargins(0, 0, 0, 0)
        work_l.setSpacing(16)

        script_card, script_l = card("Script", "Outside braces = Male  ·  {Inside} = Female")
        script_card.setMinimumHeight(440)
        script_card.setMinimumWidth(0)
        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText(
            "BELIEVERS MANNA TODAY DAILY DEVOTIONAL\n\n"
            "Written by Apostle Doctor David A. Aderibigbe\n\n"
            "{\nMemory Verse\n\nBut seek ye first the Kingdom of God...\n}"
        )
        self.editor.setMinimumHeight(300)
        self.editor.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        script_l.addWidget(self.editor)
        self.lbl_parse = QLabel("Ready")
        self.lbl_parse.setObjectName("taskLabel")
        self.lbl_parse.setWordWrap(False)
        self.lbl_parse.setMinimumHeight(24)
        self.lbl_parse.setMaximumHeight(26)
        self.lbl_parse.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        script_l.addWidget(self.lbl_parse)
        parse_row = QHBoxLayout()
        parse_row.setContentsMargins(0, 4, 0, 0)
        self.btn_parse = QPushButton("Parse Segments")
        self.btn_parse.setObjectName("secondaryButton")
        self.btn_parse.setMinimumHeight(36)
        parse_row.addWidget(self.btn_parse)
        parse_row.addStretch(1)
        script_l.addLayout(parse_row)
        work_l.addWidget(script_card, 1)

        seg_card, seg_l = card("Segments", "Click a segment to edit, preview, or regenerate")
        seg_card.setMinimumHeight(440)
        seg_card.setMinimumWidth(0)
        self.seg_list = QListWidget()
        self.seg_list.setMinimumHeight(180)
        self.seg_list.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        seg_l.addWidget(self.seg_list)
        self.seg_edit = QPlainTextEdit()
        self.seg_edit.setPlaceholderText("Selected segment text…")
        self.seg_edit.setMinimumHeight(88)
        self.seg_edit.setMaximumHeight(120)
        self.seg_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        seg_l.addWidget(self.seg_edit)
        self.btn_preview_seg = QPushButton("Preview Segment")
        self.btn_preview_seg.setObjectName("secondaryButton")
        self.btn_regen_seg = QPushButton("Regenerate")
        self.btn_toggle_seg = QPushButton("Disable / Enable")
        self.btn_toggle_seg.setObjectName("tertiaryButton")
        self.btn_apply_seg = QPushButton("Apply Edit")
        self.btn_apply_seg.setObjectName("secondaryButton")
        self.btn_swap_voice = QPushButton("Swap Speaker")
        self.btn_swap_voice.setObjectName("tertiaryButton")
        row_a = QHBoxLayout()
        row_a.setSpacing(10)
        row_b = QHBoxLayout()
        row_b.setSpacing(10)
        for b in (self.btn_preview_seg, self.btn_regen_seg, self.btn_toggle_seg, self.btn_apply_seg, self.btn_swap_voice):
            b.setMinimumHeight(36)
            b.setMinimumWidth(0)
        row_a.addWidget(self.btn_apply_seg)
        row_a.addWidget(self.btn_preview_seg)
        row_a.addStretch(1)
        row_b.addWidget(self.btn_regen_seg)
        row_b.addWidget(self.btn_toggle_seg)
        row_b.addWidget(self.btn_swap_voice)
        row_b.addStretch(1)
        seg_l.addLayout(row_a)
        seg_l.addLayout(row_b)
        work_l.addWidget(seg_card, 1)
        root.addWidget(work)

        gen_card, gen_l = card("Generate", "Smart regeneration only rebuilds changed segments")
        gen_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_generate = QPushButton("Generate Final Audio")
        self.btn_generate.setObjectName("primaryButton")
        self.btn_generate.setMinimumHeight(44)
        self.btn_generate.setMinimumWidth(200)
        self.btn_generate.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setObjectName("tertiaryButton")
        self.btn_cancel.setEnabled(False)
        self.btn_ab = QPushButton("A/B Preview")
        self.btn_ab.setObjectName("secondaryButton")
        self.btn_open_out = QPushButton("Open Output Folder")
        self.btn_open_out.setObjectName("secondaryButton")
        for b in (self.btn_cancel, self.btn_ab, self.btn_open_out):
            b.setMinimumHeight(36)
            b.setMinimumWidth(120)
            b.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        gen_row = QHBoxLayout()
        gen_row.setSpacing(12)
        gen_row.addWidget(self.btn_generate)
        gen_row.addWidget(self.btn_cancel)
        gen_row.addWidget(self.btn_ab)
        gen_row.addWidget(self.btn_open_out)
        gen_row.addStretch(1)
        gen_l.addLayout(gen_row)
        self.lbl_task = QLabel("Ready")
        self.lbl_task.setObjectName("taskLabel")
        self.lbl_task.setWordWrap(False)
        self.lbl_task.setMinimumHeight(20)
        self.lbl_task.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        gen_l.addWidget(self.lbl_task)
        self.progress = QProgressBar()
        self.progress.setValue(0)
        gen_l.addWidget(self.progress)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setFixedHeight(64)
        self.log.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        gen_l.addWidget(self.log)

        play_card, play_l = card("Final audio", "Play, seek, and check the mastered export")
        play_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.player = AudioPlayerBar()
        play_l.addWidget(self.player)
        root.addWidget(gen_card)
        root.addWidget(play_card)
        outer.addWidget(wrap_in_scroll(inner), 1)

    def _wire(self) -> None:
        self.btn_parse.clicked.connect(self.parse_script)
        self.editor.textChanged.connect(self._on_text_changed)
        self.preset.currentIndexChanged.connect(self._on_preset)
        self.seg_list.currentRowChanged.connect(self._on_seg_selected)
        self.btn_apply_seg.clicked.connect(self._apply_seg_edit)
        self.btn_toggle_seg.clicked.connect(self._toggle_seg)
        self.btn_swap_voice.clicked.connect(self._swap_speaker)
        self.btn_preview_seg.clicked.connect(self._preview_seg)
        self.btn_regen_seg.clicked.connect(self._regen_one)
        self._generating = False
        self.btn_generate.clicked.connect(self.generate)
        self.btn_cancel.clicked.connect(self._gen.cancel)
        self.btn_ab.clicked.connect(self._ab_preview)
        self.btn_open_out.clicked.connect(self._open_output)
        self.btn_save.clicked.connect(self.save_project)
        self.btn_open.clicked.connect(self.open_project)
        self.btn_new.clicked.connect(self.new_project)
        self._gen.signals.progress.connect(self._on_progress)
        self._gen.signals.log.connect(self._append_log)
        self._gen.signals.finished.connect(self._on_done)
        self._gen.signals.error.connect(self._on_error)
        self._gen.signals.segment_failed.connect(self._on_seg_fail)
        self._gen.signals.segment_done.connect(lambda i, p: None)

    def set_voice_options(self, male_names: list[str], female_names: list[str]) -> None:
        cur_m, cur_f = self.male.currentText(), self.female.currentText()
        self.male.blockSignals(True)
        self.female.blockSignals(True)
        self.male.clear()
        self.female.clear()
        self.male.addItems(male_names or [cur_m] if cur_m else [])
        self.female.addItems(female_names or [cur_f] if cur_f else [])
        if cur_m:
            self.male.setCurrentText(cur_m)
        if cur_f:
            self.female.setCurrentText(cur_f)
        self.male.blockSignals(False)
        self.female.blockSignals(False)

    def apply_preset(self, preset_id: str) -> None:
        from bmt_voice_studio.config.presets import get_preset

        p = get_preset(preset_id)
        if not p:
            return
        idx = self.preset.findData(preset_id)
        if idx >= 0:
            self.preset.setCurrentIndex(idx)
        self.male.setCurrentText(p.male_voice)
        self.female.setCurrentText(p.female_voice)
        self.rate.setCurrentText(p.rate)
        self.pitch.setCurrentText(p.pitch)
        self.provider.setCurrentIndex(0 if p.provider == "edge" else 1)

    def _on_preset(self) -> None:
        self.apply_preset(self.preset.currentData())

    def _on_text_changed(self) -> None:
        # Lightweight brace validation highlight
        text = self.editor.toPlainText()
        result = parse_speaker_script(text)
        if result.errors:
            errs = [e for e in result.errors if e.severity == "error"]
            if errs:
                e = errs[0]
                loc = f"L{e.line}:{e.column}" if e.line else ""
                self.lbl_parse.setText(f"Syntax: {e.message} {loc}")
                self.lbl_parse.setStyleSheet("color:#F07178; font-size:13px; background:transparent;")
                return
        self.lbl_parse.setText(f"{len(result.segments)} segments detected")
        self.lbl_parse.setStyleSheet("color:#7FD99A; font-size:13px; background:transparent;")

    def parse_script(self) -> None:
        result = parse_speaker_script(self.editor.toPlainText())
        if not result.ok:
            msgs = "\n".join(
                f"Line {e.line}: {e.message}" if e.line else e.message for e in result.errors
            )
            show_error(self, "Script syntax", msgs)
            return
        # Preserve cache paths for unchanged text hashes where possible
        old_by_idx = {s.index: s for s in self.segments}
        for seg in result.segments:
            seg.voice = self.male.currentText() if seg.speaker == Speaker.MALE else self.female.currentText()
            seg.rate = self.rate.currentText()
            seg.pitch = self.pitch.currentText()
            seg.volume = "+0%"
            seg.provider = self.provider.currentData()
            prev = old_by_idx.get(seg.index)
            if prev and prev.text == seg.text and prev.speaker == seg.speaker:
                seg.audio_path = prev.audio_path
                seg.cache_hash = prev.cache_hash
                seg.enabled = prev.enabled
        self.segments = result.segments
        self._refresh_seg_list()
        self.status_message.emit(f"Parsed {len(self.segments)} segments")

    def _refresh_seg_list(self) -> None:
        self.seg_list.clear()
        for seg in self.segments:
            flag = "" if seg.enabled else " [OFF]"
            item = QListWidgetItem(f"{seg.label}{flag}")
            if seg.speaker == Speaker.FEMALE:
                item.setForeground(QColor("#E5A5FF"))
            else:
                item.setForeground(QColor("#7EC8FF"))
            if not seg.enabled:
                item.setForeground(QColor("#6B7A8F"))
            self.seg_list.addItem(item)

    def _on_seg_selected(self, row: int) -> None:
        if row < 0 or row >= len(self.segments):
            return
        self.seg_edit.setPlainText(self.segments[row].text)

    def _apply_seg_edit(self) -> None:
        row = self.seg_list.currentRow()
        if row < 0:
            return
        self.segments[row].text = self.seg_edit.toPlainText().strip()
        self.segments[row].cache_hash = ""  # force regen
        self._refresh_seg_list()
        self.seg_list.setCurrentRow(row)

    def _toggle_seg(self) -> None:
        row = self.seg_list.currentRow()
        if row < 0:
            return
        self.segments[row].enabled = not self.segments[row].enabled
        self._refresh_seg_list()
        self.seg_list.setCurrentRow(row)

    def _swap_speaker(self) -> None:
        row = self.seg_list.currentRow()
        if row < 0:
            return
        seg = self.segments[row]
        seg.speaker = Speaker.FEMALE if seg.speaker == Speaker.MALE else Speaker.MALE
        seg.voice = self.male.currentText() if seg.speaker == Speaker.MALE else self.female.currentText()
        seg.cache_hash = ""
        self._refresh_seg_list()
        self.seg_list.setCurrentRow(row)

    def _sync_project(self) -> None:
        self.project.source_text = self.editor.toPlainText()
        self.project.preset_id = self.preset.currentData() or "bmt_english"
        self.project.provider = self.provider.currentData() or "edge"
        self.project.male_voice = self.male.currentText()
        self.project.female_voice = self.female.currentText()
        self.project.rate = self.rate.currentText()
        self.project.pitch = self.pitch.currentText()
        self.project.pause_ms = int(self.pause.currentData() or 450)
        self.project.mp3_bitrate = int(self.bitrate.currentData() or 128)
        self.project.normalize_loudness = self.chk_norm.isChecked()
        self.project.peak_limiter = self.chk_limit.isChecked()
        self.project.remove_silence = self.chk_silence.isChecked()
        self.project.set_segments(self.segments)

    def generate(self) -> None:
        if getattr(self, "_generating", False):
            return
        if not self.segments:
            self.parse_script()
        if not self.segments:
            return
        self._sync_project()
        self._generating = True
        self.btn_generate.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.progress.setValue(0)
        self.lbl_task.setText("Starting generation…")
        self._append_log("Starting generation…")
        self._gen.start(self.project, self.segments)

    def _regen_one(self) -> None:
        row = self.seg_list.currentRow()
        if row < 0:
            return
        self.segments[row].cache_hash = ""
        self.segments[row].audio_path = ""
        self.generate()

    def _preview_seg(self) -> None:
        row = self.seg_list.currentRow()
        if row < 0:
            return
        path = self.segments[row].audio_path
        if path and Path(path).exists():
            self.player.play_file(path)
        else:
            QMessageBox.information(self, "Preview", "Generate this segment first.")

    def _ab_preview(self) -> None:
        # Toggle between raw and mastered if both exist
        if self._mastered_path and Path(self._mastered_path).exists():
            if self.player._path == self._mastered_path and self._raw_preview_path:
                self.player.play_file(self._raw_preview_path)
                self.status_message.emit("A/B: Original")
            else:
                self.player.play_file(self._mastered_path)
                self.status_message.emit("A/B: Processed")
        else:
            QMessageBox.information(self, "A/B Preview", "Generate final audio first.")

    def _open_output(self) -> None:
        folder = self.project.output_folder
        if folder and Path(folder).exists():
            import os

            os.startfile(folder)  # noqa: S606
        else:
            QMessageBox.information(self, "Output", "No output folder yet — generate first.")

    def _on_progress(self, current: int, total: int, message: str) -> None:
        self.progress.setMaximum(max(1, total))
        self.progress.setValue(current)
        self.lbl_task.setText(message)
        self.status_message.emit(message)

    def _append_log(self, msg: str) -> None:
        self.log.append(msg)

    def _on_done(self, result: dict) -> None:
        self._generating = False
        self.btn_generate.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.project = result["project"]
        self.segments = result["segments"]
        self._mastered_path = result.get("mp3", "")
        self._raw_preview_path = result.get("raw", "")
        self._refresh_seg_list()
        if self._mastered_path:
            self.player.play_file(self._mastered_path)
        self.lbl_task.setText("Final audio ready")
        self.status_message.emit("Final audio ready")
        self.project_changed.emit(self.project)
        QMessageBox.information(
            self,
            "Done",
            f"Export complete.\n\nMP3: {result.get('mp3')}\nWAV: {result.get('wav')}",
        )

    def _on_error(self, human: str, technical: str) -> None:
        self._generating = False
        self.btn_generate.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        show_error(self, "Generation error", human, technical)

    def _on_seg_fail(self, index: int, error: str) -> None:
        dlg = SegmentFailDialog(self, index, error)
        dlg.exec()
        clicked = dlg.clickedButton()
        if clicked == dlg.retry:
            self._gen.resolve_failure("retry")
        elif clicked == dlg.use_piper:
            self._gen.resolve_failure("switch")
        elif clicked == dlg.skip:
            self._gen.resolve_failure("skip")
        else:
            self._gen.cancel()
            self._gen.resolve_failure("skip")

    def new_project(self) -> None:
        self.project = ProjectService().new_project()
        self.editor.clear()
        self.segments = []
        self._refresh_seg_list()
        self.apply_preset(self.project.preset_id)
        self.status_message.emit("New project")

    def save_project(self) -> None:
        self._sync_project()
        path = ProjectService().save(self.project)
        self.status_message.emit(f"Saved {path}")
        QMessageBox.information(self, "Saved", f"Project saved:\n{path}")

    def open_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Project", str(Path.home()), "BMT Project (*.json)"
        )
        if not path:
            return
        self.load_project_path(path)

    def load_project_path(self, path: str) -> None:
        project = ProjectService().load(Path(path))
        self.project = project
        self.editor.setPlainText(project.source_text)
        self.segments = project.get_segments()
        self.apply_preset(project.preset_id)
        self.male.setCurrentText(project.male_voice)
        self.female.setCurrentText(project.female_voice)
        self.rate.setCurrentText(project.rate)
        self.pitch.setCurrentText(project.pitch)
        self._refresh_seg_list()
        if project.final_mp3 and Path(project.final_mp3).exists():
            self._mastered_path = project.final_mp3
            self.player.load(project.final_mp3)
        self.status_message.emit(f"Opened {project.name}")

    def load_sample(self, text: str, preset_id: str) -> None:
        self.new_project()
        self.editor.setPlainText(text)
        self.apply_preset(preset_id)
        self.parse_script()
