"""Centralized design tokens and stylesheets for BMT Voice Studio.

Visual / UX only — do not put business logic here.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Spacing:
    xs: int = 4
    sm: int = 8
    md: int = 12
    lg: int = 16
    xl: int = 24
    section: int = 18
    card_pad_x: int = 18
    card_pad_y: int = 16
    card_gap: int = 10
    header_pad_x: int = 20
    header_pad_y: int = 10
    page_margin: int = 18
    column_gutter: int = 16


@dataclass(frozen=True)
class Radius:
    small: int = 6
    medium: int = 8
    large: int = 12
    card: int = 12
    badge: int = 10
    pill: int = 999


@dataclass(frozen=True)
class TypeScale:
    page_title: int = 26
    section_title: int = 18
    card_title: int = 15
    body: int = 13
    secondary: int = 12
    metadata: int = 12
    button: int = 13
    status: int = 12


@dataclass(frozen=True)
class ControlHeight:
    small: int = 28
    standard: int = 34
    primary: int = 44
    line_edit: int = 34
    combo: int = 34


@dataclass(frozen=True)
class Colors:
    # Surfaces
    app_bg: str = "#0F141C"
    surface: str = "#151E2A"
    elevated: str = "#1B2736"
    border: str = "#243041"
    border_strong: str = "#2A3A4F"
    # Text
    text_primary: str = "#F2F6FC"
    text_body: str = "#E8EDF5"
    text_secondary: str = "#A9B8CC"
    text_muted: str = "#8FA0B6"
    text_disabled: str = "#6B7A8F"
    # Accents
    blue_primary: str = "#1E5BB8"
    blue_hover: str = "#2F6FED"
    blue_focus: str = "#3D6FB8"
    gold: str = "#D4A017"
    gold_soft: str = "#F0C040"
    # Status
    success: str = "#2E9A6A"
    success_text: str = "#7FD99A"
    warning: str = "#E6C15A"
    error: str = "#B44545"
    error_text: str = "#F07178"
    info: str = "#7EC8FF"
    # Misc
    track: str = "#0C121A"
    navy: str = "#101820"
    selected_fill: str = "#1E3A5F"


SPACE = Spacing()
RADIUS = Radius()
TYPE = TypeScale()
HEIGHT = ControlHeight()
COLOR = Colors()

# Stable production release — never overwrite / mutate this ZIP in UI polish work.
STABLE_130_ZIP_NAME = "BMTVoiceStudio-1.3.0-Windows-x64-Portable.zip"
STABLE_130_SHA256 = "f3c9591220adc645f22365dda1e669658e155308978215e93389b18fb8d95db9"


def _dark_qss() -> str:
    c = COLOR
    r = RADIUS
    t = TYPE
    h = HEIGHT
    return f"""
