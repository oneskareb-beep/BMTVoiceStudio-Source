"""Projects page — recent projects and samples."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from bmt_voice_studio.projects.project import ProjectService
from bmt_voice_studio.ui.widgets.common import card


class ProjectsPage(QWidget):
    open_project = Signal(str)
    load_sample = Signal(str, str)  # text, preset_id

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.svc = ProjectService()
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)
        title = QLabel("Projects")
        title.setObjectName("pageTitle")
        root.addWidget(title)

        recent_card, recent_l = card("RECENT PROJECTS", "Double-click to open")
        self.list = QListWidget()
        recent_l.addWidget(self.list)
        btns = QHBoxLayout()
        self.btn_refresh = QPushButton("Refresh")
        self.btn_open = QPushButton("Open Selected")
        btns.addWidget(self.btn_refresh)
        btns.addWidget(self.btn_open)
        btns.addStretch(1)
        recent_l.addLayout(btns)
        root.addWidget(recent_card)

        sample_card, sample_l = card("SAMPLE DEVOTIONALS", "Bundled demos — no third-party audio")
        self.btn_en = QPushButton("Load English Sample (BMT ENGLISH)")
        self.btn_fr = QPushButton("Load French Sample (BMT FRENCH)")
        sample_l.addWidget(self.btn_en)
        sample_l.addWidget(self.btn_fr)
        root.addWidget(sample_card)
        root.addStretch(1)

        self.btn_refresh.clicked.connect(self.refresh)
        self.btn_open.clicked.connect(self._open)
        self.list.itemDoubleClicked.connect(lambda _: self._open())
        self.btn_en.clicked.connect(lambda: self._sample("english"))
        self.btn_fr.clicked.connect(lambda: self._sample("french"))
        self.refresh()

    def refresh(self) -> None:
        self.list.clear()
        for path in self.svc.recent():
            self.list.addItem(path)

    def _open(self) -> None:
        item = self.list.currentItem()
        if item:
            self.open_project.emit(item.text())

    def _sample(self, which: str) -> None:
        base = Path(__file__).resolve().parents[3] / "samples"
        if which == "english":
            path = base / "english_sample.txt"
            preset = "bmt_english"
        else:
            path = base / "french_sample.txt"
            preset = "bmt_french"
        if path.exists():
            self.load_sample.emit(path.read_text(encoding="utf-8"), preset)
        else:
            # Fallback inline
            if which == "english":
                text = (
                    "BELIEVERS MANNA TODAY DAILY DEVOTIONAL\n\n"
                    "Written by Apostle Doctor David A. Aderibigbe\n\n"
                    "{\nMemory Verse\n\n"
                    "But seek ye first the kingdom of God, and his righteousness; "
                    "and all these things shall be added unto you. Matthew 6:33\n}\n\n"
                    "Beloved, every day presents a fresh invitation to put God first.\n\n"
                    "{\nToday, choose His kingdom in your decisions, your words, and your worship.\n}"
                )
            else:
                text = (
                    "MANNE DES CROYANTS AUJOURD'HUI\n\n"
                    "Écrit par l'Apôtre Docteur David A. Aderibigbe\n\n"
                    "{\nVerset à mémoriser\n\n"
                    "Cherchez premièrement le royaume et la justice de Dieu; "
                    "et toutes ces choses vous seront données par-dessus. Matthieu 6:33\n}\n\n"
                    "Bien-aimés, chaque jour est une invitation à mettre Dieu en premier.\n\n"
                    "{\nAujourd'hui, choisissez Son royaume dans vos décisions et votre adoration.\n}"
                )
            self.load_sample.emit(text, preset)
