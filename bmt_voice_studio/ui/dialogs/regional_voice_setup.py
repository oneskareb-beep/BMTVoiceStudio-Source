"""Help → Troubleshooting → Regional Voice Setup (audition + explicit approve)."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from bmt_voice_studio.daily.regional_approval import (
    approve_fallback_candidate,
    get_regional_entry,
    get_swahili_trial_pair,
    is_language_production_approved,
    select_swahili_male_candidate,
    set_swahili_trial_pair,
)
from bmt_voice_studio.daily.regional_audition import (
    PT_PORTUGAL,
    SW_KENYA,
    SW_TANZANIA,
    auditions_dir,
    full_test_dir,
    generate_all_regional_auditions,
    generate_swahili_daudi_rehema_full_test,
    generate_swahili_male_review_auditions,
    load_manifest,
)
from bmt_voice_studio.daily.regional_voice_discovery import (
    discover_portuguese_angola,
    discover_swahili_congo,
)
from bmt_voice_studio.ui.widgets.common import AudioPlayerBar
from bmt_voice_studio.workers.generation import AsyncWorker, WorkerSignals


class _CandidateCard(QFrame):
    def __init__(self, spec: dict[str, str], parent=None) -> None:
        super().__init__(parent)
        self.spec = dict(spec)
        self.setObjectName("card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(6)

        title = QLabel(spec.get("label", ""))
        title.setObjectName("cardTitle")
        banner = QLabel(spec.get("banner", ""))
        banner.setObjectName("appSubtitle")
        banner.setWordWrap(True)
        self.lbl_male = QLabel(f"Male voice: {spec.get('male_voice', '')}")
        self.lbl_female = QLabel(f"Female voice: {spec.get('female_voice', '')}")
        for lbl in (self.lbl_male, self.lbl_female):
            lbl.setObjectName("appSubtitle")
            lbl.setWordWrap(True)
        self.lbl_files = QLabel("Audition files: not generated yet")
        self.lbl_files.setObjectName("appSubtitle")
        self.lbl_files.setWordWrap(True)
        self.lbl_approved = QLabel("")
        self.lbl_approved.setObjectName("appSubtitle")
        self.lbl_approved.setWordWrap(True)

        lay.addWidget(title)
        lay.addWidget(banner)
        lay.addWidget(self.lbl_male)
        lay.addWidget(self.lbl_female)
        lay.addWidget(self.lbl_files)
        lay.addWidget(self.lbl_approved)

        row = QHBoxLayout()
        self.btn_male = QPushButton("Play male")
        self.btn_female = QPushButton("Play female")
        self.btn_combined = QPushButton("Play combined audition")
        self.btn_approve = QPushButton("APPROVE THIS PAIR")
        self.btn_approve.setObjectName("primaryButton")
        for b in (self.btn_male, self.btn_female, self.btn_combined):
            b.setObjectName("secondaryButton")
            b.setEnabled(False)
            row.addWidget(b)
        row.addWidget(self.btn_approve)
        row.addStretch(1)
        lay.addLayout(row)

        self._male_path = ""
        self._female_path = ""
        self._combined_path = ""

    def apply_result(self, data: dict) -> None:
        self.spec["male_voice"] = data.get("male_voice") or self.spec.get("male_voice", "")
        self.spec["female_voice"] = data.get("female_voice") or self.spec.get("female_voice", "")
        self.lbl_male.setText(f"Male voice: {self.spec['male_voice']}")
        self.lbl_female.setText(f"Female voice: {self.spec['female_voice']}")
        self._male_path = data.get("male_sample_mp3") or ""
        self._female_path = data.get("female_sample_mp3") or ""
        self._combined_path = data.get("combined_mp3") or ""
        ok = bool(data.get("ok"))
        self.btn_male.setEnabled(bool(self._male_path and Path(self._male_path).exists()))
        self.btn_female.setEnabled(bool(self._female_path and Path(self._female_path).exists()))
        self.btn_combined.setEnabled(bool(self._combined_path and Path(self._combined_path).exists()))
        dur = data.get("duration_sec")
        files = []
        if data.get("combined_mp3"):
            files.append(Path(data["combined_mp3"]).name)
        if data.get("combined_wav"):
            files.append(Path(data["combined_wav"]).name)
        probe = (
            f" · {dur}s · {data.get('sample_rate')} Hz · "
            f"{data.get('channels')} ch · {data.get('bitrate_kbps')} kbps"
            if ok
            else ""
        )
        status = "OK" if ok else ("FAILED: " + "; ".join(data.get("errors") or []))
        self.lbl_files.setText(
            f"Audition: {', '.join(files) or '(none)'} — {status}{probe}"
        )

    def refresh_approval_badge(self) -> None:
        entry = get_regional_entry(self.spec["language_id"])
        approved = (
            is_language_production_approved(self.spec["language_id"])
            and entry.get("approved_candidate_id") == self.spec.get("candidate_id")
        )
        if approved:
            self.lbl_approved.setText(
                f"Approved for production · fallback_locale={entry.get('fallback_locale')}"
            )
        else:
            self.lbl_approved.setText("Not approved (requires explicit APPROVE THIS PAIR)")


class RegionalVoiceSetupDialog(QDialog):
    def __init__(self, parent=None, *, focus_language: str | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Regional Voice Setup")
        self.setMinimumSize(860, 720)
        root = QVBoxLayout(self)

        hint = QLabel(
            "Target locales sw-CD and pt-AO are currently unavailable.\n"
            "Swahili trial pair (Daudi + Rehema, Tanzania) is for listening only — NOT Congo, NOT approved.\n"
            "Portuguese remains blocked until Angolan listeners approve a fallback.\n"
            "Nothing is approved automatically."
        )
        hint.setWordWrap(True)
        hint.setObjectName("appSubtitle")
        root.addWidget(hint)

        actions = QHBoxLayout()
        self.btn_verify = QPushButton("Re-check target locales (sw-CD / pt-AO)")
        self.btn_generate = QPushButton("Generate pair auditions")
        self.btn_generate_male = QPushButton("Generate Swahili male review")
        self.btn_generate_male.setObjectName("primaryButton")
        self.btn_open_folder = QPushButton("Open auditions folder")
        for b in (self.btn_verify, self.btn_generate, self.btn_generate_male, self.btn_open_folder):
            if b is not self.btn_generate_male:
                b.setObjectName("secondaryButton")
            actions.addWidget(b)
        actions.addStretch(1)
        root.addLayout(actions)

        self.lbl_target = QLabel("Target status: not checked this session")
        self.lbl_target.setObjectName("appSubtitle")
        self.lbl_target.setWordWrap(True)
        root.addWidget(self.lbl_target)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        host = QWidget()
        self._host_lay = QVBoxLayout(host)
        self._host_lay.setSpacing(12)

        self._cards: dict[str, _CandidateCard] = {}
        self._male_paths: dict[str, str] = {}
        self._full_test_mp3 = ""

        # --- Priority: Swahili trial pair (Daudi + Rehema) ---
        trial_hdr = QLabel("SWAHILI TRIAL PAIR")
        trial_hdr.setObjectName("cardTitle")
        self._host_lay.addWidget(trial_hdr)
        trial_card = QFrame()
        trial_card.setObjectName("card")
        trial_lay = QVBoxLayout(trial_card)
        trial_lay.setContentsMargins(12, 10, 12, 10)
        trial_lay.setSpacing(6)
        self.lbl_trial_male = QLabel("Male:\nDaudi — Tanzania")
        self.lbl_trial_female = QLabel("Female:\nRehema — Tanzania")
        self.lbl_trial_status = QLabel("Status:\nTRIAL — NOT APPROVED")
        for lbl in (self.lbl_trial_male, self.lbl_trial_female, self.lbl_trial_status):
            lbl.setObjectName("appSubtitle")
            lbl.setWordWrap(True)
            trial_lay.addWidget(lbl)
        trial_note = QLabel(
            "Target remains Congo / DRC. Voices are Tanzania fallback candidates — not Congo labels.\n"
            "Daily Swahili production stays blocked until you press Approve Pair."
        )
        trial_note.setObjectName("appSubtitle")
        trial_note.setWordWrap(True)
        trial_lay.addWidget(trial_note)
        trial_btns = QHBoxLayout()
        self.btn_play_full_test = QPushButton("Play Full Test")
        self.btn_open_test_folder = QPushButton("Open Test Folder")
        self.btn_approve_trial = QPushButton("Approve Pair")
        self.btn_generate_full_test = QPushButton("Generate Full Test")
        for b in (
            self.btn_play_full_test,
            self.btn_open_test_folder,
            self.btn_approve_trial,
            self.btn_generate_full_test,
        ):
            b.setObjectName("secondaryButton")
            trial_btns.addWidget(b)
        trial_btns.addStretch(1)
        trial_lay.addLayout(trial_btns)
        self._host_lay.addWidget(trial_card)

        # --- Swahili male review ---
        male_hdr = QLabel("SWAHILI MALE VOICE REVIEW")
        male_hdr.setObjectName("cardTitle")
        self._host_lay.addWidget(male_hdr)
        male_note = QLabel(
            "Not Congo. Compare African male candidates only.\n"
            "SELECT MALE CANDIDATE records preference — it does NOT approve production."
        )
        male_note.setObjectName("appSubtitle")
        male_note.setWordWrap(True)
        self._host_lay.addWidget(male_note)

        self.lbl_male_selection = QLabel("Selected male: (none)")
        self.lbl_male_selection.setObjectName("appSubtitle")
        self._host_lay.addWidget(self.lbl_male_selection)

        for mid, title, voice in (
            ("sw_male_rafiki_ke", "Rafiki — Kenya", "sw-KE-RafikiNeural"),
            ("sw_male_daudi_tz", "Daudi — Tanzania", "sw-TZ-DaudiNeural"),
        ):
            row_w = QFrame()
            row_w.setObjectName("card")
            row = QHBoxLayout(row_w)
            lab = QLabel(f"{title}\n{voice}")
            lab.setObjectName("appSubtitle")
            lab.setWordWrap(True)
            btn_play = QPushButton("Play")
            btn_play.setObjectName("secondaryButton")
            btn_sel = QPushButton("SELECT MALE CANDIDATE")
            btn_sel.setObjectName("secondaryButton")
            btn_play.clicked.connect(lambda _=False, cid=mid: self._play_male_review(cid))
            btn_sel.clicked.connect(
                lambda _=False, cid=mid, v=voice, t=title: self._select_male(cid, v, t)
            )
            row.addWidget(lab, 1)
            row.addWidget(btn_play)
            row.addWidget(btn_sel)
            self._host_lay.addWidget(row_w)

        brazil_placeholder = {
            "candidate_id": "pt_brazil",
            "language_id": "pt",
            "label": "BRAZIL",
            "fallback_locale": "pt-BR",
            "male_voice": "(selected from live Edge list)",
            "female_voice": "(selected from live Edge list)",
            "stem": "PORTUGUESE_BRAZIL_AUDITION",
            "banner": "Candidate fallback for Angola target",
        }
        for title, specs in (
            ("SWAHILI — pair auditions (approval deferred while male is under review)", [SW_KENYA, SW_TANZANIA]),
            ("PORTUGUESE — candidate fallbacks for Angola (keep unapproved)", [PT_PORTUGAL, brazil_placeholder]),
        ):
            hdr = QLabel(title)
            hdr.setObjectName("cardTitle")
            self._host_lay.addWidget(hdr)
            for spec in specs:
                card = _CandidateCard(spec)
                card.btn_male.clicked.connect(
                    lambda _=False, c=card: self._play(c._male_path)
                )
                card.btn_female.clicked.connect(
                    lambda _=False, c=card: self._play(c._female_path)
                )
                card.btn_combined.clicked.connect(
                    lambda _=False, c=card: self._play(c._combined_path)
                )
                card.btn_approve.clicked.connect(
                    lambda _=False, c=card: self._approve(c)
                )
                # Swahili pair approval deferred during male review.
                if spec["language_id"] == "sw":
                    card.btn_approve.setEnabled(False)
                    card.btn_approve.setText("APPROVE PAIR (deferred)")
                    card.lbl_approved.setText(
                        "Male under review — pair approval disabled in this phase"
                    )
                self._cards[spec["candidate_id"]] = card
                self._host_lay.addWidget(card)
        self._host_lay.addStretch(1)
        scroll.setWidget(host)
        root.addWidget(scroll, 1)

        self.player = AudioPlayerBar()
        root.addWidget(self.player)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(140)
        root.addWidget(self.log)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        root.addWidget(buttons)

        self.btn_verify.clicked.connect(self._verify_targets)
        self.btn_generate.clicked.connect(self._generate_auditions)
        self.btn_generate_male.clicked.connect(self._generate_male_review)
        self.btn_open_folder.clicked.connect(self._open_folder)
        self.btn_play_full_test.clicked.connect(self._play_full_test)
        self.btn_open_test_folder.clicked.connect(self._open_test_folder)
        self.btn_approve_trial.clicked.connect(self._approve_trial_pair)
        self.btn_generate_full_test.clicked.connect(self._generate_full_test)

        # Ensure trial pair is recorded (not approved).
        set_swahili_trial_pair()
        self._reload_from_manifest()
        self._refresh_all_badges()
        self._refresh_target_status()
        self._refresh_male_selection_label()
        self._refresh_trial_panel()
        if focus_language:
            self.log.append(f"Focused language: {focus_language}")

    def _refresh_trial_panel(self) -> None:
        trial = get_swahili_trial_pair()
        male = trial.get("male_voice") or "sw-TZ-DaudiNeural"
        female = trial.get("female_voice") or "sw-TZ-RehemaNeural"
        self.lbl_trial_male.setText(f"Male:\nDaudi — Tanzania\n{male}")
        self.lbl_trial_female.setText(f"Female:\nRehema — Tanzania\n{female}")
        approved = is_language_production_approved("sw")
        status = "APPROVED" if approved else "TRIAL — NOT APPROVED"
        self.lbl_trial_status.setText(f"Status:\n{status}")
        mp3 = full_test_dir() / "SWAHILI_DAUDI_REHEMA_FULL_TEST.mp3"
        if mp3.exists():
            self._full_test_mp3 = str(mp3)

    def _play_full_test(self) -> None:
        path = self._full_test_mp3 or str(
            full_test_dir() / "SWAHILI_DAUDI_REHEMA_FULL_TEST.mp3"
        )
        self._play(path)

    def _open_test_folder(self) -> None:
        folder = full_test_dir()
        try:
            os.startfile(folder)  # noqa: S606
        except Exception as exc:
            QMessageBox.warning(self, "Folder", str(exc))

    def _generate_full_test(self) -> None:
        self.btn_generate_full_test.setEnabled(False)
        self.log.append("Generating SWAHILI Daudi+Rehema FULL TEST (Edge only)…")
        signals = WorkerSignals()

        async def work(_w):
            return await generate_swahili_daudi_rehema_full_test()

        def done(report):
            self.btn_generate_full_test.setEnabled(True)
            data = report if isinstance(report, dict) else {}
            if data.get("mp3_path"):
                self._full_test_mp3 = data["mp3_path"]
            self._refresh_trial_panel()
            self._refresh_target_status()
            self.log.append(
                f"[FULL TEST] ok={data.get('ok')} segs={data.get('segment_count')} "
                f"dur={data.get('duration_sec')}s → {data.get('mp3_path')}"
            )
            QMessageBox.information(
                self,
                "Full test ready",
                "Daudi + Rehema full Swahili test generated.\n"
                "Status remains TRIAL — NOT APPROVED.\n"
                "Listen, then press Approve Pair only if you decide to approve.",
            )

        signals.finished.connect(done)
        signals.error.connect(
            lambda h, t: (
                self.btn_generate_full_test.setEnabled(True),
                self.log.append(f"ERROR: {h}\n{t}"),
            )
        )
        QThreadPool.globalInstance().start(AsyncWorker(work, signals))

    def _approve_trial_pair(self) -> None:
        """Human-only approve of Daudi + Rehema — never called automatically."""
        answer = QMessageBox.question(
            self,
            "Approve Swahili trial pair?",
            "Approve Daudi + Rehema (Tanzania) as the Swahili production fallback?\n\n"
            "Target remains Congo / DRC.\n"
            "Voices stay labeled as Tanzania fallback — not Congo.\n\n"
            "Male: sw-TZ-DaudiNeural\n"
            "Female: sw-TZ-RehemaNeural\n\n"
            "This is an explicit human decision.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            approve_fallback_candidate(
                "sw",
                fallback_locale="sw-TZ",
                male_voice="sw-TZ-DaudiNeural",
                female_voice="sw-TZ-RehemaNeural",
                candidate_id="sw_tanzania_trial",
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Approve", str(exc))
            return
        self._refresh_trial_panel()
        self._refresh_all_badges()
        self._refresh_target_status()
        self.log.append("APPROVED Swahili trial pair: Daudi + Rehema (sw-TZ)")
        QMessageBox.information(
            self,
            "Approved",
            "Daudi + Rehema approved for Swahili Daily production fallback.",
        )

    def _play_male_review(self, candidate_id: str) -> None:
        path = self._male_paths.get(candidate_id) or ""
        if not path:
            # Fall back to known stem paths on disk.
            stems = {
                "sw_male_rafiki_ke": "SWAHILI_MALE_RAFIKI_KE.mp3",
                "sw_male_daudi_tz": "SWAHILI_MALE_DAUDI_TZ.mp3",
            }
            path = str(auditions_dir() / stems.get(candidate_id, ""))
        self._play(path)

    def _select_male(self, candidate_id: str, voice: str, title: str) -> None:
        select_swahili_male_candidate(candidate_id, voice)
        self._refresh_male_selection_label()
        self._refresh_target_status()
        self.log.append(f"Male candidate selected (NOT approved): {title} / {voice}")
        QMessageBox.information(
            self,
            "Male candidate recorded",
            f"{title} recorded for review.\n"
            "This is NOT production approval.\n"
            "Swahili Daily BMT generation remains blocked.",
        )

    def _refresh_male_selection_label(self) -> None:
        entry = get_regional_entry("sw")
        voice = entry.get("selected_male_voice") or ""
        cid = entry.get("selected_male_candidate_id") or ""
        if voice:
            self.lbl_male_selection.setText(
                f"Selected male: {voice} ({cid}) — not production-approved"
            )
        else:
            self.lbl_male_selection.setText("Selected male: (none)")

    def _generate_male_review(self) -> None:
        self.btn_generate_male.setEnabled(False)
        self.log.append("Generating Swahili male review auditions (Edge only)…")
        signals = WorkerSignals()

        async def work(_w):
            return await generate_swahili_male_review_auditions()

        def done(results):
            self.btn_generate_male.setEnabled(True)
            for r in results or []:
                data = r.to_dict() if hasattr(r, "to_dict") else dict(r)
                cid = data.get("candidate_id") or ""
                if data.get("combined_mp3"):
                    self._male_paths[cid] = data["combined_mp3"]
                self.log.append(
                    f"[MALE {data.get('label')}] ok={data.get('ok')} "
                    f"{data.get('male_voice')} → {data.get('combined_mp3')} "
                    f"({data.get('duration_sec')}s)"
                )
            QMessageBox.information(
                self,
                "Male review ready",
                "Rafiki and Daudi male auditions generated.\n"
                "Listen, then SELECT MALE CANDIDATE.\n"
                "No production approval was granted.",
            )

        signals.finished.connect(done)
        signals.error.connect(
            lambda h, t: (
                self.btn_generate_male.setEnabled(True),
                self.log.append(f"ERROR: {h}\n{t}"),
            )
        )
        QThreadPool.globalInstance().start(AsyncWorker(work, signals))

    def _play(self, path: str) -> None:
        if path and Path(path).exists():
            self.player.play_file(path)
            self.log.append(f"Playing: {path}")
        else:
            QMessageBox.information(self, "Play", "Generate auditions first.")

    def _open_folder(self) -> None:
        folder = auditions_dir()
        try:
            os.startfile(folder)  # noqa: S606
        except Exception as exc:
            QMessageBox.warning(self, "Folder", str(exc))

    def _refresh_all_badges(self) -> None:
        for card in self._cards.values():
            card.refresh_approval_badge()

    def _refresh_target_status(self) -> None:
        sw = get_regional_entry("sw")
        pt = get_regional_entry("pt")
        self.lbl_target.setText(
            "Target sw-CD: "
            f"{(sw.get('status') or 'not_checked')} — male={len(sw.get('target_male_voices') or [])}, "
            f"female={len(sw.get('target_female_voices') or [])}\n"
            "Target pt-AO: "
            f"{(pt.get('status') or 'not_checked')} — male={len(pt.get('target_male_voices') or [])}, "
            f"female={len(pt.get('target_female_voices') or [])}\n"
            f"SW production approved: {is_language_production_approved('sw')} · "
            f"PT production approved: {is_language_production_approved('pt')}"
        )

    def _reload_from_manifest(self) -> None:
        data = load_manifest()
        for item in data.get("auditions") or []:
            cid = item.get("candidate_id") or ""
            card = self._cards.get(cid)
            if card is not None:
                card.apply_result(item)
            if cid.startswith("sw_male_") and item.get("combined_mp3"):
                self._male_paths[cid] = item["combined_mp3"]

    def _verify_targets(self) -> None:
        self.log.append("Re-checking live Edge target locales…")
        signals = WorkerSignals()

        async def work(_w):
            sw = await discover_swahili_congo()
            pt = await discover_portuguese_angola()
            return {"sw": sw.to_dict(), "pt": pt.to_dict()}

        def done(payload):
            self.log.append(str(payload))
            self._refresh_target_status()
            self._refresh_all_badges()

        signals.finished.connect(done)
        signals.error.connect(lambda h, t: self.log.append(f"ERROR: {h}\n{t}"))
        QThreadPool.globalInstance().start(AsyncWorker(work, signals))

    def _generate_auditions(self) -> None:
        self.btn_generate.setEnabled(False)
        self.log.append("Generating four candidate auditions via Edge TTS (no Piper)…")
        signals = WorkerSignals()

        async def work(_w):
            return await generate_all_regional_auditions()

        def done(results):
            self.btn_generate.setEnabled(True)
            for r in results or []:
                data = r.to_dict() if hasattr(r, "to_dict") else dict(r)
                card = self._cards.get(data.get("candidate_id") or "")
                if card is not None:
                    card.apply_result(data)
                self.log.append(
                    f"[{data.get('label')}] ok={data.get('ok')} "
                    f"{data.get('male_voice')} / {data.get('female_voice')} "
                    f"→ {data.get('combined_mp3')}"
                )
            self._refresh_all_badges()
            QMessageBox.information(
                self,
                "Auditions ready",
                "Candidate auditions finished.\n"
                "Listen carefully, then press APPROVE THIS PAIR for the chosen fallback.\n"
                "Nothing was approved automatically.",
            )

        signals.finished.connect(done)
        signals.error.connect(
            lambda h, t: (
                self.btn_generate.setEnabled(True),
                self.log.append(f"ERROR: {h}\n{t}"),
            )
        )
        QThreadPool.globalInstance().start(AsyncWorker(work, signals))

    def _approve(self, card: _CandidateCard) -> None:
        if card.spec.get("language_id") == "sw":
            QMessageBox.information(
                self,
                "Deferred",
                "Swahili pair approval is deferred while the male voice is under review.\n"
                "Use SELECT MALE CANDIDATE only.",
            )
            return
        if card.spec.get("language_id") == "pt":
            QMessageBox.information(
                self,
                "Portuguese blocked",
                "Portuguese must stay unapproved until Angolan/native listeners review auditions.",
            )
            return
        male = card.spec.get("male_voice") or ""
        female = card.spec.get("female_voice") or ""
        if "(" in male or not male or not female or "(" in female:
            QMessageBox.warning(
                self,
                "Approve",
                "Generate auditions first so exact live voice IDs are known.",
            )
            return
        answer = QMessageBox.question(
            self,
            "Approve this pair?",
            "Approve this candidate fallback for production?\n\n"
            f"Language: {card.spec.get('language_id')}\n"
            f"Target region: "
            f"{'Congo / DRC' if card.spec.get('language_id') == 'sw' else 'Angola'}\n"
            f"Fallback locale: {card.spec.get('fallback_locale')}\n"
            f"Male: {male}\n"
            f"Female: {female}\n\n"
            "This is an explicit human decision. It will NOT be labeled as the target region.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            approve_fallback_candidate(
                card.spec["language_id"],
                fallback_locale=card.spec["fallback_locale"],
                male_voice=male,
                female_voice=female,
                candidate_id=card.spec["candidate_id"],
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Approve", str(exc))
            return
        self._refresh_all_badges()
        self._refresh_target_status()
        self.log.append(
            f"APPROVED {card.spec['language_id']}: {male} / {female} "
            f"(fallback_locale={card.spec['fallback_locale']})"
        )
        QMessageBox.information(
            self,
            "Approved",
            "Fallback pair approved.\n"
            "Daily BMT will show Ready for this language (without locale marketing labels).",
        )