* {{
  font-family: "Segoe UI", "Bahnschrift", "Trebuchet MS", sans-serif;
  font-size: {t.body}px;
  color: {c.text_body};
}}
QMainWindow, QDialog, QWidget#centralRoot {{
  background-color: {c.app_bg};
}}
QMenuBar {{
  background-color: {c.surface};
  color: {c.text_body};
  border-bottom: 1px solid {c.border};
  padding: 2px 6px;
  spacing: 4px;
}}
QMenuBar::item {{
  background: transparent;
  padding: 6px 10px;
  border-radius: {r.small}px;
}}
QMenuBar::item:selected {{
  background-color: {c.elevated};
}}
QMenu {{
  background-color: {c.surface};
  color: {c.text_body};
  border: 1px solid {c.border_strong};
  border-radius: {r.medium}px;
  padding: 6px;
}}
QMenu::item {{
  padding: 8px 28px 8px 14px;
  border-radius: {r.small}px;
}}
QMenu::item:selected {{
  background-color: {c.selected_fill};
}}
QMenu::separator {{
  height: 1px;
  background: {c.border};
  margin: 6px 8px;
}}
QWidget#jobProgressStrip {{
  background-color: {c.surface};
  border-bottom: 1px solid {c.border};
}}
QLabel#jobProgressLabel {{
  color: {c.text_primary};
  font-size: {t.secondary}px;
  font-weight: 600;
}}
QProgressBar#jobProgressBar {{
  min-height: 22px;
  max-height: 24px;
  font-size: 13px;
}}
QLabel#logoPreviewCard {{
  background-color: #F3E6C4;
  border: 1px solid {c.border_strong};
  border-radius: {r.medium}px;
}}
QLabel#captionPreviewStage {{
  background-color: {c.navy};
  border: 1px solid {c.border_strong};
  border-radius: {r.medium}px;
}}
QWidget#musicTrackCrop {{
  background-color: {c.elevated};
  border: 1px solid {c.border};
  border-radius: {r.medium}px;
}}
QWidget#appHeader {{
  background-color: {c.surface};
  border-bottom: 1px solid {c.border};
}}
QWidget#pageHeader {{
  background-color: {c.app_bg};
  border-bottom: 1px solid {c.border};
}}
QFrame#histCollapseBar {{
  background-color: {c.surface};
  border: 1px solid {c.border};
  border-radius: {r.medium}px;
}}
QWidget#studioTimeline {{
  background-color: {c.surface};
  border: 1px solid {c.border};
  border-radius: {r.medium}px;
}}
QLabel#headerDate {{
  font-size: {t.body}px;
  font-weight: 600;
  color: {c.text_primary};
}}
QLabel#languageFlag {{
  border: 1px solid rgba(255,255,255,0.18);
  border-radius: 3px;
  background: rgba(0,0,0,0.12);
}}
QWidget#workspaceSwitch {{
  background-color: {c.track};
  border: 1px solid {c.border};
  border-radius: {r.medium}px;
}}
QLabel#appTagline {{
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.8px;
  color: {c.text_muted};
}}
QLabel#appTitle {{
  font-size: 20px;
  font-weight: 700;
  color: {c.text_primary};
  letter-spacing: 0.2px;
}}
QLabel#pageTitle {{
  font-size: {t.page_title}px;
  font-weight: 700;
  color: {c.text_primary};
}}
QLabel#sectionTitle {{
  font-size: {t.section_title}px;
  font-weight: 700;
  color: {c.text_primary};
}}
QLabel#appSubtitle {{
  font-size: {t.secondary}px;
  color: {c.text_muted};
}}
QLabel#metaLabel {{
  font-size: {t.metadata}px;
  font-weight: 600;
  color: {c.text_muted};
}}
QLabel#valueLabel {{
  font-size: {t.body}px;
  font-weight: 600;
  color: {c.text_primary};
}}
QLabel#topicValue {{
  font-size: 16px;
  font-weight: 700;
  color: {c.text_primary};
}}
QLabel#brandLogo {{
  background: transparent;
  padding: 0;
}}
QLabel#fieldLabel {{
  font-size: {t.secondary}px;
  font-weight: 600;
  color: {c.text_secondary};
  padding-bottom: 2px;
}}
QLabel#taskLabel {{
  font-size: {t.body}px;
  color: {c.text_secondary};
}}
QLabel#statusBadge {{
  font-size: 11px;
  font-weight: 700;
  padding: 1px 8px;
  border-radius: 9px;
  background-color: {c.elevated};
  color: {c.text_secondary};
  border: 1px solid {c.border};
  max-height: 20px;
}}
QLabel#statusBadge[state="ready"], QLabel#statusBadge[state="complete"] {{
  background-color: #163528;
  color: {c.success_text};
  border-color: {c.success};
}}
QLabel#statusBadge[state="selected"], QLabel#statusBadge[state="rendering"] {{
  background-color: {c.selected_fill};
  color: {c.info};
  border-color: {c.blue_focus};
}}
QLabel#statusBadge[state="waiting"], QLabel#statusBadge[state="empty"] {{
  background-color: {c.elevated};
  color: {c.text_muted};
  border-color: {c.border};
}}
QLabel#statusBadge[state="warning"], QLabel#statusBadge[state="missing"] {{
  background-color: #3A3018;
  color: {c.warning};
  border-color: #8A7428;
}}
QLabel#statusBadge[state="failed"], QLabel#statusBadge[state="error"] {{
  background-color: #3A1A1A;
  color: {c.error_text};
  border-color: {c.error};
}}
QLabel#emptyStateTitle {{
  font-size: 15px;
  font-weight: 700;
  color: {c.text_primary};
}}
QLabel#emptyStateBody {{
  font-size: {t.secondary}px;
  color: {c.text_muted};
}}
QPushButton {{
  background-color: {c.elevated};
  border: 1px solid {c.border_strong};
  border-radius: {r.medium}px;
  padding: 7px 14px;
  min-height: {h.standard}px;
  color: {c.text_body};
  font-size: {t.button}px;
  font-weight: 600;
}}
QPushButton:hover {{
  background-color: #243447;
  border-color: #3D5573;
}}
QPushButton:pressed {{
  background-color: #162030;
}}
QPushButton:disabled {{
  color: {c.text_disabled};
  background-color: #151C27;
  border-color: #222C3A;
}}
QPushButton:focus {{
  border: 1px solid {c.blue_focus};
}}
QPushButton#modeButton {{
  text-align: center;
  padding: 6px 14px;
  min-height: 30px;
  max-height: 32px;
  border-radius: {r.small}px;
  background: transparent;
  border: 1px solid transparent;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.5px;
  color: {c.text_muted};
}}
QPushButton#modeButton:hover {{
  background-color: {c.elevated};
  color: {c.text_body};
  border-color: {c.border};
}}
QPushButton#modeButton:pressed {{
  background-color: #162030;
}}
QPushButton#modeButton:checked {{
  background-color: {c.selected_fill};
  color: {c.text_primary};
  border: 1px solid {c.gold};
}}
QPushButton#modeButton:focus {{
  border: 1px solid {c.blue_focus};
}}
QPushButton#templateCard {{
  text-align: center;
  font-weight: 700;
  letter-spacing: 0.3px;
  min-height: 56px;
  padding: 10px 8px;
  background: {c.navy};
  border: 1px solid {c.border};
  border-radius: {r.medium}px;
}}
QPushButton#templateCard:hover {{
  border-color: #3D5573;
  background-color: #13202C;
}}
QPushButton#templateCard:checked {{
  background-color: {c.selected_fill};
  border: 1px solid {c.gold};
  color: {c.text_primary};
}}
QToolButton#templateChip {{
  background: {c.navy};
  border: 1px solid {c.border};
  border-radius: {r.small}px;
  padding: 3px 2px 2px 2px;
  min-width: 62px;
  max-width: 72px;
  min-height: 104px;
  max-height: 114px;
  font-size: 10px;
  font-weight: 700;
  color: {c.text_secondary};
}}
QToolButton#templateChip:hover {{
  border-color: #3D5573;
  background-color: #13202C;
}}
QToolButton#templateChip:checked {{
  background-color: {c.selected_fill};
  border: 1px solid {c.gold};
  color: {c.text_primary};
}}
QToolButton#disclosureButton {{
  background-color: {c.navy};
  border: 1px solid {c.border};
  border-radius: {r.small}px;
  padding: 2px 8px;
  min-height: 26px;
  max-height: 28px;
  font-size: 11px;
  font-weight: 600;
  color: {c.text_secondary};
}}
QToolButton#disclosureButton:hover {{
  border-color: #3D5573;
  background-color: #13202C;
}}
QToolButton#disclosureButton:checked {{
  background-color: {c.selected_fill};
  border: 1px solid {c.gold};
  color: {c.text_primary};
}}
QWidget#mediaAddPanel {{
  background-color: {c.track};
  border: 1px dashed {c.border};
  border-radius: {r.small}px;
}}
QPushButton#primaryButton {{
  background-color: {c.blue_primary};
  border: 1px solid {c.blue_primary};
  color: white;
  font-weight: 700;
  font-size: 14px;
  padding: 10px 18px;
  min-height: {h.primary}px;
  border-radius: {r.medium}px;
}}
QPushButton#primaryButton:hover {{
  background-color: {c.blue_hover};
  border-color: {c.gold_soft};
}}
QPushButton#primaryButton:pressed {{
  background-color: #174A96;
}}
QPushButton#primaryButton:disabled {{
  color: #9AA8BA;
  background-color: #243447;
  border-color: #2A3A4F;
}}
QPushButton#secondaryButton {{
  background-color: #243447;
  border: 1px solid #3D5573;
  font-weight: 600;
  min-height: {h.standard}px;
}}
QPushButton#secondaryButton:hover {{
  background-color: #2C4158;
  border-color: {c.blue_hover};
}}
QPushButton#tertiaryButton {{
  background-color: transparent;
  border: 1px solid {c.border_strong};
  color: {c.text_secondary};
  min-height: {h.small}px;
  font-weight: 600;
}}
QPushButton#tertiaryButton:hover {{
  background-color: #1A2433;
  color: {c.text_body};
}}
QToolButton#iconButton {{
  background-color: transparent;
  border: none;
  border-radius: {r.small}px;
  padding: 4px;
  min-width: 28px;
  max-width: 32px;
  min-height: 28px;
  max-height: 32px;
  color: {c.text_secondary};
}}
QToolButton#iconButton:hover {{
  background-color: #1A2433;
}}
QToolButton#iconButton:pressed {{
  background-color: #162030;
}}
QToolButton#iconButton:checked {{
  background-color: {c.selected_fill};
}}
QToolButton#iconButton:disabled {{
  background-color: transparent;
}}
QPushButton#dangerButton {{
  background-color: #8B2E2E;
  border: 1px solid {c.error};
  color: white;
  font-weight: 700;
}}
QPushButton#dangerButton:hover {{
  background-color: #A33838;
}}
QPushButton#successButton {{
  background-color: #1F6B4A;
  border: 1px solid {c.success};
  color: white;
  font-weight: 700;
}}
QFrame#card {{
  background-color: {c.surface};
  border: 1px solid {c.border};
  border-radius: {r.card}px;
}}
QFrame#playerFrame {{
  background-color: {c.navy};
  border: 1px solid {c.border};
  border-radius: {r.medium}px;
}}
QFrame#previewStage, QLabel#previewStage, QWidget#previewStage {{
  background-color: {c.navy};
  border: 1px solid {c.border};
  border-radius: {r.medium}px;
}}
QFrame#audioRow {{
  background-color: {c.track};
  border: 1px solid {c.border};
  border-radius: {r.small}px;
}}
QFrame#audioRow[selected="true"] {{
  border: 1px solid {c.gold};
  background-color: {c.selected_fill};
}}
QLabel#cardTitle {{
  font-size: {t.card_title}px;
  font-weight: 700;
  color: {c.text_primary};
  min-height: 22px;
  padding: 0px;
  margin: 0px;
}}
QLabel#cardHint {{
  color: {c.text_muted};
  font-size: {t.secondary}px;
}}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QDateEdit {{
  background-color: {c.track};
  border: 1px solid {c.border_strong};
  border-radius: {r.medium}px;
  padding: 6px 10px;
  min-height: {h.line_edit - 12}px;
  selection-background-color: {c.blue_hover};
}}
QComboBox {{
  min-height: {h.combo - 12}px;
  padding-right: 28px;
}}
QComboBox::drop-down {{
  border: none;
  width: 28px;
}}
QComboBox::down-arrow {{
  width: 10px;
  height: 10px;
}}
QComboBox QAbstractItemView {{
  background-color: {c.surface};
  color: {c.text_body};
  border: 1px solid {c.border_strong};
  selection-background-color: {c.selected_fill};
  selection-color: {c.text_primary};
  outline: 0;
  padding: 4px;
}}
QPlainTextEdit, QTextEdit {{
  background-color: {c.track};
  border: 1px solid {c.border_strong};
  border-radius: {r.medium}px;
  padding: 10px 12px;
  selection-background-color: {c.blue_hover};
  line-height: 1.45;
}}
QListWidget, QTreeWidget, QTableWidget {{
  background-color: {c.track};
  border: 1px solid {c.border_strong};
  border-radius: {r.medium}px;
  padding: 4px;
  selection-background-color: {c.blue_hover};
  gridline-color: {c.border};
  alternate-background-color: #121A24;
}}
QHeaderView::section {{
  background-color: {c.surface};
  color: {c.text_secondary};
  border: none;
  border-bottom: 1px solid {c.border};
  border-right: 1px solid {c.border};
  padding: 8px 10px;
  font-weight: 700;
  font-size: {t.secondary}px;
}}
QTableWidget::item {{
  padding: 6px 8px;
}}
QTableWidget::item:selected {{
  background-color: {c.selected_fill};
  color: {c.text_primary};
}}
QTableWidget::item:hover {{
  background-color: #1A2740;
}}
QPlainTextEdit:focus, QTextEdit:focus, QLineEdit:focus, QComboBox:focus,
QListWidget:focus, QDateEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
  border: 1px solid {c.blue_focus};
}}
QListWidget#mediaStrip {{
  background-color: {c.track};
  padding: 4px;
}}
QListWidget#mediaStrip::item {{
  padding: 3px;
  border: 1px solid {c.border};
  border-radius: {r.small}px;
  margin: 2px;
}}
QListWidget#mediaStrip::item:hover {{
  border-color: #3D5573;
  background-color: #13202C;
}}
QListWidget#mediaStrip::item:selected {{
  border: 1px solid {c.gold};
  background-color: {c.selected_fill};
}}
QListWidget::item {{
  padding: 8px;
  border-radius: {r.small}px;
}}
QListWidget::item:selected {{
  background-color: {c.selected_fill};
}}
QListWidget::item:hover {{
  background-color: #1A2740;
}}
QProgressBar {{
  border: 1px solid {c.border_strong};
  border-radius: {r.medium}px;
  background: {c.track};
  text-align: center;
  color: {c.text_primary};
  font-weight: 600;
  min-height: 16px;
  max-height: 18px;
}}
QProgressBar::chunk {{
  background-color: {c.blue_hover};
  border-radius: 7px;
}}
QProgressBar[state="success"]::chunk {{
  background-color: {c.success};
}}
QProgressBar[state="error"]::chunk {{
  background-color: {c.error};
}}
QSlider::groove:horizontal {{
  height: 6px;
  background: {c.border};
  border-radius: 3px;
}}
QSlider::sub-page:horizontal {{
  background: {c.blue_hover};
  border-radius: 3px;
}}
QSlider::handle:horizontal {{
  width: 14px;
  margin: -5px 0;
  border-radius: 7px;
  background: {c.blue_hover};
  border: 1px solid #A8C4FF;
}}
QSlider::handle:horizontal:hover {{
  background: #6BA0FF;
}}
QSlider::handle:horizontal:disabled {{
  background: #3A4A5C;
  border-color: #2A3A4F;
}}
QScrollArea {{
  border: none;
  background: transparent;
}}
QScrollBar:vertical {{
  background: {c.surface};
  width: 12px;
  margin: 2px;
}}
QScrollBar::handle:vertical {{
  background: #2A3A4F;
  border-radius: 5px;
  min-height: 28px;
}}
QScrollBar::handle:vertical:hover {{
  background: #3D5573;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
  height: 0;
}}
QScrollBar:horizontal {{
  background: transparent;
  height: 10px;
  margin: 2px;
}}
QScrollBar::handle:horizontal {{
  background: #2A3A4F;
  border-radius: 5px;
  min-width: 28px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
  width: 0;
}}
QStatusBar {{
  background: {c.surface};
  color: {c.text_muted};
  border-top: 1px solid {c.border};
}}
QToolTip {{
  background-color: {c.elevated};
  color: {c.text_body};
  border: 1px solid #3D5573;
  padding: 6px 8px;
  border-radius: {r.small}px;
}}
QCheckBox, QRadioButton, QLabel {{
  background: transparent;
}}
QCheckBox {{
  spacing: 8px;
  min-height: 22px;
}}
QCheckBox::indicator, QRadioButton::indicator {{
  width: 16px;
  height: 16px;
  border-radius: 4px;
  border: 1px solid {c.border_strong};
  background: {c.track};
}}
QCheckBox::indicator:checked {{
  background-color: {c.blue_primary};
  border-color: {c.blue_hover};
}}
QCheckBox::indicator:disabled {{
  background-color: #151C27;
  border-color: #222C3A;
}}
QGroupBox {{
  border: 1px solid {c.border};
  border-radius: {r.medium}px;
  margin-top: 12px;
  padding-top: 10px;
}}
QGroupBox::title {{
  subcontrol-origin: margin;
  left: 12px;
  padding: 0 6px;
  color: {c.text_secondary};
}}
QTabWidget::pane {{
  border: 1px solid {c.border};
  border-radius: {r.medium}px;
  background: {c.surface};
}}
QTabBar::tab {{
  background: {c.surface};
  border: 1px solid {c.border};
  padding: 8px 14px;
  margin-right: 4px;
  border-top-left-radius: {r.medium}px;
  border-top-right-radius: {r.medium}px;
}}
QTabBar::tab:selected {{
  background: {c.selected_fill};
}}
QFrame#languageToggleCard {{
  background-color: {c.track};
  border: 1px solid {c.border};
  border-radius: {r.card}px;
}}
QFrame#languageToggleCard[selected="true"] {{
  border: 1px solid {c.gold};
  background-color: {c.selected_fill};
}}
QFrame#languageToggleCard[selected="false"] {{
  border: 1px solid {c.border};
  background-color: {c.track};
}}
"""


DARK_QSS = _dark_qss()

LIGHT_QSS = """
* {
  font-family: "Segoe UI", "Bahnschrift", "Trebuchet MS", sans-serif;
  font-size: 13px;
  color: #1A2433;
}
QMainWindow, QDialog, QWidget#centralRoot { background-color: #F3F6FA; }
QMenuBar { background: #FFFFFF; color: #1A2433; border-bottom: 1px solid #D5DEE9; }
QMenu { background: #FFFFFF; color: #1A2433; border: 1px solid #C9D4E3; }
QMenu::item:selected { background: #E8F0FE; }
QWidget#appHeader { background-color: #FFFFFF; border-bottom: 1px solid #D5DEE9; }
QLabel#appTitle, QLabel#pageTitle { font-size: 24px; font-weight: 700; }
QLabel#appSubtitle, QLabel#metaLabel { font-size: 12px; color: #5C6B7F; }
QLabel#valueLabel, QLabel#topicValue { font-weight: 700; color: #1A2433; }
QPushButton {
  background-color: #FFFFFF; border: 1px solid #C9D4E3; border-radius: 8px;
  padding: 8px 14px; min-height: 32px;
}
QPushButton#modeButton {
  text-align: center; padding: 6px 14px; min-height: 30px; border-radius: 6px;
  background: transparent; font-size: 11px; font-weight: 700;
}
QPushButton#modeButton:checked {
  background-color: #E8F0FE; border: 1px solid #D4A017; color: #1A2433;
}
QPushButton#primaryButton {
  background-color: #2F6FED; border: 1px solid #2F6FED; color: white;
  font-weight: 700; padding: 10px 18px; min-height: 44px;
}
QPushButton#secondaryButton { background-color: #E8EEF6; border: 1px solid #C9D4E3; font-weight: 600; }
QPushButton#tertiaryButton { background-color: transparent; border: 1px solid #C9D4E3; }
QToolButton#iconButton {
  background-color: transparent; border: none; border-radius: 6px;
  padding: 4px; min-width: 28px; max-width: 32px; min-height: 28px; max-height: 32px;
}
QToolButton#iconButton:hover { background-color: #E8EEF6; }
QToolButton#iconButton:checked { background-color: #E8F0FE; }
QToolButton#templateChip {
  background: #FFFFFF; border: 1px solid #C9D4E3; border-radius: 6px;
  padding: 3px 2px; min-width: 62px; max-width: 72px; min-height: 104px; max-height: 114px;
  font-size: 10px; font-weight: 700;
}
QToolButton#templateChip:checked { background-color: #E8F0FE; border: 1px solid #D4A017; }
QToolButton#disclosureButton {
  background: #FFFFFF; border: 1px solid #C9D4E3; border-radius: 6px;
  padding: 2px 8px; min-height: 26px; max-height: 28px; font-size: 11px; font-weight: 600;
}
QToolButton#disclosureButton:checked { background-color: #E8F0FE; border: 1px solid #D4A017; }
QWidget#mediaAddPanel { background: #F7F9FC; border: 1px dashed #C9D4E3; border-radius: 6px; }
QPushButton#dangerButton { background-color: #C62828; color: white; border: 1px solid #B71C1C; }
QFrame#card { background-color: #FFFFFF; border: 1px solid #D5DEE9; border-radius: 12px; }
QFrame#playerFrame, QFrame#previewStage { background-color: #F7F9FC; border: 1px solid #D5DEE9; border-radius: 8px; }
QLabel#cardTitle { font-size: 15px; font-weight: 700; }
QLabel#cardHint { color: #5C6B7F; font-size: 12px; }
QLineEdit, QComboBox, QDateEdit, QSpinBox, QDoubleSpinBox {
  background-color: #FFFFFF; border: 1px solid #C9D4E3; border-radius: 8px; padding: 6px 10px;
}
QComboBox QAbstractItemView {
  background-color: #FFFFFF; color: #1A2433; border: 1px solid #C9D4E3;
  selection-background-color: #E8F0FE;
}
QPlainTextEdit, QTextEdit, QListWidget, QTableWidget {
  background-color: #FFFFFF; border: 1px solid #C9D4E3; border-radius: 8px; padding: 8px;
}
QHeaderView::section { background: #F3F6FA; color: #5C6B7F; padding: 8px; border: none; border-bottom: 1px solid #D5DEE9; }
QScrollArea { border: none; background: transparent; }
QProgressBar { min-height: 16px; max-height: 18px; }
"""


def apply_theme(app, theme: str = "dark") -> None:
    app.setStyle("Fusion")
    app.setStyleSheet(DARK_QSS if theme != "light" else LIGHT_QSS)


def set_badge_state(label, state: str) -> None:
    """Apply a status badge visual state without inline color strings."""
    label.setObjectName("statusBadge")
    label.setProperty("state", (state or "waiting").lower())
    style = label.style()
    if style is not None:
        style.unpolish(label)
        style.polish(label)
    label.update()
