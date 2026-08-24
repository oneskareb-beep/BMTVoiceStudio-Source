"""Clickable language cards for Daily BMT — theme-driven, no inline styles."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from bmt_voice_studio.daily.language_config import (
    LanguageProductionConfig,
    normalize_selected_language_ids,
    selectable_daily_languages,
)
from bmt_voice_studio.resources import load_flag_pixmap


class LanguageToggleCard(QFrame):
    """Clickable language card with real flag icon + name / selection / readiness."""

    toggled = Signal(bool)

    def __init__(self, config: LanguageProductionConfig, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self._checked = False
        self.setObjectName("languageToggleCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumWidth(250)
        self.setMinimumHeight(118)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(6)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(10)

        flag = QLabel()
        flag.setObjectName("languageFlag")
        flag.setFixedSize(44, 30)
        flag.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tip = {
            "en": "English",
            "fr": "French",
            "sw": "Swahili",
            "pt": "Portuguese",
        }.get(config.language_id, config.display_name)
        flag.setToolTip(tip)
        pix = load_flag_pixmap(config.language_id, max_width=40, max_height=26)
        if pix is not None and not pix.isNull():
            flag.setPixmap(pix)
        else:
            flag.setText(config.short_code or config.language_id.upper())
            flag.setObjectName("appSubtitle")

        code = QLabel(config.short_code or config.language_id.upper())
        code.setObjectName("appSubtitle")
        code.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        header.addWidget(flag, 0)
        header.addWidget(code, 0)
        header.addStretch(1)

        self.title = QLabel(config.display_name)
        self.title.setObjectName("cardTitle")
        self.title.setWordWrap(True)
        self.title.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        self.state = QLabel("○ Not selected")
        self.state.setObjectName("appSubtitle")
        self.state.setWordWrap(True)

        self.readiness = QLabel(config.readiness_state())
        self.readiness.setObjectName("appSubtitle")
        self.readiness.setWordWrap(True)

        lay.addLayout(header)
        lay.addWidget(self.title)
        lay.addWidget(self.state)
        lay.addWidget(self.readiness)
        lay.addStretch(1)
        self._refresh_style()

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, checked: bool) -> None:
        checked = bool(checked)
        if self._checked == checked:
            self._refresh_style()
            return
        self._checked = checked
        self._refresh_style()
        self.toggled.emit(self._checked)

    def refresh_readiness(self) -> None:
        self.readiness.setText(self.config.readiness_state())

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.setChecked(not self._checked)
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.setChecked(not self._checked)
            event.accept()
            return
        super().keyPressEvent(event)

    def _refresh_style(self) -> None:
        self.state.setText("✓ Selected" if self._checked else "○ Not selected")
        self.setProperty("selected", "true" if self._checked else "false")
        style = self.style()
        if style is not None:
            style.unpolish(self)
            style.polish(self)
        self.update()


class LanguageSelector(QWidget):
    """Languages to generate — multi-select cards with responsive grid."""

    selection_changed = Signal(list)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._cards: dict[str, LanguageToggleCard] = {}
        self._columns = 2
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        hint = QLabel("Select one or more languages for today's devotional.")
        hint.setObjectName("appSubtitle")
        hint.setWordWrap(True)
        root.addWidget(hint)

        self._grid_host = QWidget()
        self._grid = QGridLayout(self._grid_host)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(12)
        self._grid.setVerticalSpacing(12)
        for cfg in selectable_daily_languages():
            card = LanguageToggleCard(cfg)
            card.toggled.connect(self._on_toggled)
            self._cards[cfg.language_id] = card
        root.addWidget(self._grid_host)
        self._relayout_cards()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._relayout_cards()

    def _desired_columns(self) -> int:
        width = max(self.width(), self._grid_host.width())
        if width >= 1120:
            return 4
        return 2

    def _relayout_cards(self) -> None:
        cols = self._desired_columns()
        self._columns = cols
        while self._grid.count():
            item = self._grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(self._grid_host)
        for index, cfg in enumerate(selectable_daily_languages()):
            card = self._cards[cfg.language_id]
            self._grid.addWidget(card, index // cols, index % cols)

    def selected_ids(self) -> list[str]:
        return normalize_selected_language_ids(
            [lid for lid, card in self._cards.items() if card.isChecked()]
        )

    def set_selected_ids(self, ids: list[str]) -> None:
        chosen = set(normalize_selected_language_ids(ids))
        for lid, card in self._cards.items():
            card.blockSignals(True)
            card._checked = lid in chosen
            card._refresh_style()
            card.blockSignals(False)
        if not self.selected_ids():
            en = self._cards.get("en")
            if en is not None:
                en.blockSignals(True)
                en._checked = True
                en._refresh_style()
                en.blockSignals(False)
        self.refresh_readiness()

    def refresh_readiness(self) -> None:
        for card in self._cards.values():
            card.refresh_readiness()

    def _on_toggled(self, _checked: bool = False) -> None:
        selected = [lid for lid, card in self._cards.items() if card.isChecked()]
        if not selected:
            sender = self.sender()
            if isinstance(sender, LanguageToggleCard):
                sender.blockSignals(True)
                sender._checked = True
                sender._refresh_style()
                sender.blockSignals(False)
        self.selection_changed.emit(self.selected_ids())
