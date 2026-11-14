"""Offline desktop reader with bounded thumbnail/preview memory and background imports.

All Qt widgets and QPixmaps stay on the GUI thread. Background workers only touch
files and Pillow/PDFium objects. No network access is used by the application.
"""
from __future__ import annotations

from . import __version__

import sys
import json
import math
import copy
from uuid import uuid4
import threading
import shutil
from pathlib import Path
import time
from urllib.parse import urlsplit

from PySide6.QtCore import (Qt, QSize, QTimer, QSettings, QUrl, Signal, QPoint, QPointF, QRectF, QEvent, QSignalBlocker,
                            QPropertyAnimation, QEasingCurve, QThreadPool, QVariantAnimation, QRect, QAbstractAnimation, QMimeData)
from PySide6.QtGui import (QAction, QBrush, QColor, QDesktopServices, QIcon, QPainter, QPen,
                           QKeySequence, QPixmap, QFont, QPainterPath, QImage, QImageReader, QShortcut, QTextCursor, QTextDocument, QPen, QLinearGradient, QCursor, QPalette, QDrag, QUndoStack, QUndoCommand)
from PySide6.QtWidgets import (
    QApplication, QAbstractItemView, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QGraphicsPixmapItem, QGraphicsScene, QGraphicsView, QGraphicsRectItem, QGraphicsPathItem, QGraphicsEllipseItem, QGraphicsItem, QGraphicsSimpleTextItem,
    QHBoxLayout, QBoxLayout, QInputDialog, QLabel, QListWidget, QListWidgetItem,
    QMainWindow, QMessageBox, QPushButton, QSplitter, QStatusBar, QTabWidget, QTabBar, QScrollArea, QTreeWidget, QStackedWidget,
    QToolBar, QVBoxLayout, QWidget, QToolButton, QGraphicsOpacityEffect,
    QFontComboBox, QSpinBox, QDoubleSpinBox, QSlider, QWidgetAction, QCheckBox, QColorDialog, QMenu, QSizePolicy, QFrame, QGridLayout, QStyledItemDelegate, QStyleOptionViewItem, QStackedLayout, QLineEdit, QStyle, QProgressBar, QProgressDialog, QPlainTextEdit,
)
from .editor import NotesEditor
from .notes_layout import NotesPageSetup
from .notes_layout_dialog import NotesPageSetupDialog
from .platform_shortcuts import IS_MAC, PRIMARY, ALT, SHIFT, docs_shortcut
from .ui import FlowLayout, WrapBar, YomuWordmark, SaveToast, SoftButtonMotion, ColourDotButton, line_icon, FocusTimer, FocusFlower, ConfettiOverlay, ReadingProgressBar, KawaiiNotice
from .importers import (ALL_EXTS, blank_page, import_document, image_for_page,
                        clear_obsolete_preview_tiers, LARGE_THUMB_MAX_WIDTH)
from .project import Project, PANEL_KEYS, valid_panel_order, short_id, validated_note_pages
from .reading_view import (empty_view, effective_zoom, remember_zoom,
                           normalise_zoom, fit_zoom, root_for_page,
                           root_for_group, pages_in_group,
                           set_page_independent, set_root_shared)
from .page_groups_ui import PageGroupsTree, ROLE_KIND, ROLE_ID
from .reading_progress import (group_counts, set_read_status,
                               percentage, notebook_totals)
from .reading_rewards import (celebration_message, crossed_milestone,
                              MILESTONE_MESSAGES)
from .import_labels import label_imported_pages, make_title
from .import_planning import plan_import
from .import_options_dialog import ImportOptionsDialog
from .import_review_dialog import SmartImportReviewDialog
from .import_structure import detected_structure
from .import_staging import cleanup_uncommitted
from .page_groups import (
    flat_tree, flatten, validate as validate_group_tree,
    reconcile as reconcile_group_tree, group_pages as wrap_group_pages,
    group_node, add_group as insert_group_node,
    rename_group as change_group_name,
    move_pages_to_group, move_pages_to_root, ungroup as dissolve_group,
    remove_group_and_pages, set_collapsed, move_group, page_node,
)
from .notebook import Notebook, MAX_TABS, default_backup_folder
from .tab_exchange import (inspect_notebook, stage_import, commit_import,
                           set_batch_present, export_tabs)
from .tab_exchange_dialog import TabExchangeDialog
from .tasks import start_task
from .lifecycle import RetiredNotebookQueue
from .diagnostics import logger, log_folder
from .resampling import bicubic_rgb_crop, MAX_UPSCALE_SOURCE_PIXELS, MAX_UPSCALE_OUTPUT_PIXELS
from .preview_clarity import sharpen_cached_preview, MODES as CLARITY_MODES
from .history import UnifiedHistory, CallbackAction, external_undo_action, rename_action, reorder_pages_action
from .vector_marks import (make_stroke, make_shape, make_highlight, make_highlight_line, translated_vector,
                           resized_vector, MAX_STROKE_POINTS,
                           add_mark, remove_stroke, restore_stroke, valid_vector)
from .layout_geometry import fit_inside, is_near_native_pixel_ratio
from .tab_strip import inline_add_position
from .ocr_engine import (MAX_REGIONS, OCR_DPI, find_tesseract, installed_languages,
                         recognise_regions, OCRCancelled)

THUMB_LIMIT = 20
# Only one large page pixmap stays in RAM. Adjacent pages are pre-rendered on disk.
NEIGHBOUR_DISK_PREFETCH = 1

# Modern stationery palette: quiet surfaces, bolder accessible ink and clear borders.
# Keep stable theme IDs for saved preferences. The PDF and project data are NOT themed.
THEMES = {
    'washi': {'name': 'Sakura Washi', 'window': '#f3e8ec', 'panel': '#fff8fa', 'paper': '#fffefd',
              'shelf': '#ebdfe7', 'canvas': '#ece9ec', 'ink': '#38374c', 'muted': '#665b70',
              'accent': '#c74879', 'accent2': '#db815d', 'border': '#c7b5c1',
              'highlight': '#f4d6e2', 'btn': '#fffdfc', 'btn2': '#f7dce6', 'preview': '#e4e1e8'},
    'indigo': {'name': 'Midnight Indigo', 'window': '#192538', 'panel': '#25344a', 'paper': '#2b394e',
               'shelf': '#1b2b40', 'canvas': '#1c293b', 'ink': '#f7f3fb', 'muted': '#c2ccde',
               'accent': '#f096c3', 'accent2': '#8acddd', 'border': '#627087',
               'highlight': '#43516b', 'btn': '#33465b', 'btn2': '#475a72', 'preview': '#18202e'},
    'matcha': {'name': 'Matcha Garden', 'window': '#e7ecdf', 'panel': '#f5f7ef', 'paper': '#fffef9',
               'shelf': '#d8e2d3', 'canvas': '#e6ece3', 'ink': '#283d35', 'muted': '#526457',
               'accent': '#357753', 'accent2': '#cb7650', 'border': '#aabdab',
               'highlight': '#cbe5d0', 'btn': '#fffdf5', 'btn2': '#e0eddf', 'preview': '#dce4db'},
    'yuzu': {'name': 'Yuzu Pop', 'window': '#f3e9db', 'panel': '#fff7ee', 'paper': '#fffefa',
             'shelf': '#f0dfc8', 'canvas': '#f4ede4', 'ink': '#4d3948', 'muted': '#776174',
             'accent': '#bd5173', 'accent2': '#b98028', 'border': '#cfb8aa',
             'highlight': '#f9dfb2', 'btn': '#fffdf8', 'btn2': '#f8e7ca', 'preview': '#eae0d8'},
    'lilac': {'name': 'Lilac Dream', 'window': '#ebe5f1', 'panel': '#faf7fd', 'paper': '#fffefe',
              'shelf': '#ded6e9', 'canvas': '#eeebf3', 'ink': '#403954', 'muted': '#675b80',
              'accent': '#8050b0', 'accent2': '#c5699a', 'border': '#c6b8d5',
              'highlight': '#e5d6f8', 'btn': '#fffcff', 'btn2': '#eadff4', 'preview': '#e2dfea'},
    'modern-light': {'name': 'Modern Light', 'window': '#e9edf1', 'panel': '#f7f9fc', 'paper': '#ffffff',
              'shelf': '#e0e6ed', 'canvas': '#edf0f4', 'ink': '#263242', 'muted': '#596b7e',
              'accent': '#2878ad', 'accent2': '#6599bf', 'border': '#b6c3d0',
              'highlight': '#d3e9f7', 'btn': '#fefefe', 'btn2': '#e3effa', 'preview': '#dee3ea'},
    'modern-dark': {'name': 'Modern Dark', 'window': '#1c222d', 'panel': '#293242', 'paper': '#333c4e',
              'shelf': '#232d3b', 'canvas': '#242d3b', 'ink': '#f4f6fb', 'muted': '#bccad9',
              'accent': '#84bcf4', 'accent2': '#ada7e2', 'border': '#58677c',
              'highlight': '#40536d', 'btn': '#39495d', 'btn2': '#4a6076', 'preview': '#181e27'},
}
# Ten optional study palettes. Their field names match the
# original seven themes, so every existing dialog and button
# inherits the same centralised colours automatically.
#
# We keep their identifiers stable: a theme's ID is saved in
# Preferences, while its display name is only shown to users.
THEMES.update({
    # Light — Japanese stationery and clean modern colours.
    'asagao': {'name': 'Asagao Morning',
               'window': '#e9edf7', 'panel': '#f7f9ff',
               'paper': '#ffffff', 'shelf': '#dde5f5',
               'canvas': '#e8edf8', 'ink': '#25324a',
               'muted': '#56647c', 'accent': '#536bc1',
               'accent2': '#a15da3', 'border': '#b4c0d9',
               'highlight': '#dce6fa', 'btn': '#ffffff',
               'btn2': '#e9eafa', 'preview': '#dbe2f0'},
    'ume': {'name': 'Ume Blossom',
            'window': '#f4e9e8', 'panel': '#fffbf9',
            'paper': '#fffefd', 'shelf': '#f0dfe2',
            'canvas': '#f4e9e9', 'ink': '#4a303e',
            'muted': '#725263', 'accent': '#b34770',
            'accent2': '#d07666', 'border': '#d7b9c4',
            'highlight': '#f7dfe6', 'btn': '#fffcfb',
            'btn2': '#f7e4e8', 'preview': '#eadddf'},
    'hinoki': {'name': 'Hinoki Paper',
               'window': '#eee9dd', 'panel': '#fcf8ee',
               'paper': '#fffef8', 'shelf': '#e3d9c8',
               'canvas': '#eee6da', 'ink': '#3d372d',
               'muted': '#685d4b', 'accent': '#8a5f30',
               'accent2': '#44715c', 'border': '#ccbea9',
               'highlight': '#eee2c9', 'btn': '#fffdf5',
               'btn2': '#eee3d0', 'preview': '#e6ddd1'},
    'sora': {'name': 'Sora Sky',
             'window': '#eaf3f8', 'panel': '#f8fcff',
             'paper': '#ffffff', 'shelf': '#dcecf6',
             'canvas': '#e7f2f9', 'ink': '#263c50',
             'muted': '#51697d', 'accent': '#286f9a',
             'accent2': '#397ca8', 'border': '#b6cedd',
             'highlight': '#d5e9f7', 'btn': '#ffffff',
             'btn2': '#e2eff8', 'preview': '#dceaf4'},
    'mizu': {'name': 'Mizu Mint',
             'window': '#e7f3ee', 'panel': '#f6fcf9',
             'paper': '#ffffff', 'shelf': '#d7eae3',
             'canvas': '#e4f1eb', 'ink': '#25453d',
             'muted': '#496c60', 'accent': '#237967',
             'accent2': '#687cba', 'border': '#b2d1c5',
             'highlight': '#d3eee2', 'btn': '#fbfffd',
             'btn2': '#dbf0e7', 'preview': '#dbeae3'},
    # Dark — ink, lacquer, night-time colours and slate UI.
    'yoru': {'name': 'Yoru Neon',
             'window': '#131c29', 'panel': '#1c293c',
             'paper': '#243247', 'shelf': '#182638',
             'canvas': '#162231', 'ink': '#f3f5ff',
             'muted': '#b8c7da', 'accent': '#6fe2d2',
             'accent2': '#bb96f3', 'border': '#4b6078',
             'highlight': '#344b63', 'btn': '#283a51',
             'btn2': '#344965', 'preview': '#111b29'},
    'sumi': {'name': 'Sumi Ink',
             'window': '#1c1e20', 'panel': '#272b2d',
             'paper': '#303537', 'shelf': '#222629',
             'canvas': '#1c2225', 'ink': '#f7f0e1',
             'muted': '#c6bfae', 'accent': '#d7ae67',
             'accent2': '#7bb6aa', 'border': '#5f6768',
             'highlight': '#4a493a', 'btn': '#394040',
             'btn2': '#4b5151', 'preview': '#191e21'},
    'beni': {'name': 'Beni Lantern',
             'window': '#291b28', 'panel': '#392737',
             'paper': '#462d40', 'shelf': '#321f30',
             'canvas': '#251b28', 'ink': '#fff1f7',
             'muted': '#dec7d7', 'accent': '#f395a8',
             'accent2': '#eab46f', 'border': '#755466',
             'highlight': '#583f52', 'btn': '#50374b',
             'btn2': '#63465d', 'preview': '#201824'},
    'aoi': {'name': 'Aoi Night',
            'window': '#121f23', 'panel': '#213339',
            'paper': '#263c41', 'shelf': '#192a2f',
            'canvas': '#14272c', 'ink': '#effff9',
            'muted': '#c2d8d3', 'accent': '#76c7bd',
            'accent2': '#a8d0a7', 'border': '#567078',
            'highlight': '#335856', 'btn': '#2f4a50',
            'btn2': '#406269', 'preview': '#0e1e22'},
    'shibui': {'name': 'Shibui Graphite',
               'window': '#1b2026', 'panel': '#252d35',
               'paper': '#2d3740', 'shelf': '#202832',
               'canvas': '#192128', 'ink': '#f5f7f9',
               'muted': '#c2ced5', 'accent': '#b5c7d9',
               'accent2': '#78b6bf', 'border': '#5b6875',
               'highlight': '#40505a', 'btn': '#35414b',
               'btn2': '#465561', 'preview': '#171e25'},
    # Saturated but readable: colourful chrome, calm paper for long sessions.
    'strawberry': {'name': 'Strawberry Milkshake',
                   'window': '#ffe4ec', 'panel': '#fff4f9', 'paper': '#fffefe',
                   'shelf': '#ffcfe0', 'canvas': '#f8dfec', 'ink': '#43243b',
                   'muted': '#70445e', 'accent': '#b91f65', 'accent2': '#d54b5b',
                   'border': '#d999b5', 'highlight': '#ffd2e5', 'btn': '#fffafd',
                   'btn2': '#ffd9e9', 'preview': '#f0d8e7'},
    'melon-soda': {'name': 'Melon Soda Pop',
                   'window': '#d8f5eb', 'panel': '#f0fff9', 'paper': '#ffffff',
                   'shelf': '#b7ebda', 'canvas': '#dff7f2', 'ink': '#193b35',
                   'muted': '#34675a', 'accent': '#087865', 'accent2': '#c83b82',
                   'border': '#7dbaaa', 'highlight': '#bef4e4', 'btn': '#f8fffc',
                   'btn2': '#cbf3e6', 'preview': '#cbece4'},
    'peach-mochi': {'name': 'Peach Mochi',
                    'window': '#fff0d9', 'panel': '#fffaf0', 'paper': '#fffefa',
                    'shelf': '#ffddb4', 'canvas': '#f8eadb', 'ink': '#4b302b',
                    'muted': '#755049', 'accent': '#ac4933', 'accent2': '#a53f87',
                    'border': '#d7b49c', 'highlight': '#ffe1ae', 'btn': '#fffcf6',
                    'btn2': '#ffdfc8', 'preview': '#f1dfcf'},
    'candy-cloud': {'name': 'Candy Cloud',
                     'window': '#ece8ff', 'panel': '#faf9ff', 'paper': '#ffffff',
                     'shelf': '#dcd6ff', 'canvas': '#e9e6f8', 'ink': '#292444',
                     'muted': '#60558a', 'accent': '#6247b0', 'accent2': '#c43679',
                     'border': '#b7aae2', 'highlight': '#efd9ff', 'btn': '#ffffff',
                     'btn2': '#e9e1ff', 'preview': '#e2def4'},
    'grape-fizz': {'name': 'Grape Fizz Night',
                   'window': '#211633', 'panel': '#37244c', 'paper': '#443059',
                   'shelf': '#2a1a41', 'canvas': '#21152f', 'ink': '#fff4ff',
                   'muted': '#dec8e9', 'accent': '#ff9de3', 'accent2': '#7ddcf2',
                   'border': '#876b9b', 'highlight': '#66487e', 'btn': '#4c3563',
                   'btn2': '#60467b', 'preview': '#1b122a'},
    'arcade-hearts': {'name': 'Arcade Hearts',
                      'window': '#1e1832', 'panel': '#30234a', 'paper': '#3a2c58',
                      'shelf': '#281d42', 'canvas': '#1d172e', 'ink': '#fff8fb',
                      'muted': '#dfd0ed', 'accent': '#ff93bc', 'accent2': '#68e3cd',
                      'border': '#796293', 'highlight': '#564378', 'btn': '#4a3561',
                      'btn2': '#5e4778', 'preview': '#18142b'},
})

THEME_NAMES = {key: c['name'] for key, c in THEMES.items()}
THEME_NAMES['system'] = 'Follow macOS / system'


def blend_colour(first: str, second: str, amount: float) -> str:
    """Blend two hex colours without changing contrast of body text or menus."""
    a, b = QColor(first), QColor(second)
    k = max(0.0, min(1.0, amount))
    return QColor(round(a.red()*(1-k)+b.red()*k),
                  round(a.green()*(1-k)+b.green()*k),
                  round(a.blue()*(1-k)+b.blue()*k)).name()


def background_gradient(c):
    """Create a richer pastel panel with a second complementary colour."""
    left = blend_colour(c['panel'], c['accent'], 0.035)
    right = blend_colour(c['panel'], c['accent2'], 0.05)
    return (f"qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            f"stop:0 {left},stop:0.5 {c['panel']},stop:1 {right})")


def application_palette(c: dict) -> QPalette:
    """Give EVERY Qt widget the active Yomu Note colours.

    A palette is Qt's fallback colour set. It is used by native Windows
    widgets and newly opened dialogs, including spin-box number fields.
    The stylesheet below then adds Yomu's borders and hover effects.
    Keeping both sources here avoids theme fixes in individual dialogs.
    """
    palette = QPalette()
    roles = {
        QPalette.ColorRole.Window: 'window',
        QPalette.ColorRole.WindowText: 'ink',
        QPalette.ColorRole.Base: 'paper',
        QPalette.ColorRole.AlternateBase: 'panel',
        QPalette.ColorRole.Text: 'ink',
        QPalette.ColorRole.Button: 'btn',
        QPalette.ColorRole.ButtonText: 'ink',
        QPalette.ColorRole.Highlight: 'highlight',
        QPalette.ColorRole.HighlightedText: 'ink',
        QPalette.ColorRole.ToolTipBase: 'panel',
        QPalette.ColorRole.ToolTipText: 'ink',
        QPalette.ColorRole.Link: 'accent',
    }
    for role, key in roles.items():
        palette.setColor(QPalette.ColorGroup.Active, role, QColor(c[key]))
        palette.setColor(QPalette.ColorGroup.Inactive, role, QColor(c[key]))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.WindowText,
                 QPalette.ColorRole.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled, role,
                         QColor(c['muted']))
    return palette


def stylesheet(c: dict) -> str:
    # The UI family comes from QApplication.setFont (Montserrat when bundled).
    # Do not set a QSS font-family on QTextEdit: notes keep user font choices.
    # QSS gradients are lightweight. No timer or constantly running animation.
    # Crisp controls on calm backgrounds replace the old all-over gradients.
    muted_q = QColor(c['muted'])
    disabled_ink = f'rgba({muted_q.red()}, {muted_q.green()}, {muted_q.blue()}, 105)'
    normal = c['btn']
    hover = c['btn2']
    primary = f"qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {c['accent']},stop:1 {c['accent2']})"
    ambient = background_gradient(c)
    return f'''
    QMainWindow, QDialog {{ background: {c['window']}; color: {c['ink']}; }}
    QWidget {{ color: {c['ink']}; font-size: 12px; }}
    QWidget#topHeader {{ background: {ambient}; border-bottom: 1px solid {c['border']}; }}
    QWidget#shelf, QWidget#canvas, QWidget#notePane {{ background: transparent; }}
    /* A scroll area has its own viewport: both it and the content must be themed. */
    QScrollArea#preferencesScroll, QWidget#preferencesViewport, QWidget#preferencesContent {{
        background: {c['panel']}; color: {c['ink']}; border: none; }}
    QWidget#preferencesContent QLabel, QWidget#preferencesContent QCheckBox {{ color: {c['ink']}; }}
    QLabel#sectionLabel {{ font-size: 11px; font-weight: 800; color: {c['muted']}; }}
    QLabel#hintLabel {{ color: {c['muted']}; font-size: 11px; }}
    QLabel#titleLabel {{ color: {c['ink']}; font-size: 14px; font-weight: 700; }}
    QLabel#saveToast {{ background: {c['accent']}; color: white; font-size: 13px;
                         font-weight: bold; border-radius: 13px; padding: 6px; }}
    QTextEdit, QPlainTextEdit {{ background: {c['paper']}; color: {c['ink']}; border: 1px solid {c['border']};
                 border-radius: 9px; padding: 10px; selection-background-color: {c['accent']}; }}
    /* OCR review uses QPlainTextEdit, not the rich-text QTextEdit above.
       Keep the viewport foreground/background matched in every light/dark theme. */
    QPlainTextEdit#ocrReviewText {{ background-color: {c['paper']}; color: {c['ink']};
                                  selection-background-color: {c['highlight']};
                                  selection-color: {c['ink']}; }}
    /* Apply consistently to notes search, page rename and every modal input.
       This also prevents Windows dark-mode edits inside otherwise light themes. */
    QLineEdit {{ background: {c['paper']}; color: {c['ink']};
        border: 1px solid {c['border']}; border-radius: 7px;
        padding: 6px 9px; selection-background-color: {c['accent']};
        selection-color: {c['paper']}; }}
    QLineEdit:focus {{ border: 2px solid {c['accent']}; }}
    QListWidget {{ background: {c['paper']}; border: 1px solid {c['border']};
                   border-radius: 9px; outline: none; padding: 5px; }}
    QListWidget::item {{ border-radius: 5px; padding: 5px; }}
    QListWidget::item:selected {{ background: {c['highlight']}; color: {c['ink']}; }}
    QListWidget::item:hover {{ background: {c['btn2']}; }}
    /* The Groups tree shares the same palette as the thumbnail list. */
    QTreeWidget {{ background: {c['paper']}; color: {c['ink']};
                   border: 1px solid {c['border']}; border-radius: 9px;
                   outline: none; padding: 4px; }}
    QTreeWidget::item {{ padding: 6px 5px; border-radius: 5px; }}
    QTreeWidget::item:selected {{ background: {c['highlight']};
                                  color: {c['ink']}; }}
    QTreeWidget::item:hover {{ background: {c['btn2']}; }}
    QTreeWidget::branch:has-children {{ color: {c['accent']}; }}
    QToolBar, QWidget#wrapBar {{ background: transparent; border: none; spacing: 3px; padding: 0; }}
    QPushButton, QToolButton {{ background: {normal}; color: {c['ink']};
                               border: 1px solid {c['border']}; border-radius: 9px;
                               padding: 4px 8px; min-height: 20px; }}
    /* The editor has fixed 29–30 px icon controls: never inflate those. */
    QToolButton {{ padding: 2px 4px; min-height: 18px; }}
    QPushButton:hover, QToolButton:hover {{ background: {hover}; border: 1px solid {c['accent']}; }}
    QPushButton:pressed, QToolButton:pressed {{ background: {c['highlight']}; border: 1px solid {c['accent2']}; }}
    QPushButton#primary, QToolButton#insertPlus {{ background: {primary}; color: white; border: none; }}
    QPushButton#primary:hover, QToolButton#insertPlus:hover {{ border: 1px solid white; }}
    QPushButton:checked, QToolButton:checked {{ border: 2px solid {c['accent']}; }}
    QPushButton:focus, QToolButton:focus {{ border: 2px solid {c['accent']}; }}
    /* Apply one theme to ALL number fields, including page-setup dialogs.
       QDoubleSpinBox wasn't styled before, so Windows painted a black
       native field with dark ink when the application was in light mode. */
    QAbstractSpinBox, QSpinBox, QDoubleSpinBox, QDateEdit, QTimeEdit,
    QDateTimeEdit, QComboBox, QFontComboBox {{
        background: {c['paper']}; color: {c['ink']};
        border: 1px solid {c['border']}; border-radius: 7px;
        padding: 4px; min-height: 20px;
        selection-background-color: {c['highlight']};
        selection-color: {c['ink']};
    }}
    QAbstractSpinBox:focus, QComboBox:focus,
    QFontComboBox:focus {{ border: 2px solid {c['accent']}; }}
    QAbstractSpinBox QLineEdit, QComboBox QLineEdit {{
        background: {c['paper']}; color: {c['ink']}; border: none;
        selection-background-color: {c['highlight']};
        selection-color: {c['ink']};
    }}
    QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{
        background: {c['btn']}; border: 0px;
        border-left: 1px solid {c['border']}; width: 15px;
    }}
    QAbstractSpinBox::up-button:hover, QAbstractSpinBox::down-button:hover {{
        background: {c['btn2']};
    }}
    /* Reading HP bars follow the active theme, never native Windows blue. */
    QProgressBar#readingProgress {{ background: {c['btn2']}; border: none;
                                     border-radius: 3px; }}
    QProgressBar#readingProgress::chunk {{ background: {c['accent']};
                                            border-radius: 3px; }}
    QCheckBox {{ spacing: 8px; color: {c['ink']}; }}
    QCheckBox::indicator {{ width: 15px; height: 15px; }}
    QCheckBox::indicator:unchecked {{ background: {c['paper']}; border: 1px solid {c['border']}; border-radius: 4px; }}
    QCheckBox::indicator:checked {{ background: {c['accent']}; border: 1px solid {c['accent']}; border-radius: 4px; }}
    QTabWidget::pane {{ border: none; }}
    QTabBar::tab {{ background: {normal}; border: 1px solid {c['border']};
                   border-bottom: none; padding: 8px 21px 8px 13px; margin-right: 5px;
                   border-top-left-radius: 9px; border-top-right-radius: 9px; }}
    QTabBar::close-button {{ margin-left: 2px; margin-right: 12px; }}
    QToolButton#tabDeleteButton {{ min-width: 18px; max-width: 18px;
        min-height: 18px; max-height: 18px; padding: 0px;
        background: transparent; border: none;
        margin: 0px; border-radius: 4px; }}
    QToolButton#tabDeleteButton:hover {{ background: {c['highlight']}; border: none; }}
    QTabBar::tab:selected {{ background: {c['panel']}; color: {c['accent']}; font-weight: 700; }}
    QSplitter::handle {{ background: {c['border']}; width: 5px; }}
    QStatusBar {{ background: {c['panel']}; color: {c['muted']}; }}
    QMenuBar, QMenu, QToolTip {{ background: {c['panel']}; color: {c['ink']}; }}
    QScrollArea {{ border: none; }}
    QDialogButtonBox {{ background: {c['panel']}; }}
    QMenu::item {{ color: {c['ink']}; padding: 5px 16px; }}
    QMenu::item:selected {{ color: {c['ink']}; background: {c['highlight']}; }}
    QMenu::item:disabled {{ color: {disabled_ink}; }}
    QPushButton:disabled, QToolButton:disabled {{ color: {disabled_ink}; background: {c['panel']}; border-color: {c['shelf']}; }}
    QMenuBar::item:selected {{ color: {c['ink']}; background: {c['highlight']}; }}
    QWidget#panelDropHeader[dropZone="before"] {{ border-left: 3px solid {c['accent']}; }}
    QWidget#panelDropHeader[dropZone="after"] {{ border-right: 3px solid {c['accent']}; }}
    QToolButton#reorderGrip {{ font-size: 17px; font-weight: 800;
        padding: 1px; min-height: 22px; max-width: 27px; }}
    QToolTip {{ border: 1px solid {c['border']}; padding: 5px 7px; border-radius: 6px; }}
    QComboBox QAbstractItemView {{ background: {c['paper']}; color: {c['ink']};
                                 selection-background-color: {c['highlight']}; selection-color: {c['ink']}; }}
    QSpinBox, QComboBox, QFontComboBox {{ selection-background-color: {c['highlight']}; selection-color: {c['ink']}; }}

    '''



class ReorderGrip(QToolButton):
    """A small six-dot handle. Moving a panel never recreates its widgets.

    Dragging is deliberately limited to this grip, so selecting notes, PDFs
    and thumbnails keeps its normal behaviour. The per-pane token prevents
    accidental drag-and-drop between two open project tabs.
    """
    MIME = 'application/x-yomu-workspace-panel'

    def __init__(self, key: str, token: str, parent=None):
        super().__init__(parent)
        self.key = key
        self.token = token
        self._press_pos = None
        self.setObjectName('reorderGrip')
        self.setText('⠿')
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setToolTip('Drag to move this panel · drop onto another panel heading')
        self.setAccessibleName(f'Move {key} panel')
        self.setFixedWidth(28)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_pos = event.position().toPoint()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._press_pos is None or not (event.buttons() & Qt.MouseButton.LeftButton):
            super().mouseMoveEvent(event)
            return
        if (event.position().toPoint() - self._press_pos).manhattanLength() < QApplication.startDragDistance():
            return
        self._press_pos = None
        payload = QMimeData()
        payload.setData(self.MIME, f'{self.token}:{self.key}'.encode('utf-8'))
        drag = QDrag(self)
        drag.setMimeData(payload)
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        try:
            drag.exec(Qt.DropAction.MoveAction)
        finally:
            self.setCursor(Qt.CursorShape.OpenHandCursor)

    def mouseReleaseEvent(self, event):
        self._press_pos = None
        super().mouseReleaseEvent(event)


class PanelDropHeader(QWidget):
    """Full-width drop zone with a slim insertion mark on the target side."""
    moveRequested = Signal(str, str, bool)  # source, target, insert-after?

    def __init__(self, key: str, token: str, title_widget: QWidget, parent=None):
        super().__init__(parent)
        self.key, self.token = key, token
        self.setObjectName('panelDropHeader')
        self.setProperty('dropZone', '')
        self.setAcceptDrops(True)
        self.setMinimumHeight(29)
        line = QHBoxLayout(self)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(6)
        self.grip = ReorderGrip(key, token, self)
        # Fixed leading alignment: hiding the title in Mini navigator mode
        # must never let Qt centre the only remaining drag grip.
        line.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        line.addWidget(self.grip, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        line.addWidget(title_widget, 1)

    def _source(self, event):
        data = event.mimeData()
        if not data.hasFormat(ReorderGrip.MIME):
            return None
        try:
            token, key = bytes(data.data(ReorderGrip.MIME)).decode('utf-8').split(':', 1)
        except ValueError:
            return None
        return key if token == self.token and key in PANEL_KEYS and key != self.key else None

    def _zone(self, event):
        return 'before' if event.position().x() < self.width() / 2 else 'after'

    def _set_zone(self, value):
        if self.property('dropZone') == value:
            return
        self.setProperty('dropZone', value)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def dragEnterEvent(self, event):
        if self._source(event):
            self._set_zone(self._zone(event))
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if self._source(event):
            self._set_zone(self._zone(event))
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self._set_zone('')
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        source = self._source(event)
        if source:
            after = self._zone(event) == 'after'
            self._set_zone('')
            self.moveRequested.emit(source, self.key, after)
            event.acceptProposedAction()
        else:
            event.ignore()


class AmbientPanel(QWidget):
    """Low-cost, scroll-reactive wash of colour beneath the interface.

    Only a widget's background is repainted. Scrollable PDF pages, rich text,
    and thumbnails do NOT move with the decoration. The animation is started
    only by scroll events and stops when the colour returns to rest.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.colours = dict(THEMES['washi'])
        self.motion_reduced = False
        self.drift = 0.0
        self._last_scroll = None
        self.anim = QVariantAnimation(self)
        self.anim.setDuration(420)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.anim.valueChanged.connect(self._step)

    def _step(self, value):
        self.drift = float(value)
        self.update()

    def set_theme_colours(self, colours):
        self.colours = dict(colours)
        self.update()

    def set_reduce_motion(self, reduce):
        self.motion_reduced = bool(reduce)
        if reduce:
            self.anim.stop()
            self.drift = 0.0
            self.update()

    def scroll_pulse(self, position):
        if self._last_scroll is None:
            self._last_scroll = int(position)
            return
        delta = int(position) - self._last_scroll
        self._last_scroll = int(position)
        if not delta or self.motion_reduced or not self.isVisible():
            return
        # Map potentially enormous scrollbar movements into a small safe drift.
        motion = max(-16.0, min(16.0, self.drift + delta * .12))
        self.anim.stop()
        self.drift = motion
        self.anim.setStartValue(motion)
        self.anim.setEndValue(0.0)
        self.anim.start()
        self.update()

    def paintEvent(self, event):
        c = self.colours
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        # Subtle background tint, not another competing layer of button-colour.
        # The PDF and notes are untouched, and the animation remains on demand.
        base = c['shelf'] if self.objectName() == 'shelf' else (
               c['canvas'] if self.objectName() == 'canvas' else c['panel'])
        gradient = QLinearGradient(-30, -self.height()*.1+self.drift,
                                   self.width()+25, self.height()*1.05+self.drift)
        gradient.setColorAt(0, QColor(blend_colour(base, c['accent'], .025)))
        gradient.setColorAt(.50, QColor(base))
        gradient.setColorAt(1, QColor(blend_colour(base, c['accent2'], .04)))
        painter.fillRect(self.rect(), gradient)
        painter.end()


class ClickableTitle(QLabel):
    """Allow a single click on the current page title to begin renaming."""
    clicked = Signal()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
        else:
            super().mouseReleaseEvent(event)


class PageTitleEditor(QWidget):
    """Rename the selected page inline without a disruptive modal dialog."""
    renamed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.stack = QStackedLayout(self)
        self.stack.setContentsMargins(0, 0, 0, 0)
        self.label = ClickableTitle('PAGE PREVIEW')
        self.label.setObjectName('titleLabel')
        self.label.setWordWrap(True)
        self.label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.label.setToolTip('Click to rename this page · Return saves · Escape cancels')
        self.label.clicked.connect(self.start_edit)
        self.edit = QLineEdit()
        self.edit.setObjectName('pageRenameInput')
        self.edit.setMaxLength(180)
        self.edit.setToolTip('Type a page name · Return saves · Escape cancels')
        self.edit.returnPressed.connect(self.commit)
        self.edit.editingFinished.connect(self.commit)
        shortcut = QShortcut(QKeySequence('Escape'), self.edit)
        shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
        shortcut.activated.connect(self.cancel)
        self._escape = shortcut
        self._cancelled = False
        self._has_page = False
        self.stack.addWidget(self.label)
        self.stack.addWidget(self.edit)

    def setText(self, text):
        self.label.setText(text)
        if self.stack.currentWidget() is not self.label:
            self.stack.setCurrentWidget(self.label)

    def start_edit(self):
        if not self._has_page:
            return
        self._cancelled = False
        self.edit.setText(self.label.text())
        self.stack.setCurrentWidget(self.edit)
        self.edit.setFocus()
        self.edit.selectAll()

    def cancel(self):
        self._cancelled = True
        self.stack.setCurrentWidget(self.label)
        self.label.setFocus()

    def commit(self):
        if self._cancelled or self.stack.currentWidget() is self.label:
            return
        title = self.edit.text().strip()
        self.stack.setCurrentWidget(self.label)
        if title and title != self.label.text():
            self.label.setText(title)
            self.renamed.emit(title)


class AnimatedPageDelegate(QStyledItemDelegate):
    """Paint a subtly animated outline around the hovered thumbnail row only.

    A single animation tracks the hovered row, so even huge projects do not
    maintain a separate animation object per thumbnail.
    """
    def __init__(self, view):
        super().__init__(view)
        self.view = view
        self.hover_row = -1
        self.intensity = 0.0
        self.accent = QColor('#e94d83')
        self.ink = QColor('#3c4054')
        self.anim = QVariantAnimation(self)
        self.anim.setDuration(180)
        self.anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.anim.valueChanged.connect(self._update)
        self.anim.finished.connect(self._end_animation)
        self._leaving = False

    def _end_animation(self):
        if self._leaving and self.intensity < .02:
            self.hover_row = -1
            self.view.viewport().update()

    def _update(self, value):
        self.intensity = float(value)
        self.view.viewport().update()

    def set_hover_row(self, row):
        if row == self.hover_row and not self._leaving:
            return
        self.anim.stop()
        if row < 0:
            # Keep painting the old row *while* the outline fades away.
            self._leaving = True
            self.anim.setStartValue(self.intensity)
            self.anim.setEndValue(0.0)
        else:
            self._leaving = False
            self.hover_row = row
            self.anim.setStartValue(0.0)
            self.anim.setEndValue(1.0)
        self.anim.start()
        self.view.viewport().update()

    def initStyleOption(self, option, index):
        """Hide visible page names while preserving their hover tooltips.

        Selection/background remain styled by Qt. The page image itself is
        fitted by this delegate, independent of the fixed card dimensions.
        """
        super().initStyleOption(option, index)
        option.text = ''
        option.decorationPosition = QStyleOptionViewItem.Position.Top
        # The actual preview placement is handled in paint(), not by a
        # portrait-shaped icon slot. This keeps every page's own aspect.
        option.decorationAlignment = Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter

    def paint(self, painter, option, index):
        """Paint the selected card natively, then fit the *actual* page inside.

        Qt's native icon slot is a preset portrait rectangle, so its layout
        does not reliably place short landscape slides in the vertical middle
        of the card. Preserve native styling/selection/focus via QStyle, but
        place the existing QPixmap explicitly in the free space ABOVE the
        page-number footer. No stretch, extra raster, or additional cache.
        """
        decorated = QStyleOptionViewItem(option)
        self.initStyleOption(decorated, index)
        decorated.icon = QIcon()  # QStyle paints the card, not its icon slot
        painter.save()
        self.view.style().drawControl(QStyle.ControlElement.CE_ItemViewItem,
                                      decorated, painter, self.view)
        painter.restore()

        row = QRectF(option.rect)
        reserved_footer = 29.0  # separate, always-visible page number
        top_margin = 7.0
        # Keep the image away from the sides of the card even when the
        # navigator stretches extremely wide. iconSize already has a cap.
        width = max(1.0, min(float(self.view.iconSize().width()), row.width() - 20.0))
        height = max(1.0, row.height() - reserved_footer - top_margin - 4.0)
        image_x = row.x() + (row.width() - width) / 2.0
        image_y = row.y() + top_margin

        # DecorationRole contains ONLY the decoded page image; do not pad it
        # to a fixed portrait ratio. This is one QPixmap for a visible row.
        page_pixmap = index.data(Qt.ItemDataRole.DecorationRole)
        if isinstance(page_pixmap, QPixmap) and not page_pixmap.isNull():
            x, y, w, h = fit_inside(page_pixmap.width(), page_pixmap.height(),
                                    image_x, image_y, width, height)
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            painter.drawPixmap(QRectF(x, y, w, h), page_pixmap,
                               QRectF(page_pixmap.rect()))
            painter.restore()

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        rect = option.rect.adjusted(3, 2, -3, -2)
        number_rect = QRect(rect.left() + 5, rect.bottom() - 20,
                            rect.width() - 10, 18)
        font = painter.font()
        font.setPointSize(8 if option.rect.width() < 175 else
                          9 if option.rect.width() < 300 else 10)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(self.ink)
        painter.drawText(number_rect, Qt.AlignmentFlag.AlignCenter,
                         str(index.row() + 1))

        if index.row() == self.hover_row and self.intensity:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            colour = QColor(self.accent)
            colour.setAlpha(int(90 * self.intensity))
            painter.setPen(QPen(colour, 2.0))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(option.rect.adjusted(2, 2, -2, -2), 8, 8)
        painter.restore()


class DropPageList(QListWidget):
    """Uniform-height rows; + button fades at page boundaries, never grows the rows."""
    filesDropped = Signal(list, int)
    addAt = Signal(int)
    blankAt = Signal(int)
    orderChanged = Signal()
    visibleAreaChanged = Signal()
    pagesPasted = Signal(str, str, list, bool)
    PAGE_MIME = 'application/x-yomu-notebook-pages'

    ROW_HEIGHT = 160

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        # A vertical list, not an icon grid. Wide pages now have the same row gap.
        self.setViewMode(QListWidget.ViewMode.ListMode)
        self.setLayoutMode(QListWidget.LayoutMode.Batched)
        self.setBatchSize(40)
        self.setUniformItemSizes(True)
        self.setIconSize(QSize(104, 108))
        self.setSpacing(4)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self._hover_delegate = AnimatedPageDelegate(self)
        self.setItemDelegate(self._hover_delegate)
        self.verticalScrollBar().valueChanged.connect(lambda _: self.visibleAreaChanged.emit())
        # Mouse-wheel clicks ease gently. Native trackpad pixel scrolling must
        # remain untouched because macOS already supplies precise momentum.
        self._wheel_animation = QPropertyAnimation(self.verticalScrollBar(), b'value', self)
        self._wheel_animation.setDuration(190)
        self._wheel_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._insert_index = 0
        self._menu_insert_index = 0
        self.plus = QToolButton(self.viewport())
        self.plus.setObjectName('insertPlus')
        self.plus.setText('+')
        self.plus.setToolTip('Insert a file or blank page at this position')
        self.plus.resize(28, 26)
        self.plus.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.plus_menu = QMenu(self.plus)
        # Freeze the gap on menu opening: cursor movements and animated
        # hover transitions must not silently redirect insertion to the end.
        self.plus_menu.aboutToShow.connect(self._freeze_insert_gap)
        self.plus_menu.addAction('Import File…', lambda: self.addAt.emit(self._menu_insert_index))
        self.plus_menu.addAction('Add Blank Page', lambda: self.blankAt.emit(self._menu_insert_index))
        self.plus.setMenu(self.plus_menu)
        self.opacity = QGraphicsOpacityEffect(self.plus)
        self.opacity.setOpacity(0.0)
        self.plus.setGraphicsEffect(self.opacity)
        self.fade = QPropertyAnimation(self.opacity, b'opacity', self)
        self.fade.setDuration(170)
        self.fade.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.plus.hide()

    def _freeze_insert_gap(self):
        self._menu_insert_index = max(0, min(self._insert_index, self.count()))

    def _page_transfer_mime(self):
        ids = [item.data(Qt.ItemDataRole.UserRole) for item in self.selectedItems()]
        if not ids or not getattr(self, 'notebook_id', None):
            return None
        data = {'notebook': self.notebook_id, 'source': self.tab_id,
                'pages': ids}
        return json.dumps(data).encode('utf-8')

    def startDrag(self, supported_actions):
        payload = self._page_transfer_mime()
        if not payload:
            super().startDrag(supported_actions)
            return
        mime = self.model().mimeData(self.selectedIndexes())
        mime.setData(self.PAGE_MIME, payload)
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.MoveAction | Qt.DropAction.CopyAction,
                  Qt.DropAction.MoveAction)

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.StandardKey.Copy):
            payload = self._page_transfer_mime()
            if payload:
                mime = QMimeData()
                mime.setData(self.PAGE_MIME, payload)
                QApplication.clipboard().setMimeData(mime)
                event.accept()
                return
        if event.matches(QKeySequence.StandardKey.Paste):
            mime = QApplication.clipboard().mimeData()
            if mime and mime.hasFormat(self.PAGE_MIME):
                try:
                    data = json.loads(bytes(mime.data(self.PAGE_MIME)).decode('utf-8'))
                    if data['notebook'] == self.notebook_id:
                        self.pagesPasted.emit(data['source'], self.tab_id, data['pages'], True)
                        event.accept()
                        return
                except (KeyError, ValueError, TypeError):
                    pass
        super().keyPressEvent(event)

    def _fade(self, visible: bool):
        self.fade.stop()
        self.fade.setStartValue(self.opacity.opacity())
        self.fade.setEndValue(1.0 if visible else 0.0)
        if visible:
            self.plus.show()
            self.plus.raise_()
        self.fade.start()
        if not visible:
            QTimer.singleShot(180, self._hide_if_faded)

    def _hide_if_faded(self):
        if self.opacity.opacity() < 0.05:
            self.plus.hide()

    def _boundary(self, p: QPoint) -> tuple[int, int] | None:
        """Return row insertion index and viewport Y at nearest nearby gap."""
        if not self.count():
            return 0, 20
        hit = self.itemAt(p)
        if hit:
            row = self.row(hit)
            rect = self.visualItemRect(hit)
            y_top, y_bottom = rect.top(), rect.bottom()
            if abs(p.y() - y_top) <= 16:
                return row, y_top
            if abs(p.y() - y_bottom) <= 16:
                return row + 1, y_bottom
            return None
        # The actual gap may not belong to either row. Probe the rows on
        # both sides so the insertion button still appears between pages.
        x = max(10, min(p.x(), self.viewport().width() - 10))
        up = self.itemAt(QPoint(x, max(0, p.y() - 19)))
        down = self.itemAt(QPoint(x, min(self.viewport().height()-1, p.y() + 19)))
        if up and down and self.row(down) == self.row(up) + 1:
            top = self.visualItemRect(down).top()
            bottom = self.visualItemRect(up).bottom()
            return self.row(down), (top + bottom)//2
        if up:
            r = self.visualItemRect(up)
            if abs(p.y()-r.bottom()) <= 19:
                return self.row(up)+1, r.bottom()
        if down:
            r = self.visualItemRect(down)
            if abs(p.y()-r.top()) <= 19:
                return self.row(down), r.top()
        # Handle the area before the first and after the last item.
        first = self.visualItemRect(self.item(0))
        last = self.visualItemRect(self.item(self.count()-1))
        if abs(p.y() - first.top()) <= 18:
            return 0, first.top()
        if abs(p.y() - last.bottom()) <= 18:
            return self.count(), last.bottom()
        return None

    def wheelEvent(self, event):
        """Ease traditional mouse-wheel notches while preserving touchpad momentum."""
        if (not event.pixelDelta().isNull()
                or event.modifiers() & (Qt.KeyboardModifier.ControlModifier |
                                       Qt.KeyboardModifier.ShiftModifier)):
            self._wheel_animation.stop()
            super().wheelEvent(event)
            return
        steps = event.angleDelta().y() / 120.0
        if not steps:
            super().wheelEvent(event)
            return
        bar = self.verticalScrollBar()
        base = (int(self._wheel_animation.endValue())
                if self._wheel_animation.state() == QAbstractAnimation.State.Running
                else bar.value())
        target = round(base - steps * 62)
        target = max(bar.minimum(), min(bar.maximum(), target))
        self._wheel_animation.stop()
        self._wheel_animation.setStartValue(bar.value())
        self._wheel_animation.setEndValue(target)
        self._wheel_animation.start()
        event.accept()

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        hit = self.itemAt(event.position().toPoint())
        self._hover_delegate.set_hover_row(self.row(hit) if hit else -1)
        boundary = self._boundary(event.position().toPoint())
        if boundary:
            self._insert_index, y = boundary
            self.plus.move(max(5, self.viewport().width() - 40),
                           max(0, min(self.viewport().height()-27, y - 13)))
            if self.opacity.opacity() < 0.99 and self.fade.endValue() != 1.0:
                self._fade(True)
        elif self.fade.endValue() != 0.0:
            self._fade(False)

    def leaveEvent(self, event):
        self._hover_delegate.set_hover_row(-1)
        if self.fade.endValue() != 0.0:
            self._fade(False)
        super().leaveEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self.visibleAreaChanged.emit)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
            b = self._boundary(event.position().toPoint())
            self.filesDropped.emit(paths, b[0] if b else self.count())
            event.acceptProposedAction()
        else:
            super().dropEvent(event)
            QTimer.singleShot(0, self.orderChanged.emit)


class MultiplyHighlightItem(QGraphicsRectItem):
    """Tint the underlying document instead of washing it out with source-over.

    Multiply preserves dark writing beneath a translucent highlighter.  The
    item is still vector scene geometry and works at every document zoom.
    """
    def paint(self, painter, option, widget=None):
        painter.save()
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Multiply)
        painter.fillRect(self.rect(), self.brush())
        painter.restore()


class MultiplyStrokeItem(QGraphicsPathItem):
    """Multiply translucent marker ink against the *underlying* PDF pixels.

    The painter's blend mode is scoped to this item; opaque historical pen
    strokes continue to render with their original appearance.
    """
    def paint(self, painter, option, widget=None):
        painter.save()
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Multiply)
        super().paint(painter, option, widget)
        painter.restore()


class AnnotationQuickEditBackdrop(QWidget):
    """Mouse-transparent, opaque backing for the interactive Quick Edit.

    Never apply QGraphicsDropShadowEffect or a widget opacity effect to the
    container holding real editors. Both effects force Qt to rasterise child
    controls into one surface; hovering/re-styling a swatch can then produce
    stale or missing child paint on some Windows graphics configurations.

    Instead this *single sibling* draws a lightweight soft shadow and a
    fully opaque panel. Controls remain 100% opaque and interactive.
    The shadow remains separate from child controls to avoid Windows hover
    repaint artifacts. The PDF is never blended through the panel.
    """
    MARGIN = 9

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._surface = QColor('#fff8fa')
        self._surface.setAlpha(255)
        self._border = QColor('#c7b5c1')

    def set_theme(self, colours):
        surface = QColor(colours['panel'])
        # No transparency: keeps text readable over detailed PDF pages.
        surface.setAlpha(255)
        self._surface = surface
        self._border = QColor(colours['border'])
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        body = QRectF(self.rect()).adjusted(self.MARGIN, self.MARGIN,
                                            -self.MARGIN, -self.MARGIN)
        painter.setPen(Qt.PenStyle.NoPen)
        # A handful of soft bands cost negligible RAM and don't intercept
        # input, unlike a graphics effect on the entire interactive panel.
        for spread, opacity in ((8, 2), (6, 4), (4, 6), (2, 8)):
            painter.setBrush(QColor(0, 0, 0, opacity))
            painter.drawRoundedRect(body.adjusted(-spread, -spread, spread, spread),
                                    11 + spread, 11 + spread)
        painter.setPen(QPen(self._border, 1))
        painter.setBrush(self._surface)
        painter.drawRoundedRect(body, 10, 10)
        painter.end()


class AnnotationColourSwatch(QToolButton):
    """Compact paint-style colour chip, independent of alpha and PDF rendering.

    Single-click selects the quick-palette destination; double-click edits the
    custom colour. The native dialog never changes transparency.
    """
    colourEditRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.colour = QColor('#d74685')
        self._active = False
        self._paint_enabled = True
        self.setFixedSize(34, 25)
        self.setAccessibleName('Annotation colour')
        self._refresh()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.colourEditRequested.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def set_colour(self, value):
        colour = QColor(value)
        if colour.isValid():
            self.colour = colour
            self._refresh()

    def set_active(self, active):
        self._active = bool(active)
        self._refresh()

    def set_paint_enabled(self, enabled):
        self._paint_enabled = bool(enabled)
        self._refresh()

    def _refresh(self):
        border = '3px solid #e17aa9' if self._active else '1px solid #788598'
        fill = self.colour.name() if self._paint_enabled else '#8892a4'
        self.setText('' if self._paint_enabled else '×')
        self.setStyleSheet('QToolButton {background: ' + fill + '; border: ' + border +
                           '; border-radius: 5px; color: #ffffff; font-weight: bold;}')


class LabelledHighlightButton(ColourDotButton):
    """Retain the familiar colour dot while restoring an accessible label."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setText('Highlight')
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.setMinimumSize(118, 39)
        self.setMaximumSize(205, 39)
        self.setStyleSheet('QToolButton {padding: 6px 15px 6px 10px;}')


class AnnotationOpacitySlider(QSlider):
    """Commit one history action after a complete mouse/keyboard adjustment."""
    editFinished = Signal()

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        self.editFinished.emit()

    def keyReleaseEvent(self, event):
        super().keyReleaseEvent(event)
        self.editFinished.emit()

    def wheelEvent(self, event):
        super().wheelEvent(event)
        self.editFinished.emit()


class ImageCanvas(QGraphicsView):
    """Zoomable middle-column canvas for a single document page.

    Qt's QGraphicsView displays a scene of annotation items and a page image.
    Mouse input may draw a mark, select an existing mark, or move the view;
    the higher-level ProjectPane decides which project/page is active.
    """
    filesDropped = Signal(list)
    highlightCreated = Signal(dict)
    strokeCreated = Signal(dict)
    strokeMoved = Signal(int, dict)
    strokeEraseRequested = Signal(int)  # compatibility with existing single-click API
    strokesEraseGestureRequested = Signal(list)  # one undoable drag, original indexes
    shapeCreated = Signal(dict)
    strokeResized = Signal(int, dict)
    annotationSelected = Signal(int, object)  # index, saved mark; -1 when deselected
    editingGesture = Signal(bool)  # hide one floating editor while moving/resizing
    zoomChanged = Signal(float, bool)  # actual displayed scale, Fit state
    ocrRegionsChanged = Signal(int)
    ocrCancelRequested = Signal()

    def __init__(self):
        super().__init__()
        self.canvas_scene = QGraphicsScene(self)
        self.setScene(self.canvas_scene)
        self.image_item = QGraphicsPixmapItem()
        # Qt already enables bilinear/smooth display of the EXISTING pixmap.
        # Do not replace this with higher-DPI PDF renders or a scaled-image
        # cache: both would violate our bounded-memory design. Qt's smoothing
        # can't invent finer text detail that isn't in the source preview.
        self.image_item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self.setRenderHints(QPainter.RenderHint.Antialiasing |
                            QPainter.RenderHint.SmoothPixmapTransform |
                            QPainter.RenderHint.TextAntialiasing)
        self.canvas_scene.addItem(self.image_item)
        # This overlay is a transient, viewport-sized bicubic enlargement.
        # We never render a bigger PDF, write another cache file, or retain a
        # second full-page bitmap. Its maximum output is 2.25 megapixels.
        self._bicubic_item = QGraphicsPixmapItem()
        self._bicubic_item.setZValue(2)  # beneath vector highlights (z=3)
        self._bicubic_item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self._bicubic_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.canvas_scene.addItem(self._bicubic_item)
        self._bicubic_token = 0
        self._bicubic_in_flight = False  # at most one upscale job per canvas
        self._bicubic_timer = QTimer(self)
        self._bicubic_timer.setSingleShot(True)
        self._bicubic_timer.setInterval(360)
        self._bicubic_timer.timeout.connect(self._draw_settled_bicubic)
        self.verticalScrollBar().valueChanged.connect(self._schedule_bicubic)
        self.horizontalScrollBar().valueChanged.connect(self._schedule_bicubic)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        # Previously unvisited fitted pages begin flush with the top.
        self.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self._fit = True
        self.setAcceptDrops(True)
        self.highlight_mode = False
        self.highlight_color = '#ffcf69'
        self.annotation_tool = 'pan'
        self.pen_color = '#d74685'
        self.pen_width = 0.003
        self.shape_fill = False
        # Per-tool defaults are distinct from the selected object's properties.
        # All width values use the existing page-relative 0.0005..0.03 units.
        self.tool_styles = {
            key: {'color': '#d74685', 'opacity': 100, 'width': .003,
                  'fill': None, 'fill_opacity': 30, 'stroke_enabled': True}
            for key in ('pen', 'line', 'arrow', 'rectangle', 'ellipse')}
        self.tool_styles['arrow']['head_width'] = .018
        self.tool_styles['arrow']['head_length'] = .025
        # All three new Multiply highlighter tools start at 100% opacity.
        # Existing saved strokes/highlights keep their original stored alpha.
        self.tool_styles['marker'] = {'color': self.highlight_color, 'opacity': 100,
                                       'width': .009, 'fill': None}
        self.tool_styles['highlight'] = {'color': self.highlight_color,
                                          'opacity': 100, 'width': .013}
        self.tool_styles['highlight_line'] = {'color': self.highlight_color,
                                               'opacity': 100, 'width': .013}
        self._shape_origin = None
        self._shape_preview = None
        self._shape_end = None
        self._item_marks = {}
        self._selection_handles = {}
        self._selection_outline = None
        self._resize_handle = None
        self._resize_mark = None
        self._resize_index = None
        self._stroke_points = None
        self._live_stroke = None
        self._selected_stroke = None
        self._stroke_drag_origin = None
        self._stroke_drag_start = None
        self._stroke_items = {}
        self._highlight_origin = None
        self._live_highlight = None
        self._marks = []
        self._eraser_dragging = False
        self._eraser_last = None
        self._eraser_indexes = set()
        self._eraser_hidden = {}
        # OCR is ephemeral UI state: no change to persistent annotations.
        self._ocr_regions = []
        self._ocr_drag = None
        self._ocr_pointer = QPoint()
        self._ocr_dragging = False
        self._ocr_edge_timer = QTimer(self)
        self._ocr_edge_timer.setInterval(34)
        self._ocr_edge_timer.timeout.connect(self._ocr_autoscroll)
        self._ocr_mask = QGraphicsPathItem()
        self._ocr_mask.setZValue(100)
        self._ocr_mask.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.canvas_scene.addItem(self._ocr_mask)
        self._ocr_mask.setVisible(False)
        self._ocr_outline_items = []
        self._ocr_colour = QColor('#22a998')
        self._zoom_factor = 1.0
        self._reference_size = QSize()
        self._last_native_zoom_at = 0.0
        # Mac trackpad: zoom via native gesture; other touch devices may send
        # a Qt pinch gesture. A wheel with Command/Ctrl also zooms.
        self.viewport().grabGesture(Qt.GestureType.PinchGesture)
        self.grabGesture(Qt.GestureType.PinchGesture)

    def stop_bicubic(self):
        """Drop the entire temporary upscale on tab switch/minimise/page change."""
        self._bicubic_token += 1
        self._bicubic_timer.stop()
        self._bicubic_item.setPixmap(QPixmap())

    def _schedule_bicubic(self, *_):
        """Never resample on every 120 Hz animation frame or mouse movement.

        Native Qt draws a quick smooth preview throughout the gesture. After
        360 ms of rest, the visible crop alone gets a bicubic refinement.
        """
        self._bicubic_token += 1
        if (not self.image_item.pixmap().isNull()
                and abs(self.transform().m11()) > 1.015
                and self.isVisible() and not self.window().isMinimized()):
            self._bicubic_timer.start()
        else:
            self._bicubic_timer.stop()
            self._bicubic_item.setPixmap(QPixmap())

    def _draw_settled_bicubic(self):
        """Upsample the visible ORIGINAL pixels only, off the GUI thread.

        PIL's BICUBIC is explicitly chosen instead of relying on Qt's
        platform-dependent SmoothPixmapTransform implementation. The source
        raster is never modified and nothing is written to disk.
        """
        if (self.image_item.pixmap().isNull() or self.window().isMinimized()
                or abs(self.transform().m11()) <= 1.015):
            return
        if self._bicubic_in_flight:
            return  # pending work will schedule a fresh frame if it went stale
        visible = self.mapToScene(self.viewport().rect()).boundingRect()
        visible = visible.intersected(self._page_bounds())
        if visible.isEmpty():
            return
        src = self.image_item.mapRectFromScene(visible).adjusted(-3, -3, 3, 3)
        pixmap = self.image_item.pixmap()
        rect = src.toAlignedRect().intersected(QRect(QPoint(0, 0), pixmap.size()))
        if rect.width() < 1 or rect.height() < 1 or rect.width() * rect.height() > MAX_UPSCALE_SOURCE_PIXELS:
            # A very large source crop needs no expensive upscale: native
            # compositing remains the fallback. No RAM-heavy allocation.
            return
        screen = self.screen()
        dpr = min(2.0, max(1.0, screen.devicePixelRatio() if screen else 1.0))
        requested_scale = (abs(self.transform().m11()) * abs(self.image_item.scale()) * dpr)
        if requested_scale <= 1.015:
            return
        scale = min(requested_scale, math.sqrt(MAX_UPSCALE_OUTPUT_PIXELS / (rect.width() * rect.height())))
        if scale <= 1.0:  # budget would prohibit any meaningful enlargement
            return
        out_w = max(1, round(rect.width() * scale))
        out_h = max(1, round(rect.height() * scale))
        # Rounding each axis separately can exceed the strict area cap by
        # a fraction. Reduce the larger side rather than allocate more RAM.
        while out_w * out_h > MAX_UPSCALE_OUTPUT_PIXELS:
            if out_w >= out_h:
                out_w -= 1
            else:
                out_h -= 1
        try:
            crop = pixmap.copy(rect).toImage().convertToFormat(QImage.Format.Format_RGB888)
            pixels = bytes(crop.bits())
        except Exception:
            return  # safe fallback to the native Qt transform
        src_w, src_h, stride = crop.width(), crop.height(), crop.bytesPerLine()
        token = self._bicubic_token
        self._bicubic_in_flight = True

        def worker():
            return bicubic_rgb_crop(pixels, src_w, src_h, stride,
                                     out_w, out_h)

        def complete(result, error):
            self._bicubic_in_flight = False
            if token != self._bicubic_token:
                # Do not apply stale crop after panning or zooming. Schedule
                # the newer view once; no worker backlog is created.
                self._schedule_bicubic()
                return
            if (error or not result or self.image_item.pixmap().isNull()
                    or not self.isVisible() or self.window().isMinimized()):
                return
            try:
                img = QImage(result, out_w, out_h, out_w * 3,
                             QImage.Format.Format_RGB888).copy()
                self._bicubic_item.setPixmap(QPixmap.fromImage(img))
                self._bicubic_item.setPos(self.image_item.mapToScene(
                    QPointF(rect.left(), rect.top())))
                self._bicubic_item.setScale(self.image_item.scale() * src_w / out_w)
            except Exception:
                self._bicubic_item.setPixmap(QPixmap())

        start_task(self, worker, complete, priority=-1)

    def set_highlighter(self, enabled):
        """Compatibility with the existing highlight colour-button behaviour."""
        self.set_annotation_tool('highlight' if enabled else 'pan')

    def set_annotation_tool(self, tool: str):
        self._cancel_eraser_drag()
        if tool not in ('pan', 'ocr', 'highlight', 'highlight_line', 'pen', 'marker', 'select', 'eraser',
                        'line', 'arrow', 'rectangle', 'ellipse'):
            raise ValueError('Unsupported annotation tool')
        if self._live_stroke is not None and self._live_stroke in self._marks:
            self._marks.remove(self._live_stroke)
            self._stroke_items.pop(self._live_stroke, None)
            self._item_marks.pop(self._live_stroke, None)
            self.canvas_scene.removeItem(self._live_stroke)
        self._live_stroke = None
        if self._shape_preview is not None and self._shape_preview in self._marks:
            self._marks.remove(self._shape_preview)
            self.canvas_scene.removeItem(self._shape_preview)
        self._shape_preview = None
        self._shape_origin = None
        self._shape_end = None
        if self._selected_stroke is not None:
            self._selected_stroke.setSelected(False)
        self._selected_stroke = None
        self._clear_resize_handles()
        self._resize_handle = None
        self._resize_mark = None
        self._resize_index = None
        self.clear_ocr_regions()
        self.annotation_tool = tool
        self._ocr_mask.setVisible(tool == 'ocr')
        self._refresh_ocr_overlay()
        self.highlight_mode = tool in ('highlight', 'highlight_line')
        self._highlight_origin = None
        self._stroke_points = None
        self._stroke_drag_start = None
        self.annotationSelected.emit(-1, None)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag if tool == 'pan'
                         else QGraphicsView.DragMode.NoDrag)
        self.viewport().setCursor(Qt.CursorShape.ArrowCursor if tool == 'pan'
                                  else Qt.CursorShape.CrossCursor)

    def clear_marks(self):
        self._cancel_eraser_drag()
        self._clear_resize_handles()
        for item in self._marks:
            self.canvas_scene.removeItem(item)
        self._marks.clear()
        self._stroke_items.clear()
        self._item_marks.clear()
        self._shape_preview = None
        self._shape_origin = None
        self._shape_end = None
        self._resize_handle = None
        self._resize_mark = None
        self._resize_index = None
        self._live_highlight = None
        self._highlight_origin = None
        self._live_stroke = None
        self._stroke_points = None
        self._selected_stroke = None
        self._stroke_drag_start = None
        self._stroke_drag_origin = None

    def set_annotations(self, marks):
        """Rebuild only active-page vector items; restore selection by ID/index."""
        selected = self._selected_stroke
        old_index = self._stroke_items.get(selected) if selected else None
        old_mark = self._item_marks.get(selected) if selected else None
        self.clear_marks()
        bounds = self._page_bounds()
        if bounds.isEmpty():
            self.annotationSelected.emit(-1, None)
            return
        for index, mark in enumerate(marks):
            if mark.get('kind') in ('highlight', 'highlight_line'):
                self._draw_highlight(mark, index)
            elif mark.get('kind') == 'stroke':
                self._draw_stroke(mark, index)
            elif mark.get('kind') == 'shape':
                self._draw_shape(mark, index)
        if old_mark is not None and self.annotation_tool == 'select':
            for item, mark in self._item_marks.items():
                if ((old_mark.get('id') and mark.get('id') == old_mark['id']) or
                        (not old_mark.get('id') and self._stroke_items[item] == old_index)):
                    self._selected_stroke = item
                    item.setSelected(True)
                    self._show_resize_handles()
                    self.annotationSelected.emit(self._stroke_items[item], mark)
                    return
        self.annotationSelected.emit(-1, None)

    def _tool_style(self, tool=None):
        return self.tool_styles.get(tool or self.annotation_tool,
                                    self.tool_styles['pen'])

    def _stroke_path(self, points):
        """Recreate the live path from mouse-down, never append to a stale path.

        Building from the first real point also prevents the temporary
        upper-left-to-cursor diagonal reported during active pen gestures.
        """
        bounds = self._page_bounds()
        if not points:
            return QPainterPath()
        x0, y0 = points[0]
        path = QPainterPath(QPointF(x0 * bounds.width(), y0 * bounds.height()))
        for x, y in points[1:]:
            path.lineTo(QPointF(x * bounds.width(), y * bounds.height()))
        return path

    def _shape_path(self, mark):
        bounds = self._page_bounds()
        if mark['kind'] == 'highlight':
            path = QPainterPath()
            path.addRect(QRectF(mark['x'] * bounds.width(), mark['y'] * bounds.height(),
                                mark['w'] * bounds.width(), mark['h'] * bounds.height()))
            return path
        p1 = QPointF(mark['x1'] * bounds.width(), mark['y1'] * bounds.height())
        p2 = QPointF(mark['x2'] * bounds.width(), mark['y2'] * bounds.height())
        path = QPainterPath(p1)
        shape = mark.get('shape', 'line')
        if shape == 'rectangle':
            path.addRect(QRectF(p1, p2).normalized())
        elif shape == 'ellipse':
            path.addEllipse(QRectF(p1, p2).normalized())
        else:
            path.lineTo(p2)
            if shape == 'arrow':
                # A true filled polygon, not a round-ended line with two
                # round-ended whiskers.  Arrow heads stay pointed at 100pt.
                dx, dy = p2.x() - p1.x(), p2.y() - p1.y()
                length = math.hypot(dx, dy)
                if length > .001:
                    ux, uy = dx/length, dy/length
                    nx, ny = -uy, ux
                    unit = min(bounds.width(), bounds.height())
                    shaft = max(.7, float(mark['width'])*unit)
                    head_width = max(shaft*1.2, float(mark.get('head_width',
                                              max(.018, 2.5*mark['width'])))*unit)
                    head_length = min(length*.70, max(shaft*1.5, float(mark.get('head_length',
                                               max(.025, 3.0*mark['width'])))*unit))
                    base = QPointF(p2.x()-ux*head_length, p2.y()-uy*head_length)
                    path = QPainterPath(QPointF(p1.x()+nx*shaft/2, p1.y()+ny*shaft/2))
                    for point in (
                        QPointF(base.x()+nx*shaft/2, base.y()+ny*shaft/2),
                        QPointF(base.x()+nx*head_width/2, base.y()+ny*head_width/2),
                        p2,
                        QPointF(base.x()-nx*head_width/2, base.y()-ny*head_width/2),
                        QPointF(base.x()-nx*shaft/2, base.y()-ny*shaft/2),
                        QPointF(p1.x()-nx*shaft/2, p1.y()-ny*shaft/2)):
                        path.lineTo(point)
                    path.closeSubpath()
        return path

    def _apply_item_appearance(self, item, mark):
        """One place for pen, shape and Multiply style (also live UI preview).

        Do not create extra graphics items or PDF bitmaps when changing alpha.
        Older marks without alpha retain their exact historical byte values.
        """
        kind = mark.get('kind', 'stroke')  # live pen preview omits metadata
        shade = QColor(mark['color'])
        if kind == 'highlight':
            shade.setAlphaF(float(mark.get('opacity', 100*92/255))/100)
            item.setPen(QPen(Qt.PenStyle.NoPen))
            item.setBrush(QBrush(shade))
            return
        if kind == 'highlight_line':
            shade.setAlphaF(float(mark.get('opacity', 35))/100)
            pen = QPen(shade)
            pen.setWidthF(max(.7, mark['width'] * min(
                self._page_bounds().width(), self._page_bounds().height())))
            pen.setCapStyle(Qt.PenCapStyle.FlatCap)
            pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
            item.setPen(pen)
            item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            return
        shade.setAlphaF(float(mark.get('opacity',
                       100*135/255 if mark.get('blend') == 'multiply' else 100))/100)
        pen = QPen(shade)
        pen.setWidthF(max(.7, float(mark['width']) *
                          min(self._page_bounds().width(), self._page_bounds().height())))
        shape = mark.get('shape') if kind == 'shape' else None
        pen.setCapStyle(Qt.PenCapStyle.RoundCap if kind == 'stroke'
                        else Qt.PenCapStyle.FlatCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin if kind == 'stroke'
                         else Qt.PenJoinStyle.MiterJoin)
        if shape == 'arrow':
            # The arrow polygon already includes the shaft thickness.  An
            # additional outline would round / double the visible shaft.
            item.setPen(QPen(Qt.PenStyle.NoPen))
            item.setBrush(QBrush(shade) if mark.get('stroke_enabled', True)
                          else QBrush(Qt.BrushStyle.NoBrush))
            return
        if kind == 'shape' and not mark.get('stroke_enabled', True):
            pen.setStyle(Qt.PenStyle.NoPen)
        item.setPen(pen)
        if kind == 'shape' and mark.get('fill') and mark['shape'] in ('rectangle', 'ellipse'):
            fill = QColor(mark['fill'])
            fill.setAlphaF(float(mark.get('fill_opacity', 100*55/255))/100)
            item.setBrush(QBrush(fill))
        else:
            item.setBrush(QBrush(Qt.BrushStyle.NoBrush))

    def _register_vector_item(self, item, mark, index, z=4):
        item.setZValue(z)
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.canvas_scene.addItem(item)
        self._marks.append(item)
        self._stroke_items[item] = index
        self._item_marks[item] = mark
        return item

    def _draw_stroke(self, mark, index):
        item_type = MultiplyStrokeItem if mark.get('blend') == 'multiply' else QGraphicsPathItem
        item = item_type(self._stroke_path(mark['points']))
        self._apply_item_appearance(item, mark)
        return self._register_vector_item(item, mark, index)

    def _draw_shape(self, mark, index):
        item = QGraphicsPathItem(self._shape_path(mark))
        self._apply_item_appearance(item, mark)
        return self._register_vector_item(item, mark, index)

    def _draw_highlight(self, mark, index):
        """Both page-highlighter modes multiply against the visible page."""
        item = MultiplyStrokeItem(self._shape_path(mark))
        self._apply_item_appearance(item, mark)
        return self._register_vector_item(item, mark, index, z=3)

    def preview_selected_appearance(self, mark):
        """Preview alpha/width in-place; no history or persistence until commit."""
        if self._selected_stroke in self._item_marks:
            if mark.get('shape') == 'arrow':
                self._selected_stroke.setPath(self._shape_path(mark))
                self._show_resize_handles()
            self._apply_item_appearance(self._selected_stroke, mark)

    def preview_selected_geometry(self, mark):
        """Preview a selected arrow's head dimensions without rebuilding marks."""
        item = self._selected_stroke
        if item is not None and mark.get('kind') == 'shape':
            item.setPath(self._shape_path(mark))
            self._show_resize_handles()

    def select_mark_by_id(self, mark_id):
        """Select a completed mark using the stable saved ID, not scene order."""
        for item, mark in self._item_marks.items():
            if mark.get('id') == mark_id:
                if self._selected_stroke is not None:
                    self._selected_stroke.setSelected(False)
                self._selected_stroke = item
                item.setSelected(True)
                self._show_resize_handles()
                self.annotationSelected.emit(self._stroke_items[item], mark)
                return True
        return False

    def _clear_resize_handles(self):
        if self._selection_outline is not None:
            self.canvas_scene.removeItem(self._selection_outline)
            self._selection_outline = None
        for handle in self._selection_handles.values():
            self.canvas_scene.removeItem(handle)
        self._selection_handles.clear()

    def _show_resize_handles(self):
        """Position small resize handles; reuse their QGraphicsItems on drag."""
        item = self._selected_stroke
        if item is None or item not in self._item_marks:
            self._clear_resize_handles()
            return
        mark = self._item_marks[item]
        if mark['kind'] == 'highlight_line' or (mark['kind'] == 'shape' and mark['shape'] in ('line', 'arrow')):
            bounds = self._page_bounds()
            handles = {'start': QPointF(mark['x1'] * bounds.width(),
                                         mark['y1'] * bounds.height()) + item.pos(),
                       'end': QPointF(mark['x2'] * bounds.width(),
                                       mark['y2'] * bounds.height()) + item.pos()}
        else:
            rect = item.mapRectToScene(item.path().boundingRect())
            handles = {'tl': rect.topLeft(), 'tr': rect.topRight(),
                       'bl': rect.bottomLeft(), 'br': rect.bottomRight()}
        rect = item.mapRectToScene(item.path().boundingRect())
        if set(handles) != set(self._selection_handles):
            self._clear_resize_handles()
            frame = QGraphicsRectItem(rect)
            frame.setPen(QPen(QColor('#5b83e7'), 1.2, Qt.PenStyle.DashLine))
            frame.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            frame.setZValue(8)
            frame.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            self.canvas_scene.addItem(frame)
            self._selection_outline = frame
            for name in handles:
                handle = QGraphicsEllipseItem(-4.5, -4.5, 9, 9)
                handle.setBrush(QBrush(QColor('#ffffff')))
                handle.setPen(QPen(QColor('#4771cf'), 1.6))
                handle.setZValue(9)
                handle.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
                handle.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
                self.canvas_scene.addItem(handle)
                self._selection_handles[name] = handle
        if self._selection_outline is not None:
            self._selection_outline.setRect(rect)
        for name, pos in handles.items():
            self._selection_handles[name].setPos(pos)

    def _hit_resize_handle(self, point):
        for name, handle in self._selection_handles.items():
            if (self.mapFromScene(point) - self.mapFromScene(handle.scenePos())).manhattanLength() < 11:
                return name
        return None

    def _stroke_hit(self, scene_point):
        for item in self.canvas_scene.items(scene_point):
            if item in self._stroke_items:
                return item, self._stroke_items[item]
        return None, None

    def _page_bounds(self):
        # Always use stable scene coordinates, even for a 10% raster.
        return QRectF(0, 0, self._reference_size.width(), self._reference_size.height())

    def _mark_rect(self, rect, color, opacity=35):
        item = MultiplyHighlightItem(rect)
        shade = QColor(color)
        shade.setAlphaF(float(opacity)/100)
        item.setBrush(QBrush(shade))
        item.setPen(QPen(Qt.PenStyle.NoPen))
        item.setZValue(3)
        self.canvas_scene.addItem(item)
        self._marks.append(item)
        return item

    def _clamp_scene(self, pos):
        bounds = self._page_bounds()
        point = self.mapToScene(pos)
        return QPointF(max(0, min(bounds.width(), point.x())),
                       max(0, min(bounds.height(), point.y())))

    def _cancel_eraser_drag(self):
        """Restore temporarily hidden graphics when a gesture is interrupted."""
        for item in getattr(self, '_eraser_hidden', {}):
            if item.scene() is self.canvas_scene:
                item.setVisible(True)
        self._eraser_hidden = {}
        self._eraser_indexes = set()
        self._eraser_last = None
        self._eraser_dragging = False

    def _erase_along_segment(self, point):
        """Hit-test the visible vector shapes *along* the pointer path.

        Intermediate scene samples avoid skipping thin marks during fast mouse
        motion. Only one scene hit-test is done per small segment; the full
        annotation list is never scanned on each move.
        """
        previous = self._eraser_last or point
        length = math.hypot(point.x()-previous.x(), point.y()-previous.y())
        steps = min(750, max(1, math.ceil(length / 3.0)))
        for n in range(steps + 1):
            t = n / steps
            sample = QPointF(previous.x() + t*(point.x()-previous.x()),
                             previous.y() + t*(point.y()-previous.y()))
            item, index = self._stroke_hit(sample)
            if item is None or index is None or index < 0 or index in self._eraser_indexes:
                continue
            self._eraser_indexes.add(index)
            self._eraser_hidden[item] = index
            item.setVisible(False)  # visual feedback, no save/history yet
        self._eraser_last = point

    def _finish_eraser_drag(self, point):
        if not self._eraser_dragging:
            return
        self._erase_along_segment(point)
        indexes = sorted(self._eraser_indexes)
        self._cancel_eraser_drag()  # restore preview before history rebuild
        if indexes:
            self.strokesEraseGestureRequested.emit(indexes)

    def clear_ocr_regions(self):
        self._ocr_edge_timer.stop()
        self._ocr_drag = None
        self._ocr_dragging = False
        self._ocr_regions.clear()
        self._refresh_ocr_overlay()
        self.ocrRegionsChanged.emit(0)

    def undo_ocr_region(self):
        if self._ocr_regions and not self._ocr_dragging:
            self._ocr_regions.pop()
            self._refresh_ocr_overlay()
            self.ocrRegionsChanged.emit(len(self._ocr_regions))

    def select_whole_ocr_page(self):
        if self.image_item.pixmap().isNull():
            return
        self._ocr_regions = [QRectF(0, 0, 1, 1)]
        self._refresh_ocr_overlay()
        self.ocrRegionsChanged.emit(1)

    def ocr_regions(self):
        return [(r.x(), r.y(), r.width(), r.height()) for r in self._ocr_regions
                if r.width() > .0001 and r.height() > .0001]

    def set_ocr_colour(self, colour: str):
        self._ocr_colour = QColor(colour)
        self._refresh_ocr_overlay()

    def _ocr_scene_rect(self, rect: QRectF) -> QRectF:
        bounds = self._page_bounds()
        return QRectF(rect.left()*bounds.width(), rect.top()*bounds.height(),
                      rect.width()*bounds.width(), rect.height()*bounds.height())

    def _refresh_ocr_overlay(self):
        for item in self._ocr_outline_items:
            self.canvas_scene.removeItem(item)
        self._ocr_outline_items.clear()
        bounds = self._page_bounds()
        if self.annotation_tool != 'ocr' or bounds.isEmpty():
            self._ocr_mask.setVisible(False)
            return
        bright = QPainterPath()
        for i, rect in enumerate(self._ocr_regions):
            visible = self._ocr_scene_rect(rect)
            if visible.isEmpty():
                continue
            shape = QPainterPath()
            shape.addRect(visible)
            bright = bright.united(shape)
            item = QGraphicsRectItem(visible)
            item.setZValue(102)
            item.setPen(QPen(self._ocr_colour, 2.0/max(.15,abs(self.transform().m11())),
                             Qt.PenStyle.DashLine))
            item.setBrush(QBrush(QColor(255, 255, 255, 32)))
            item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            self.canvas_scene.addItem(item)
            self._ocr_outline_items.append(item)
            tag = QGraphicsSimpleTextItem(str(i+1))
            tag.setBrush(QBrush(self._ocr_colour))
            tag.setZValue(103)
            tag.setPos(visible.topLeft())
            tag.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            self.canvas_scene.addItem(tag)
            self._ocr_outline_items.append(tag)
            # A screen-sized corner handle communicates that boxes can be
            # resized even when the PDF is zoomed very far out or in.
            handle = QGraphicsEllipseItem(-4, -4, 8, 8)
            handle.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
            handle.setPos(visible.bottomRight())
            handle.setPen(QPen(QColor('white'), 1.1))
            handle.setBrush(QBrush(self._ocr_colour))
            handle.setZValue(104)
            handle.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            self.canvas_scene.addItem(handle)
            self._ocr_outline_items.append(handle)
        outside = QPainterPath()
        outside.addRect(bounds)
        self._ocr_mask.setPath(outside.subtracted(bright))
        self._ocr_mask.setBrush(QBrush(QColor(23, 34, 46, 94)))
        self._ocr_mask.setPen(QPen(Qt.PenStyle.NoPen))
        self._ocr_mask.setVisible(True)

    def _ocr_norm_point(self, viewport_point: QPoint) -> QPointF:
        point = self._clamp_scene(viewport_point)
        bounds = self._page_bounds()
        return QPointF(point.x()/max(1, bounds.width()),
                       point.y()/max(1, bounds.height()))

    def _ocr_start_drag(self, viewport_point: QPoint):
        if self._ocr_dragging or len(self._ocr_regions) >= MAX_REGIONS:
            return
        point = self._ocr_norm_point(viewport_point)
        scale = abs(self.transform().m11())
        bounds = self._page_bounds()
        hit_x = 11/max(1, bounds.width()*max(.05,scale))
        hit_y = 11/max(1, bounds.height()*max(.05,scale))
        for i in range(len(self._ocr_regions)-1, -1, -1):
            rect = self._ocr_regions[i]
            if (abs(point.x()-rect.right()) < hit_x and
                    abs(point.y()-rect.bottom()) < hit_y):
                self._ocr_drag = ('resize', i, point, QRectF(rect))
                break
            if rect.contains(point):
                self._ocr_drag = ('move', i, point, QRectF(rect))
                break
        else:
            rect = QRectF(point, point)
            self._ocr_regions.append(rect)
            self._ocr_drag = ('draw', len(self._ocr_regions)-1, point, QRectF(rect))
        self._ocr_pointer = QPoint(viewport_point)
        self._ocr_dragging = True
        self._ocr_edge_timer.start()
        self._refresh_ocr_overlay()

    def _ocr_update_drag(self, viewport_point: QPoint):
        if not self._ocr_dragging or self._ocr_drag is None:
            return
        self._ocr_pointer = QPoint(viewport_point)
        kind, index, origin, old = self._ocr_drag
        point = self._ocr_norm_point(viewport_point)
        if kind == 'draw':
            rect = QRectF(origin, point).normalized()
        elif kind == 'resize':
            rect = QRectF(old.topLeft(), point).normalized()
        else:
            dx, dy = point.x() - origin.x(), point.y() - origin.y()
            rect = QRectF(max(0, min(1-old.width(), old.x()+dx)),
                          max(0, min(1-old.height(), old.y()+dy)),
                          old.width(), old.height())
        self._ocr_regions[index] = rect
        self._refresh_ocr_overlay()

    def _ocr_autoscroll(self):
        if not self._ocr_dragging:
            self._ocr_edge_timer.stop()
            return
        p = self._ocr_pointer
        viewport = self.viewport()
        edge = 34
        for sb, pos, size in ((self.verticalScrollBar(), p.y(), viewport.height()),
                              (self.horizontalScrollBar(), p.x(), viewport.width())):
            if pos < edge:
                amount = -max(1, round((edge-pos)*.42))
            elif pos > size-edge:
                amount = max(1, round((pos-(size-edge))*.42))
            else:
                amount = 0
            if amount:
                sb.setValue(sb.value()+amount)
        self._ocr_update_drag(p)

    def _ocr_finish_drag(self, viewport_point: QPoint):
        self._ocr_edge_timer.stop()
        self._ocr_update_drag(viewport_point)
        self._ocr_dragging = False
        self._ocr_drag = None
        # Treat small clicks in empty space as no selection.
        self._ocr_regions = [r for r in self._ocr_regions
                             if r.width() > .001 and r.height() > .001]
        self._refresh_ocr_overlay()
        self.ocrRegionsChanged.emit(len(self._ocr_regions))

    def keyPressEvent(self, event):
        if self.annotation_tool == 'ocr':
            if event.key() in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete):
                self.undo_ocr_region()
                event.accept()
                return
            if event.key() == Qt.Key.Key_Escape:
                self.ocrCancelRequested.emit()
                event.accept()
                return
            if event.key() == Qt.Key.Key_A and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                self.select_whole_ocr_page()
                event.accept()
                return
        super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and not self.image_item.pixmap().isNull():
            point = self._clamp_scene(event.position().toPoint())
            bounds = self._page_bounds()
            if bounds.isEmpty():
                event.accept()
                return
            if self.annotation_tool == 'ocr':
                self._ocr_start_drag(event.position().toPoint())
                event.accept()
                return
            if self.annotation_tool in ('pen', 'marker'):
                self._stroke_points = [[point.x()/bounds.width(), point.y()/bounds.height()]]
                tool = self.annotation_tool
                style = self._tool_style(tool)
                self._live_stroke = self._draw_stroke(
                    {'points': [self._stroke_points[0]], 'color': style['color'],
                     'width': style['width'], 'opacity': style['opacity'],
                     'blend': 'multiply' if tool == 'marker' else 'normal'}, -1)
                event.accept()
                return
            if self.annotation_tool in ('line', 'arrow', 'rectangle', 'ellipse',
                                        'highlight_line'):
                self._shape_origin = point
                self._shape_end = point
                candidate = self._live_shape_mark(point, event.modifiers())
                self._shape_preview = (self._draw_highlight(candidate, -1)
                    if self.annotation_tool == 'highlight_line'
                    else self._draw_shape(candidate, -1))
                event.accept()
                return
            if self.annotation_tool == 'eraser':
                self._eraser_dragging = True
                self._eraser_last = point
                self._eraser_indexes.clear()
                self._eraser_hidden.clear()
                self._erase_along_segment(point)
                event.accept()
                return
            if self.annotation_tool == 'select':
                if self.annotation_tool == 'select' and self._selected_stroke is not None:
                    handle = self._hit_resize_handle(point)
                    if handle:
                        self._resize_handle = handle
                        self._resize_mark = self._item_marks[self._selected_stroke]
                        self._resize_index = self._stroke_items[self._selected_stroke]
                        self.editingGesture.emit(True)
                        event.accept()
                        return
                item, index = self._stroke_hit(point)
                if item is not None and index >= 0:
                    if self._selected_stroke is not None:
                        self._selected_stroke.setSelected(False)
                    item.setSelected(True)
                    self._selected_stroke = item
                    self._stroke_drag_start = point
                    self._stroke_drag_origin = QPointF(item.pos())
                    self._show_resize_handles()
                    self.annotationSelected.emit(index, self._item_marks[item])
                    self.editingGesture.emit(True)
                    event.accept()
                    return
                if self._selected_stroke is not None:
                    self._selected_stroke.setSelected(False)
                self._selected_stroke = None
                self._clear_resize_handles()
                self.annotationSelected.emit(-1, None)
                event.accept()
                return
            if self.annotation_tool == 'highlight':
                self._highlight_origin = point
                self._live_highlight = self._mark_rect(
                    QRectF(point, point), self._tool_style('highlight')['color'],
                    self._tool_style('highlight')['opacity'])
                event.accept()
                return
        super().mousePressEvent(event)

    def _shape_endpoint(self, point, modifiers):
        """Shift constrains square/circle or 45° line; Alt draws from centre."""
        first = self._shape_origin
        dx, dy = point.x() - first.x(), point.y() - first.y()
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            if self.annotation_tool in ('rectangle', 'ellipse'):
                side = max(abs(dx), abs(dy))
                dx = math.copysign(side, dx or 1.)
                dy = math.copysign(side, dy or 1.)
            else:
                length = math.hypot(dx, dy)
                angle = round(math.atan2(dy, dx)/(math.pi/4))*(math.pi/4)
                dx, dy = length*math.cos(angle), length*math.sin(angle)
        end = QPointF(first.x() + dx, first.y() + dy)
        if modifiers & Qt.KeyboardModifier.AltModifier:
            first = QPointF(first.x() - dx, first.y() - dy)
        bounds = self._page_bounds()
        def clamp(p):
            return QPointF(max(0., min(bounds.width(), p.x())),
                           max(0., min(bounds.height(), p.y())))
        return clamp(first), clamp(end)

    def _live_shape_mark(self, point, modifiers):
        first, end = self._shape_endpoint(point, modifiers)
        bounds = self._page_bounds()
        style = self._tool_style()
        mark = {'kind': 'highlight_line' if self.annotation_tool == 'highlight_line' else 'shape',
                'x1': first.x()/bounds.width(), 'y1': first.y()/bounds.height(),
                'x2': end.x()/bounds.width(), 'y2': end.y()/bounds.height(),
                'color': style['color'], 'opacity': style['opacity'],
                'width': style['width']}
        if self.annotation_tool != 'highlight_line':
            mark['shape'] = self.annotation_tool
            mark['stroke_enabled'] = style.get('stroke_enabled', True)
            mark['fill'] = (style.get('fill')
                            if self.annotation_tool in ('rectangle', 'ellipse') else None)
            mark['fill_opacity'] = style.get('fill_opacity', 30)
            if self.annotation_tool == 'arrow':
                mark['head_width'] = style.get('head_width', .018)
                mark['head_length'] = style.get('head_length', .025)
        return mark

    def mouseMoveEvent(self, event):
        if self._ocr_dragging:
            self._ocr_update_drag(event.position().toPoint())
            event.accept()
            return
        if self._eraser_dragging:
            # Even if the cursor crosses an empty region, only button-held
            # gestures erase; simple hovering leaves all marks untouched.
            if not (event.buttons() & Qt.MouseButton.LeftButton):
                self._finish_eraser_drag(self._clamp_scene(event.position().toPoint()))
            else:
                self._erase_along_segment(self._clamp_scene(event.position().toPoint()))
            event.accept()
            return
        if self._stroke_points is not None and self._live_stroke is not None:
            bounds = self._page_bounds()
            point = self._clamp_scene(event.position().toPoint())
            x, y = point.x()/bounds.width(), point.y()/bounds.height()
            last = self._stroke_points[-1]
            if (len(self._stroke_points) < MAX_STROKE_POINTS and
                    (x-last[0])**2 * bounds.width()**2 +
                    (y-last[1])**2 * bounds.height()**2 >= 0.8**2):
                self._stroke_points.append([x, y])
                # Rebuild only the transient path, never append to an
                # uninitialised Qt painter position near the page origin.
                self._live_stroke.setPath(self._stroke_path(self._stroke_points))
            event.accept()
            return
        if self._shape_origin is not None and self._shape_preview is not None:
            point = self._clamp_scene(event.position().toPoint())
            self._shape_end = point
            self._shape_preview.setPath(self._shape_path(
                self._live_shape_mark(point, event.modifiers())))
            event.accept()
            return
        if self._resize_handle is not None and self._selected_stroke is not None:
            point = self._clamp_scene(event.position().toPoint())
            bounds = self._page_bounds()
            try:
                proposal = resized_vector(self._resize_mark, self._resize_handle,
                                          point.x()/bounds.width(), point.y()/bounds.height(),
                                          keep_aspect=bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier),
                                          from_center=bool(event.modifiers() & Qt.KeyboardModifier.AltModifier))
            except ValueError:
                event.accept()
                return
            item = self._selected_stroke
            item.setPath(self._shape_path(proposal) if proposal['kind'] != 'stroke'
                         else self._stroke_path(proposal['points']))
            self._item_marks[item] = proposal
            self._show_resize_handles()
            event.accept()
            return
        if self._stroke_drag_start is not None and self._selected_stroke is not None:
            point = self._clamp_scene(event.position().toPoint())
            self._selected_stroke.setPos(self._stroke_drag_origin +
                                         (point - self._stroke_drag_start))
            self._show_resize_handles()
            event.accept()
            return
        if self._highlight_origin is not None and self._live_highlight:
            point = self._clamp_scene(event.position().toPoint())
            self._live_highlight.setRect(QRectF(self._highlight_origin, point).normalized())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._ocr_dragging and event.button() == Qt.MouseButton.LeftButton:
            self._ocr_finish_drag(event.position().toPoint())
            event.accept()
            return
        if self._eraser_dragging and event.button() == Qt.MouseButton.LeftButton:
            self._finish_eraser_drag(self._clamp_scene(event.position().toPoint()))
            event.accept()
            return
        if self._stroke_points is not None:
            points = self._stroke_points
            if len(points) == 1:
                # A tap is a round dot, not an invisible zero-length path.
                x, y = points[0]
                points = [points[0], [min(1.0, x + 0.00001), y]]
            marker = self.annotation_tool == 'marker'
            style = self._tool_style()
            mark = make_stroke(points, style['color'], style['width'],
                               blend='multiply' if marker else 'normal',
                               opacity=style['opacity'])
            self._stroke_points = None
            if self._live_stroke in self._marks:
                self._marks.remove(self._live_stroke)
                self._stroke_items.pop(self._live_stroke, None)
                self._item_marks.pop(self._live_stroke, None)
                self.canvas_scene.removeItem(self._live_stroke)
            self._live_stroke = None
            self.strokeCreated.emit(mark)
            event.accept()
            return
        if self._shape_origin is not None and self._shape_preview is not None:
            point = self._clamp_scene(event.position().toPoint())
            candidate = self._live_shape_mark(point, event.modifiers())
            bounds = self._page_bounds()
            self._shape_origin = None
            self._shape_end = None
            self._marks.remove(self._shape_preview)
            self._stroke_items.pop(self._shape_preview, None)
            self._item_marks.pop(self._shape_preview, None)
            self.canvas_scene.removeItem(self._shape_preview)
            self._shape_preview = None
            length = math.hypot((candidate['x2'] - candidate['x1'])*bounds.width(),
                                (candidate['y2'] - candidate['y1'])*bounds.height())
            if length >= 3.:
                first = (candidate['x1'], candidate['y1'])
                last = (candidate['x2'], candidate['y2'])
                if candidate['kind'] == 'highlight_line':
                    self.highlightCreated.emit(make_highlight_line(
                        first, last, candidate['color'], candidate['width'],
                        candidate['opacity']))
                else:
                    self.shapeCreated.emit(make_shape(
                        candidate['shape'], first, last, candidate['color'],
                        candidate['width'], candidate['fill'],
                        opacity=candidate['opacity'],
                        fill_opacity=candidate['fill_opacity'],
                        stroke_enabled=candidate['stroke_enabled'],
                        head_width=candidate.get('head_width'),
                        head_length=candidate.get('head_length')))
            event.accept()
            return
        if self._resize_handle is not None and self._selected_stroke is not None:
            point = self._clamp_scene(event.position().toPoint())
            bounds = self._page_bounds()
            index = self._resize_index
            old = self._resize_mark
            handle = self._resize_handle
            self._resize_handle = None
            self._resize_mark = None
            self._resize_index = None
            try:
                result = resized_vector(old, handle,
                                        point.x()/bounds.width(), point.y()/bounds.height(),
                                        keep_aspect=bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier),
                                        from_center=bool(event.modifiers() & Qt.KeyboardModifier.AltModifier))
            except ValueError:
                result = old
            if result != old and index is not None and index >= 0:
                self._clear_resize_handles()
                self.strokeResized.emit(index, result)
            else:
                self._selected_stroke.setPath(self._shape_path(old) if old['kind'] != 'stroke'
                                              else self._stroke_path(old['points']))
                self._item_marks[self._selected_stroke] = old
                self._show_resize_handles()
            self.editingGesture.emit(False)
            event.accept()
            return
        if self._stroke_drag_start is not None and self._selected_stroke is not None:
            point = self._clamp_scene(event.position().toPoint())
            delta = point - self._stroke_drag_start
            index = self._stroke_items.get(self._selected_stroke)
            self._selected_stroke.setPos(self._stroke_drag_origin)
            self._stroke_drag_start = None
            if (index is not None and index >= 0 and
                    abs(delta.x()) + abs(delta.y()) > 0.75):
                self._clear_resize_handles()
                self.strokeMoved.emit(index, {'dx': delta.x()/self._page_bounds().width(),
                                              'dy': delta.y()/self._page_bounds().height()})
            else:
                self._show_resize_handles()
            self.editingGesture.emit(False)
            event.accept()
            return
        if self._highlight_origin is not None and self._live_highlight:
            rect = self._live_highlight.rect()
            bounds = self._page_bounds()
            if rect.width() >= 3 and rect.height() >= 3 and not bounds.isEmpty():
                style = self._tool_style('highlight')
                self.highlightCreated.emit(make_highlight(
                    (rect.left()/bounds.width(), rect.top()/bounds.height(),
                     rect.width()/bounds.width(), rect.height()/bounds.height()),
                    style['color'], style['opacity']))
            else:
                self.canvas_scene.removeItem(self._live_highlight)
                self._marks.remove(self._live_highlight)
            self._highlight_origin = None
            self._live_highlight = None
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _native_magnify(self, event):
        """Zoom by a small *incremental* gesture value around the pinch point.

        The pan under the user's fingers is anchored in scene coordinates to
        avoid the disorienting jump caused by anchoring only to mouse location.
        """
        if event.gestureType() == Qt.NativeGestureType.ZoomNativeGesture:
            self._last_native_zoom_at = time.monotonic()
            factor = math.exp(max(-0.24, min(0.24, float(event.value()) * 1.7)))
            self.zoom(factor, self.mapFromGlobal(QCursor.pos()))
            event.accept()
            return True
        return False

    def viewportEvent(self, event):
        if event.type() == QEvent.Type.NativeGesture and self._native_magnify(event):
            return True
        if event.type() == QEvent.Type.Gesture:
            pinch = event.gesture(Qt.GestureType.PinchGesture)
            if pinch and pinch.lastScaleFactor():
                # Some Qt/macOS versions deliver both native AND Qt pinch
                # signals. Handle only one to avoid multiplying each movement.
                if time.monotonic() - self._last_native_zoom_at > .12:
                    self.zoom(pinch.scaleFactor() / pinch.lastScaleFactor())
                event.accept()
                return True
        return super().viewportEvent(event)

    def event(self, event):
        if event.type() == QEvent.Type.NativeGesture and self._native_magnify(event):
            return True
        return super().event(event)

    def wheelEvent(self, event):
        if event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier):
            dy = event.pixelDelta().y() if not event.pixelDelta().isNull() else event.angleDelta().y()
            if dy:
                factor = math.exp(max(-.20, min(.20, dy * (.002 if not event.pixelDelta().isNull() else .0014))))
                self.zoom(factor, event.position().toPoint())
            event.accept()
            return
        # Native trackpad pixels + kinetic scrolling already have momentum;
        # don't add artificial easing or a second scrolling animation.
        if not event.pixelDelta().isNull():
            super().wheelEvent(event)
            return
        # Regular mouse wheel panning can keep Qt's default step behaviour.
        # More aggressive animation here would interfere with zoom anchors.
        super().wheelEvent(event)

    def _sync_page_sampling(self):
        """Keep Lanczos-shrunk image crisp at (near) 1:1 screen pixels.

        This affects the *preview item only*, never highlighter drawing or
        UI widgets. No re-render and no additional image is produced.
        """
        if self.image_item.pixmap().isNull():
            return
        screen = self.screen()
        dpr = max(1.0, float(screen.devicePixelRatio()) if screen else 1.0)
        pixel_ratio = abs(self.transform().m11() * self.image_item.scale()) * dpr
        self.image_item.setTransformationMode(
            Qt.TransformationMode.FastTransformation
            if is_near_native_pixel_ratio(pixel_ratio)
            else Qt.TransformationMode.SmoothTransformation)

    def _emit_zoom(self):
        self._sync_page_sampling()
        self._schedule_bicubic()
        if self.image_item.pixmap().isNull():
            self.zoomChanged.emit(0.0, False)
        else:
            self.zoomChanged.emit(abs(self.transform().m11()) * 100.0, self._fit)

    def replace_quality_image(self, path: Path) -> bool:
        """Replace the displayed page from its disposable JPEG cache."""
        if self._reference_size.isEmpty() or not path:
            return False
        reader = QImageReader(str(path))
        reader.setAutoTransform(True)
        image = reader.read()
        if image.isNull():
            return False
        return self._replace_quality_pixmap(QPixmap.fromImage(image))

    def replace_quality_rgb(self, width: int, height: int, pixels: bytes) -> bool:
        """Display optional low-zoom clarity pixels; never write new caches.

        RGB bytes are prepared on a worker, then deeply copied on the GUI
        thread. The canvas still holds just one displayed page pixmap.
        """
        if (width < 1 or height < 1 or width * height > 12_000_000
                or len(pixels) != width * height * 3):
            return False
        image = QImage(pixels, width, height, width * 3,
                       QImage.Format.Format_RGB888).copy()
        if image.isNull():
            return False
        return self._replace_quality_pixmap(QPixmap.fromImage(image))

    def _replace_quality_pixmap(self, pixmap: QPixmap) -> bool:
        """Preserve the scene coordinates, zoom, scroll and vector highlights."""
        if self._reference_size.isEmpty() or pixmap.isNull():
            return False
        # Note that setScale() scales only the graphics item, NOT the view.
        # Scene coordinates stay stable across all rendering tiers.
        factor = self._reference_size.width() / max(1, pixmap.width())
        self.stop_bicubic()
        self.image_item.setPixmap(pixmap)
        self.image_item.setScale(factor)
        self._sync_page_sampling()
        self.canvas_scene.setSceneRect(self._page_bounds())
        self._refresh_ocr_overlay()
        self._schedule_bicubic()
        self.viewport().update()
        return True

    def show_image(self, path: Path | None):
        self.clear_ocr_regions()
        # QPixmap(path) implicitly populates Qt's process-global pixmap cache.
        # QImageReader -> QPixmap avoids that hidden second copy. Clearing the
        # scene item then actually releases the active page's large bitmap.
        if path:
            reader = QImageReader(str(path))
            reader.setAutoTransform(True)
            decoded = reader.read()
            pixmap = QPixmap.fromImage(decoded) if not decoded.isNull() else QPixmap()
        else:
            pixmap = QPixmap()
        self.stop_bicubic()
        self.clear_marks()
        self.image_item.setScale(1.0)
        self.image_item.setPixmap(pixmap)
        self._reference_size = pixmap.size()
        self.canvas_scene.setSceneRect(self._page_bounds())
        self._refresh_ocr_overlay()
        self.fit_page()
        return not pixmap.isNull()

    def capture_reading_position(self):
        """Save the scene coordinate at the viewport's top-left (not scrollbar px)."""
        if self.image_item.pixmap().isNull():
            return None
        rect = self._page_bounds()
        if rect.width() <= 0 or rect.height() <= 0:
            return None
        top_left = self.mapToScene(QPoint(0, 0))
        x = max(0.0, min(1.0, (top_left.x() - rect.left()) / rect.width()))
        y = max(0.0, min(1.0, (top_left.y() - rect.top()) / rect.height()))
        vertical = self.verticalScrollBar()
        return {'x': round(x, 7), 'y': round(y, 7),
                'bottom': (vertical.maximum() > 0 and
                           vertical.value() >= vertical.maximum() - 2)}

    def apply_reading_zoom(self, saved):
        """Apply Fit or absolute view scale; never render an extra PDF bitmap."""
        if self.image_item.pixmap().isNull():
            return
        if not saved or saved.get('mode') != 'manual':
            self.fit_page()
            return
        level = float(saved.get('scale', 1.0))
        if not math.isfinite(level) or not 0.03 <= level <= 15:
            self.fit_page()
            return
        self._fit = False
        self.resetTransform()
        self.scale(level, level)
        self._emit_zoom()

    def restore_reading_position(self, saved=None, *, start_at_top=True):
        """Reposition using page-relative coordinates across window sizes/DPI.

        An unvisited page begins at its top edge, with horizontal centring.
        Previously visited pages use their own scroll memory, never a group
        scroll position. If the viewport is taller than the image, alignment
        rules are used rather than inventing empty scroll range.
        """
        if self.image_item.pixmap().isNull():
            return
        rect = self._page_bounds()
        if rect.isEmpty():
            return
        scale = max(0.0001, abs(self.transform().m11()))
        visible_w = max(1, self.viewport().width()) / scale
        visible_h = max(1, self.viewport().height()) / scale
        range_x = max(0.0, rect.width() - visible_w)
        range_y = max(0.0, rect.height() - visible_h)
        if saved:
            x = max(0.0, min(1.0, float(saved.get('x', 0.0)))) * rect.width()
            y = max(0.0, min(1.0, float(saved.get('y', 0.0)))) * rect.height()
            if saved.get('bottom'):
                y = range_y
        else:
            x = range_x * .5  # centre columns on an unvisited zoomed page
            y = 0.0 if start_at_top else range_y * .5
        x = min(range_x, max(0.0, x))
        y = min(range_y, max(0.0, y))
        self.centerOn(QPointF(rect.left() + x + visible_w * .5,
                              rect.top() + y + visible_h * .5))
        self._schedule_bicubic()

    def fit_page(self):
        self._fit = True
        self.resetTransform()
        self._zoom_factor = 1.0
        if not self.image_item.pixmap().isNull():
            self.fitInView(self._page_bounds(), Qt.AspectRatioMode.KeepAspectRatio)
        self._emit_zoom()

    def zoom(self, multiplier: float, anchor_pos=None):
        """Continuous scale change without rerendering or reallocating the PDF.

        For trackpad gestures, keep the image point under the fingers stationary
        rather than zooming from an unrelated mouse-cursor position.
        """
        if self.image_item.pixmap().isNull() or not 0.03 < multiplier < 15:
            return
        current = abs(self.transform().m11())
        if not 0.03 <= current * multiplier <= 15:
            return
        point = anchor_pos if anchor_pos is not None else self.viewport().rect().center()
        point = QPoint(max(0, min(self.viewport().width(), point.x())),
                       max(0, min(self.viewport().height(), point.y())))
        before = self.mapToScene(point)
        self._fit = False
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.scale(multiplier, multiplier)
        after = self.mapToScene(point)
        centre = self.mapToScene(self.viewport().rect().center())
        self.centerOn(centre + (before - after))
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self._emit_zoom()

    def disable_fit(self):
        '''Lock the current display transform while turning auto-fit off.'''
        if self._fit:
            self._fit = False
            self._emit_zoom()

    def actual_pixels(self):
        self._fit = False
        self.resetTransform()
        self._emit_zoom()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._fit:
            self.fit_page()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            self.filesDropped.emit([u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()])
            event.acceptProposedAction()
        else:
            super().dropEvent(event)


class AnnotationChangeCommand(QUndoCommand):
    """Reversible page-mark edit, identified by stable page ID.

    The compact before/after snapshots let us support future mark types without
    coupling them to rich-text storage. The shared manager now coordinates all actions.
    """
    def __init__(self, pane, page_id: str, before: list, after: list, title: str):
        super().__init__(title)
        self.pane = pane
        self.page_id = page_id
        self.before = copy.deepcopy(before)
        self.after = copy.deepcopy(after)

    def undo(self):
        self.pane._apply_annotation_snapshot(self.page_id, self.before)

    def redo(self):
        self.pane._apply_annotation_snapshot(self.page_id, self.after)


class ProjectPane(QWidget):
    """Three-panel study workspace for one tab, including per-tab UI state.

    IMPORTANT: a previewed page is NOT necessarily an explicitly selected
    navigator page. The two states stay separate to protect paste/import
    insertion positions. Background workers must never mutate Qt widgets;
    completion handlers run on the GUI thread and ignore stale generations.
    """
    notebookDropped = Signal(str)  # external notebook file, not a preview page
    readingChanged = Signal()
    readingAction = Signal(str, str, int)  # manual checkbox only: level, title, count delta
    ocrProgress = Signal(int, int)
    titleChanged = Signal(str)
    statusMessage = Signal(str)

    def __init__(self, project: Project, settings: QSettings, parent=None):
        super().__init__(parent)
        self.project = project
        self._tab_id = project.identifier  # overridden by Notebook tab ID when attached
        self.settings = settings
        self._loading = False
        self._active = False
        self._closed = False
        self._importing = False
        # A standalone ProjectPane has local history; MainWindow replaces it
        # with the notebook-wide shared manager when the pane is attached.
        self.history = UnifiedHistory()
        self._generation = 0
        self._thumb_pending: set[tuple[int, str]] = set()
        self._thumb_failed: set[str] = set()
        self._preview_token = 0
        # Tracks the image actually on canvas (selection changes first).
        self._view_displayed_page_id = None
        self._session_reading_view = empty_view()
        self._view_restoring = False
        self._view_scroll_timer = QTimer(self)
        self._view_scroll_timer.setSingleShot(True)
        self._view_scroll_timer.setInterval(650)
        self._view_scroll_timer.timeout.connect(
            self._capture_displayed_reading_position)
        self._quality_token = 0
        self._quality_level = 1.0
        self._normal_preview_path = None
        self._displayed_cache_path = None
        # Display-only sharpening for already Lanczos-downscaled previews.
        # Work occurs in one background job, with no extra cache files.
        self._clarity_token = 0
        self._clarity_in_flight = False
        self._clarity_applied_signature = None
        self._panel_order = list(PANEL_KEYS)
        self._reorder_token = str(id(self))
        self._thumbnail_bucket = 110
        self._quality_timer = QTimer(self)
        self._quality_timer.setSingleShot(True)
        self._quality_timer.setInterval(260)
        self._quality_timer.timeout.connect(self._update_adaptive_quality)
        # Coalesce resize repaints; no source PDF/page rendering occurs.
        self._thumb_rescale_timer = QTimer(self)
        self._thumb_rescale_timer.setSingleShot(True)
        self._thumb_rescale_timer.setInterval(180)
        self._thumb_rescale_timer.timeout.connect(self._rescale_visible_thumb_icons)
        self._loaded_thumb_rows: set[int] = set()
        self._wanted_thumbnail_ids: frozenset[str] = frozenset()
        # A dirty-only 60-second autosave.  The timer starts on the FIRST
        # edit and is NOT reset by later keystrokes (continuous writing is
        # still protected).  A successful save disarms it until the next edit.
        # Manual Save, closing, and tab switches still save immediately.
        self._dirty = False
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(60_000)
        self._save_timer.timeout.connect(self._autosave)
        self._thumb_timer = QTimer(self)
        self._thumb_timer.setSingleShot(True)
        self._thumb_timer.setInterval(90)
        self._thumb_timer.timeout.connect(self.update_visible_thumbnails)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        outer.addWidget(self.splitter)

        shelf = AmbientPanel()
        shelf.setObjectName('shelf')
        # The page shelf may shrink into a tiny thumbnail rail.  The real
        # minimum width stays small; layout controls adapt to avoid clipping.
        shelf.setMinimumWidth(74)
        self.shelf = shelf
        self.canvas_panel = None
        self._nav_mode = None
        self._navigator_requested_visible = str(self.settings.value('showPageNavigator', 'true')).lower() != 'false'
        self._navigator_visible = True  # the shelf begins as a visible splitter child
        self._navigator_restore_width = max(74, dict(zip(PANEL_KEYS, project.splitter_sizes)).get('pages', 225))
        sl = QVBoxLayout(shelf)
        self.shelf_layout = sl
        sl.setContentsMargins(8, 10, 7, 8)
        sl.setSpacing(5)
        title = QLabel('PAGES & IMAGES')
        title.setObjectName('sectionLabel')
        self.shelf_heading = title
        self.pages_header = PanelDropHeader('pages', self._reorder_token, title)
        self.pages_header.moveRequested.connect(self.move_workspace_panel)
        pages_heading_row = QHBoxLayout()
        pages_heading_row.setContentsMargins(0, 0, 0, 0)
        pages_heading_row.setSpacing(2)
        pages_heading_row.addWidget(self.pages_header, 1)
        self.navigator_previous = QToolButton()
        self.navigator_previous.setText('‹')
        self.navigator_previous.setFixedSize(24, 25)
        self.navigator_previous.setToolTip(
            f'Previous page · {PRIMARY}{ALT}↑' if IS_MAC
            else 'Previous page · Ctrl+Alt+Up')
        self.navigator_previous.clicked.connect(lambda: self.move_selection(-1))
        pages_heading_row.addWidget(self.navigator_previous)
        self.navigator_next = QToolButton()
        self.navigator_next.setText('›')
        self.navigator_next.setFixedSize(24, 25)
        self.navigator_next.setToolTip(
            f'Next page · {PRIMARY}{ALT}↓' if IS_MAC
            else 'Next page · Ctrl+Alt+Down')
        self.navigator_next.clicked.connect(lambda: self.move_selection(1))
        pages_heading_row.addWidget(self.navigator_next)
        sl.addLayout(pages_heading_row)
        self.counter = QLabel('0 pages')
        self.counter.setObjectName('hintLabel')
        sl.addWidget(self.counter)
        # A small, calm per-tab completion display.  It includes pages
        # under collapsed folders and ungrouped pages alike.
        self.reading_summary = QLabel('Read 0 / 0')
        self.reading_summary.setObjectName('hintLabel')
        sl.addWidget(self.reading_summary)
        self.reading_progress = ReadingProgressBar()
        self.reading_progress.setObjectName('readingProgress')
        self.reading_progress.set_reduced_motion(
            str(self.settings.value('reducedMotion', 'false')).lower() == 'true')
        self.reading_progress.setFixedHeight(6)
        self.reading_progress.setTextVisible(False)
        sl.addWidget(self.reading_progress)
        # Flow layout, not a horizontal row: the splitter can always shrink.
        actions = WrapBar('Navigator controls')
        self.import_button = QToolButton()
        self.import_button.setObjectName('insertPlus')
        self.import_button.setText('+Add')
        self.import_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.import_button.setToolTip('Insert a file or blank page after the selected page')
        self.add_page_menu = QMenu(self.import_button)
        self.add_page_menu.addAction(
            'Import…', lambda: self.choose_files(
                self._selected_insertion_index()))
        self.add_page_menu.addAction(
            'Smart Import…', lambda: self.choose_files(
                self._selected_insertion_index(), smart_default=True))
        self.add_page_menu.addAction('Add Blank Page', self.add_blank)
        self.import_button.setMenu(self.add_page_menu)
        actions.addWidget(self.import_button)
        # Kept as a compatibility alias; there is only one user-visible + menu.
        self.blank_button = QToolButton(self)
        self.blank_button.hide()

        # Clicking this always cycles Normal → Compact → Mini → Normal.
        # Dragging the splitter manually chooses a mode automatically, so
        # there is no extra settings switch to remember.
        self.nav_cycle = QToolButton()
        self.nav_cycle.setText('▦')
        self.nav_cycle.setFixedWidth(29)
        self.nav_cycle.clicked.connect(self.cycle_navigator_mode)
        actions.addWidget(self.nav_cycle)

        self.nav_overflow = QToolButton()
        self.nav_overflow.setText('⋯')
        self.nav_overflow.setFixedWidth(29)
        self.nav_overflow.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.nav_overflow.setToolTip('Page actions · import, blank, rename, remove, undo and reorder')
        self.nav_menu = QMenu(self.nav_overflow)
        self.nav_menu.addAction('Import pages…', lambda: self.choose_files())
        self.nav_menu.addAction(
            'Smart Import…', lambda: self.choose_files(smart_default=True))
        self.nav_menu.addAction('Add blank page', self.add_blank)
        self.nav_menu.addAction('Create page group…',
                                lambda: self.create_page_group(root=True))
        self.nav_menu.addSeparator()
        self.nav_menu.addAction('Rename selected page', self.rename_page)
        self.nav_menu.addAction('Remove selected pages · Delete', self.remove_page)
        self._nav_undo_action = self.nav_menu.addAction(f'Undo · {PRIMARY}Z', self.undo_remove_pages)
        self.nav_menu.aboutToShow.connect(self._update_page_undo_availability)
        self.nav_menu.addSeparator()
        self.nav_menu.addAction('Move page earlier', lambda: self.move_page(-1))
        self.nav_menu.addAction('Move page later', lambda: self.move_page(1))
        self.nav_overflow.setMenu(self.nav_menu)
        actions.addWidget(self.nav_overflow)
        sl.addWidget(actions)
        self.pages_list = DropPageList()
        if str(self.settings.value('reducedMotion', 'false')).lower() == 'true':
            self.pages_list._hover_delegate.anim.setDuration(0)
        self.pages_list.filesDropped.connect(self.import_paths)
        self.pages_list.addAt.connect(self.choose_files_at)
        self.pages_list.blankAt.connect(self.add_blank)
        self.pages_list.orderChanged.connect(self.reorder_pages)
        self.pages_list.visibleAreaChanged.connect(self.schedule_thumbnails)
        self.pages_list.verticalScrollBar().valueChanged.connect(shelf.scroll_pulse)
        self.pages_list.currentItemChanged.connect(self.select_item)
        # Yomu v0.3.1 hotfix: Navigate the selected left-shelf page even
        # while writing in the notes column. Qt maps Ctrl to Cmd on macOS.
        # WidgetWithChildrenShortcut prevents shortcuts in an inactive tab
        # from affecting a different open project.
        self.project_page_shortcuts = []
        for keys, step in [('Ctrl+Alt+Up', -1), ('Ctrl+Alt+Down', 1)]:
            shortcut = QShortcut(QKeySequence(keys), self)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(lambda step=step: self.move_selection(step))
            self.project_page_shortcuts.append(shortcut)
        self.pages_list.setToolTip(
            'Select a page to show it in the centre.\n' +
            (f'Previous: {PRIMARY}{ALT}↑ · Next: {PRIMARY}{ALT}↓' if IS_MAC
             else 'Previous: Ctrl+Alt+Up · Next: Ctrl+Alt+Down') +
            '\nThese shortcuts also work while editing notes.'
        )
        self.pages_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.pages_list.customContextMenuRequested.connect(self.page_context_menu)
        self.page_shortcuts = []
        for keys, fn in [('Backspace', self.remove_page), ('Delete', self.remove_page),
                         ('Ctrl+A', self.pages_list.selectAll),
                         ('Alt+PgUp', lambda: self.move_selection(-1)),
                         ('Alt+PgDown', lambda: self.move_selection(1))]:
            shortcut = QShortcut(QKeySequence(keys), self.pages_list)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(fn)
            self.page_shortcuts.append(shortcut)
        # Groups are a VIEW over the existing flat page list.  The old
        # thumbnail list remains alive even while hidden, so selection,
        # page navigation and the preview renderer keep working unchanged.
        self.nav_views = QStackedWidget()
        self.nav_views.addWidget(self.pages_list)
        self.group_tree = PageGroupsTree()
        self.group_tree.set_reading_reduced_motion(
            str(self.settings.value('reducedMotion', 'false')).lower() == 'true')
        self.group_tree.tab_id = self._tab_id
        # Group thumbnails reuse the same cached 110 px page images.
        # The separate set helps us keep only visible icons in memory.
        self._group_thumb_pending = set()
        self._wanted_group_thumb_ids = frozenset()
        self.group_tree.verticalScrollBar().valueChanged.connect(
            lambda _: self.schedule_thumbnails())
        self.group_tree.filesDropped.connect(self.import_paths)
        self.group_tree.pagesPasted.connect(
            lambda source, target, ids, copying:
            self.pages_list.pagesPasted.emit(source, target, ids, copying))
        self.group_tree.pageActivated.connect(self.select_page_id)
        # Defer model changes until Qt has finished its current click.
        # Rebuilding QTreeWidget inside itemChanged/dropEvent can delete
        # the item while Qt still processes the mouse event.
        self.group_tree.readToggled.connect(
            lambda kind, pid, checked: QTimer.singleShot(
                0, lambda: self._toggle_read_status(kind, pid, checked)))
        self.group_tree.structureChanged.connect(self._group_tree_dropped)
        self.group_tree.groupMoveRequested.connect(
            lambda gid, parent, index: QTimer.singleShot(
                0, lambda: self._move_whole_group(gid, parent, index)))
        self.group_tree.collapseChanged.connect(self._group_collapse_changed)
        self.group_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.group_tree.customContextMenuRequested.connect(self.group_context_menu)
        self.nav_views.addWidget(self.group_tree)
        self.nav_view_buttons = QWidget()
        nav_switch = QHBoxLayout(self.nav_view_buttons)
        nav_switch.setContentsMargins(0, 0, 0, 0)
        nav_switch.setSpacing(4)
        self.show_groups_button = QToolButton()
        self.show_groups_button.setText('▸ Groups')
        self.show_groups_button.setToolTip('Organise pages into folders and subgroups')
        self.show_groups_button.setCheckable(True)
        self.show_groups_button.clicked.connect(lambda: self.set_navigation_view('groups'))
        nav_switch.addWidget(self.show_groups_button)
        self.show_thumbs_button = QToolButton()
        self.show_thumbs_button.setText('▦ Individual')
        self.show_thumbs_button.setToolTip('Browse individual pages and their thumbnails')
        self.show_thumbs_button.setCheckable(True)
        self.show_thumbs_button.clicked.connect(lambda: self.set_navigation_view('thumbnails'))
        nav_switch.addWidget(self.show_thumbs_button)
        nav_switch.addStretch(1)
        self.new_group_button = QToolButton()
        self.new_group_button.setText('+ Group')
        self.new_group_button.setToolTip('Create an empty group or a subgroup')
        self.new_group_button.clicked.connect(self.create_page_group)
        nav_switch.addWidget(self.new_group_button)
        sl.addWidget(self.nav_view_buttons)
        sl.addWidget(self.nav_views, 1)
        initial_view = str(self.settings.value('pageNavigatorView', 'groups'))
        if initial_view not in ('groups', 'thumbnails'):
            initial_view = 'groups'
        self._navigator_view = initial_view
        self.set_navigation_view(initial_view, persist=False)
        actions2 = WrapBar('Page actions')
        for text, callback, hint in [
                ('↑', lambda: self.move_page(-1), 'Move selected page earlier'),
                ('↓', lambda: self.move_page(1), 'Move selected page later'),
                ('Rename', self.rename_page, 'Rename current page'),
                ('Remove', self.remove_page, 'Remove selected pages · Delete/Backspace'),
                ('Undo', self.undo_remove_pages, f'Undo most recent edit · {PRIMARY}Z')]:
            action = actions2.addAction(text)
            action.setToolTip(hint)
            action.triggered.connect(callback)
            if text == 'Undo':
                self._page_undo_button = action
        sl.addWidget(actions2)
        self._update_page_undo_availability()
        self.nav_actions = actions2
        # Once the bottom-row actions can sit together, further width no longer
        # helps navigation.  Keep enough room for a small page-number margin.
        # Optional wider shelf for large readable thumbnails.  Existing
        # saved splitter widths and the 20-icon memory cap are unchanged.
        self.shelf.setMaximumWidth(540)
        hint = QLabel('Hover between pages for + · drag files into the shelf · drag rows to reorder')
        hint.setObjectName('hintLabel')
        hint.setWordWrap(True)
        sl.addWidget(hint)
        self.nav_hint = hint
        self.splitter.addWidget(shelf)

        canvas_panel = AmbientPanel()
        canvas_panel.setObjectName('canvas')
        self.canvas_panel = canvas_panel
        canvas_panel.setMinimumWidth(245)
        cl = QVBoxLayout(canvas_panel)
        cl.setContentsMargins(10, 13, 10, 11)
        cl.setSpacing(9)
        self.page_title = PageTitleEditor()
        self.page_title.renamed.connect(self.rename_page_to)
        self.preview_header = PanelDropHeader('preview', self._reorder_token, self.page_title)
        self.preview_header.moveRequested.connect(self.move_workspace_panel)
        preview_header_row = QHBoxLayout()
        preview_header_row.setContentsMargins(0, 0, 0, 0)
        preview_header_row.setSpacing(5)
        preview_header_row.addWidget(self.preview_header, 1)
        self.navigator_toggle = QToolButton()
        self.navigator_toggle.setText('▤')
        self.navigator_toggle.setFixedSize(30, 29)
        self.navigator_toggle.setToolTip('Hide or show the Pages & Images navigator')
        self.navigator_toggle.setAccessibleName('Toggle page navigator visibility')
        self.navigator_toggle.clicked.connect(self.toggle_navigator_visibility)
        preview_header_row.addWidget(self.navigator_toggle)
        cl.addLayout(preview_header_row)
        self.canvas = ImageCanvas()
        self._ocr_cancel_event = None
        self._ocr_running = False
        self._ocr_last_text = ''
        self._ocr_last_page_id = None
        self._ocr_results_by_page = {}  # Each page keeps its latest OCR result.
        self.ocrProgress.connect(self._on_ocr_progress)
        self.canvas.ocrRegionsChanged.connect(self._update_ocr_region_count)
        self.canvas.ocrCancelRequested.connect(self.leave_ocr_mode)
        remembered_pen_width = float(self.settings.value('annotationPenWidth', 3.0))
        remembered_pen_width = max(.5, min(30., remembered_pen_width))
        self.canvas.tool_styles['pen']['width'] = remembered_pen_width / 1000
        self.canvas.zoomChanged.connect(self._on_preview_zoom)
        self.canvas.verticalScrollBar().valueChanged.connect(
            self._reading_scroll_moved)
        self.canvas.horizontalScrollBar().valueChanged.connect(
            self._reading_scroll_moved)
        controls = WrapBar('Preview controls')
        controls.addIconAction('zoom-out', f'Zoom out · {PRIMARY}−', lambda: self.canvas.zoom(0.8))
        controls.addIconAction('zoom-in', f'Zoom in · {PRIMARY}+', lambda: self.canvas.zoom(1.25))
        for text, callback, hint in [
                ('100%', self.canvas_actual, 'View at one image pixel per screen pixel'),
]:
            action = controls.addAction(text)
            action.setToolTip(hint)
            action.triggered.connect(callback)
        # Standard checkable QAction lets Qt theme the button's persistent
        # :checked outline (and keeps it keyboard/screen-reader accessible).
        self.fit_action = controls.addAction('Fit')
        self.fit_action.setCheckable(True)
        self.fit_action.setChecked(True)  # new pages open in Fit mode
        self.fit_action.setToolTip('Auto-fit page to preview. Click again to lock the current zoom.')
        self.fit_action.triggered.connect(self.canvas_fit)
        self.preview_zoom_label = QLabel('Page · —')
        self.preview_zoom_label.setObjectName('hintLabel')
        self.preview_zoom_label.setMinimumWidth(86)
        self.preview_zoom_label.setToolTip('Live document zoom · smart on-demand preview below 100%, smooth scaling above 100%')
        controls.addWidget(self.preview_zoom_label)
        self._ocr_entry_action = controls.addAction('✂ OCR')
        self._ocr_entry_action.setToolTip('Extract text from PDF/image: draw several rectangles, scroll, recognise and copy')
        self._ocr_entry_action.triggered.connect(self.enter_ocr_mode)
        cl.addWidget(controls)
        self.canvas.filesDropped.connect(lambda paths: self.import_paths(paths, len(self.project.pages)))
        self.canvas.highlightCreated.connect(self.add_highlight)
        self.canvas.strokeCreated.connect(self.add_stroke)
        self.canvas.strokeMoved.connect(self.move_stroke)
        self.canvas.strokeEraseRequested.connect(self.erase_stroke)
        self.canvas.strokesEraseGestureRequested.connect(self.erase_strokes)
        self.canvas.shapeCreated.connect(self.add_shape)
        self.canvas.strokeResized.connect(self.resize_stroke)
        self.canvas.annotationSelected.connect(self._annotation_selection_changed)
        self.preview_shortcuts = []
        for keys, callback in [('Alt+PgUp', lambda: self.move_selection(-1)),
                               ('Alt+PgDown', lambda: self.move_selection(1)),
                               ('Ctrl++', lambda: self.canvas.zoom(1.25)),
                               ('Ctrl+=', lambda: self.canvas.zoom(1.25)),
                               ('Ctrl+-', lambda: self.canvas.zoom(0.8))]:
            shortcut = QShortcut(QKeySequence(keys), self.canvas)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(callback)
            self.preview_shortcuts.append(shortcut)
        cl.addWidget(self.canvas, 1)
        # OCR controls are separate from annotation buttons and transient.
        # A QGridLayout lets the strip shrink without wrapping the normal tools.
        self.ocr_bar = QFrame(canvas_panel)
        self.ocr_bar.setObjectName('ocrSelectionBar')
        self.ocr_bar.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.ocr_bar.setMinimumWidth(0)
        ocr_strip = QVBoxLayout(self.ocr_bar)
        ocr_strip.setContentsMargins(7, 7, 7, 7)
        ocr_strip.setSpacing(3)
        ocr_row1 = QHBoxLayout()
        ocr_row1.setSpacing(4)
        self.ocr_count = QLabel('0 regions')
        self.ocr_count.setToolTip('Draw up to 40 boxes on one page, in any order. Scroll to select more.')
        ocr_row1.addWidget(self.ocr_count, 1)
        self.ocr_whole_button = QPushButton('All')
        self.ocr_whole_button.setToolTip('Select the entire source page')
        self.ocr_whole_button.clicked.connect(self.canvas.select_whole_ocr_page)
        ocr_row1.addWidget(self.ocr_whole_button)
        self.ocr_undo_button = QPushButton('↶')
        self.ocr_undo_button.setToolTip('Remove last selection rectangle')
        self.ocr_undo_button.clicked.connect(self.canvas.undo_ocr_region)
        ocr_row1.addWidget(self.ocr_undo_button)
        self.ocr_clear_button = QPushButton('Clear')
        self.ocr_clear_button.clicked.connect(self.canvas.clear_ocr_regions)
        ocr_row1.addWidget(self.ocr_clear_button)
        ocr_strip.addLayout(ocr_row1)
        ocr_row2 = QHBoxLayout()
        ocr_row2.setSpacing(4)
        self.ocr_dpi = QComboBox()
        self.ocr_dpi.setToolTip('Source extraction resolution, independently of preview zoom')
        for value in OCR_DPI:
            self.ocr_dpi.addItem(f'{value} DPI', value)
        saved_dpi = int(self.settings.value('ocrDpi', 300))
        self.ocr_dpi.setCurrentIndex(max(0, self.ocr_dpi.findData(saved_dpi)))
        self.ocr_dpi.currentIndexChanged.connect(lambda: self.settings.setValue('ocrDpi', self.ocr_dpi.currentData()))
        ocr_row2.addWidget(self.ocr_dpi, 1)
        self.ocr_language = QComboBox()
        self.ocr_language.setToolTip('Installed local OCR languages')
        self.ocr_language.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.ocr_language.setMinimumContentsLength(6)
        self.ocr_language.addItem('English', 'eng')
        ocr_row2.addWidget(self.ocr_language, 1)
        self.ocr_recognise_button = QPushButton('Recognise')
        self.ocr_recognise_button.setToolTip('Recognise selections, copy result and open text review')
        self.ocr_recognise_button.clicked.connect(self.recognise_ocr_selection)
        ocr_row2.addWidget(self.ocr_recognise_button)
        self.ocr_cancel_button = QPushButton('✕')
        self.ocr_cancel_button.setToolTip('Cancel OCR mode or stop recognition')
        self.ocr_cancel_button.clicked.connect(lambda: self.leave_ocr_mode())
        ocr_row2.addWidget(self.ocr_cancel_button)
        ocr_strip.addLayout(ocr_row2)
        ocr_row3 = QHBoxLayout()
        ocr_row3.setSpacing(5)
        self.ocr_join_lines = QCheckBox('Join wrapped lines')
        self.ocr_join_lines.setChecked(str(self.settings.value('ocrJoinLines', 'true')).lower() == 'true')
        self.ocr_join_lines.toggled.connect(lambda checked: self.settings.setValue('ocrJoinLines', checked))
        ocr_row3.addWidget(self.ocr_join_lines)
        ocr_row3.addStretch(1)
        self.ocr_review_button = QPushButton('Review')
        self.ocr_review_button.setEnabled(False)
        self.ocr_review_button.clicked.connect(self.show_ocr_review)
        ocr_row3.addWidget(self.ocr_review_button)
        ocr_strip.addLayout(ocr_row3)
        # Recognise/Cancel live on their own row, so no controls vanish when
        # the centre splitter reaches its 245px minimum width.
        ocr_row2.removeWidget(self.ocr_recognise_button)
        ocr_row2.removeWidget(self.ocr_cancel_button)
        ocr_row4 = QHBoxLayout()
        ocr_row4.setSpacing(4)
        ocr_row4.addWidget(self.ocr_recognise_button, 1)
        ocr_row4.addWidget(self.ocr_cancel_button)
        ocr_strip.addLayout(ocr_row4)
        self.ocr_progress = QProgressBar()
        self.ocr_progress.setTextVisible(False)
        self.ocr_progress.setRange(0, 0)
        self.ocr_progress.setFixedHeight(5)
        self.ocr_progress.hide()
        ocr_strip.addWidget(self.ocr_progress)
        self.ocr_status = QLabel('Draw rectangles, scroll to select more · Esc to exit')
        self.ocr_status.setWordWrap(True)
        self.ocr_status.setObjectName('hintLabel')
        ocr_strip.addWidget(self.ocr_status)
        self.ocr_bar.hide()
        cl.addWidget(self.ocr_bar)
        footer = QWidget(canvas_panel)
        footer.setObjectName('annotationFooter')
        # Do not let the button row enforce a wide splitter minimum.
        footer.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        footer.setMinimumWidth(0)
        footer_row = QHBoxLayout(footer)
        footer_row.setContentsMargins(0, 2, 0, 2)
        footer_row.setSpacing(5)
        self.annotation_footer = footer
        self._annotation_footer_buttons = []
        self.annotation_mode_buttons = {}
        self._annotation_groups = {
            'drawing': ('pen', 'line', 'arrow', 'rectangle', 'ellipse'),
            'highlight': ('marker', 'highlight', 'highlight_line'),
            'erase': ('eraser',),
        }
        self._annotation_last_tool = {'drawing': 'pen',
                                      'highlight': 'highlight', 'erase': 'eraser'}
        self._annotation_group_buttons = {}

        def mini_tool(symbol, tip, handler=None):
            button = QToolButton()
            button.setObjectName('annotationToolbarButton')
            button.setText(symbol)
            # Give icons and one-word labels breathing room. Wrapping remains
            # owned by the existing footer, not the PDF or workspace splitter.
            button.setFixedHeight(39)
            button.setMinimumWidth(46)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            button.setStyleSheet('QToolButton#annotationToolbarButton {'
                                 'padding: 6px 10px; margin: 0px 1px;}')
            button.setToolTip(tip)
            if handler is not None:
                button.clicked.connect(handler)
            footer_row.addWidget(button)
            self._annotation_footer_buttons.append(button)
            return button

        select_button = mini_tool('Select', 'Select, move and resize annotations',
                                  lambda: self.set_annotation_mode('select'))
        select_button.setIcon(line_icon('mouse-pointer-2'))
        select_button.setProperty('annotationIconName', 'mouse-pointer-2')
        select_button.setIconSize(QSize(23, 23))
        select_button.setMinimumWidth(75)
        select_button.setCheckable(True)
        self.annotation_mode_buttons['select'] = select_button
        pan_button = mini_tool('✋', 'Pan the page',
                               lambda: self.set_annotation_mode('pan'))
        pan_button.setIcon(line_icon('hand'))
        pan_button.setProperty('annotationIconName', 'hand')
        pan_button.setCheckable(True)
        pan_button.setChecked(True)
        self.annotation_mode_buttons['pan'] = pan_button
        self._annotation_label_text = {}

        def tool_group(icon, group, options):
            button = mini_tool(icon, f'{group.title()} tools · click to reuse last tool; ▾ to choose',
                lambda _checked=False, key=group: self.set_annotation_mode(self._annotation_last_tool[key]))
            button.setCheckable(True)
            button.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
            menu = QMenu(button)
            for label, tool in options:
                menu.addAction(label, lambda _checked=False, t=tool: self.set_annotation_mode(t))
            button.setMenu(menu)
            self._annotation_group_buttons[group] = button
            return button

        drawing_button = tool_group('▱ Draw', 'drawing', (
            ('✎ Pen', 'pen'), ('╱ Straight line', 'line'),
            ('➜ Arrow', 'arrow'), ('▭ Rectangle', 'rectangle'),
            ('◯ Ellipse', 'ellipse')))
        drawing_button.setIcon(line_icon('shapes'))
        drawing_button.setProperty('annotationIconName', 'shapes')

        self.highlight_button = LabelledHighlightButton()
        self.highlight_button.set_colour(self.project.highlight_color)
        self.canvas.highlight_color = self.project.highlight_color
        for name in ('highlight', 'highlight_line', 'marker'):
            self.canvas.tool_styles[name]['color'] = self.project.highlight_color
        self.highlight_button.setProperty('annotationIconName', 'highlighter')
        self.highlight_button.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self.highlight_button.setToolTip('Highlight · click to use, ▾ to choose a mode, right-click for appearance')
        self.highlight_menu = QMenu(self.highlight_button)
        for label, tool in (('🖍 Freehand Multiply marker', 'marker'),
                            ('▭ Rectangle highlight', 'highlight'),
                            ('━ Straight-line highlight', 'highlight_line')):
            self.highlight_menu.addAction(label, lambda _checked=False, t=tool: self.set_annotation_mode(t))
        self.highlight_button.setMenu(self.highlight_menu)
        self.highlight_button.clicked.connect(
            lambda: self.set_annotation_mode(self._annotation_last_tool['highlight']))
        self.highlight_button.colourRequested.connect(self.show_annotation_appearance)
        footer_row.addWidget(self.highlight_button)
        self._annotation_footer_buttons.append(self.highlight_button)
        self._annotation_group_buttons['highlight'] = self.highlight_button

        eraser = mini_tool('Erase', 'Hold and drag to erase touched annotations; one Undo restores the stroke',
                           lambda: self.set_annotation_mode('eraser'))
        eraser.setIcon(line_icon('eraser'))
        eraser.setProperty('annotationIconName', 'eraser')
        eraser.setIconSize(QSize(16, 16))
        eraser.setCheckable(True)
        self.annotation_mode_buttons['eraser'] = eraser
        self._annotation_group_buttons['erase'] = eraser
        clear_button = mini_tool('Clear', 'Clear all annotations on this page (undoable)',
                                 self.clear_highlights)
        clear_button.setIcon(line_icon('trash-2'))
        clear_button.setProperty('annotationIconName', 'trash-2')
        clear_button.setIconSize(QSize(16, 16))
        self._annotation_clear_button = clear_button
        self.appearance_button = mini_tool('Colour', 'Edit appearance: stroke, fill, thickness and opacity',
                                          self.show_annotation_appearance)
        self.appearance_button.setIcon(line_icon('palette'))
        self.appearance_button.setProperty('annotationIconName', 'palette')
        self.appearance_button.setIconSize(QSize(17, 17))

        link_button = mini_tool('Link', f'Insert a link to this page in notes · {docs_shortcut("page_link")}',
                                self.link_current_page)
        link_button.setIcon(line_icon('link-2'))
        link_button.setProperty('annotationIconName', 'link-2')
        link_button.setIconSize(QSize(15, 15))
        link_button.setAccessibleName('Link current page into notes')
        self._annotation_link_button = link_button
        self._annotation_overflow = QToolButton(footer)
        self._annotation_overflow.setObjectName('annotationToolbarButton')
        self._annotation_overflow.setIcon(line_icon('more'))
        self._annotation_overflow.setProperty('annotationIconName', 'more')
        self._annotation_overflow.setToolTip('More annotation tools')
        self._annotation_overflow.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        overflow_menu = QMenu(self._annotation_overflow)
        overflow_menu.addAction('Erase', lambda: self.set_annotation_mode('eraser'))
        overflow_menu.addAction('Clear', self.clear_highlights)
        overflow_menu.addAction('Colour', self.show_annotation_appearance)
        overflow_menu.addAction('Link', self.link_current_page)
        self._annotation_overflow.setMenu(overflow_menu)
        footer_row.addWidget(self._annotation_overflow)
        self._annotation_footer_buttons.append(self._annotation_overflow)
        self._annotation_overflow.hide()
        self._annotation_label_text = {self._annotation_overflow: '',
            select_button: 'Select', pan_button: '',
            drawing_button: 'Draw', self.highlight_button: 'Highlight',
            eraser: 'Erase', clear_button: 'Clear',
            self.appearance_button: 'Colour', link_button: 'Link'}
        # Contextual pen width: does not touch existing selected marks or the
        # Quick Edit panel. One compact control, visible only in freehand Pen.
        self.pen_size_widget = QWidget(footer)
        pen_row = QHBoxLayout(self.pen_size_widget)
        pen_row.setContentsMargins(1, 0, 1, 0)
        pen_row.setSpacing(3)
        self.pen_size_label = QLabel(f'{remembered_pen_width:g}pt')
        self.pen_size_label.setToolTip('Thickness of newly drawn freehand pen strokes')
        self.pen_size_slider = QSlider(Qt.Orientation.Horizontal)
        self.pen_size_slider.setRange(1, 60)  # 0.5 pt through 30 pt
        self.pen_size_slider.setValue(round(remembered_pen_width * 2))
        self.pen_size_slider.setMinimumWidth(45)
        self.pen_size_slider.setMaximumWidth(92)
        self.pen_size_slider.setToolTip('New pen stroke thickness: 0.5–30 pt')
        self.pen_size_slider.valueChanged.connect(self._set_pen_size)
        pen_row.addWidget(self.pen_size_label)
        pen_row.addWidget(self.pen_size_slider, 1)
        footer_row.addWidget(self.pen_size_widget)
        self.pen_size_widget.hide()
        footer_row.addStretch(1)
        cl.addWidget(footer)
        self._update_annotation_toolbar_layout()

        # Compact annotation-only appearance controls. These never inspect or
        # modify the notes editor, PDF preview cache, or global shortcuts.
        self._syncing_appearance = False
        self._appearance_selection_index = -1
        self._appearance_selection_mark = None
        self.appearance_panel = QWidget()
        appearance_layout = QVBoxLayout(self.appearance_panel)
        appearance_layout.setContentsMargins(2, 2, 2, 2)
        appearance_layout.setSpacing(4)
        self.appearance_panel.setMinimumWidth(0)
        self.appearance_panel.setMaximumWidth(620)
        # Do not put these two stacked swatches into a FlowLayout/WrapBar.
        # FlowLayout does not propagate a reliable height-for-width sizeHint
        # through this nested popup, which collapsed the row in v0.5.4 and
        # allowed the thickness control to paint over the colour swatches.
        # Keep the old state objects internally for compatibility with the
        # drawing model and existing GUI tests; the visible interface uses
        # swatch context menus instead of two more permanent checkboxes.
        self.stroke_enabled_checkbox = QCheckBox('Stroke', self.appearance_panel)
        self.stroke_enabled_checkbox.setChecked(True)
        self.stroke_enabled_checkbox.toggled.connect(self._appearance_changed)
        self.stroke_enabled_checkbox.hide()
        self.shape_fill_checkbox = QCheckBox('Fill', self.appearance_panel)
        self.shape_fill_checkbox.toggled.connect(self._appearance_changed)
        self.shape_fill_checkbox.hide()
        self._palette_channel = 'stroke'

        paint_widget = QWidget()
        paint_layout = QHBoxLayout(paint_widget)
        paint_layout.setContentsMargins(1, 0, 3, 0)
        paint_layout.setSpacing(3)
        paint_stack = QVBoxLayout()
        paint_stack.setContentsMargins(0, 0, 0, 0)
        paint_stack.setSpacing(2)
        self.stroke_paint_row = QWidget()
        stroke_row = QHBoxLayout(self.stroke_paint_row)
        stroke_row.setContentsMargins(0, 0, 0, 0)
        stroke_row.setSpacing(4)
        self.stroke_colour_label = QLabel('Stroke')
        self.stroke_colour_label.setMinimumWidth(53)
        stroke_row.addWidget(self.stroke_colour_label)
        self.pen_colour = AnnotationColourSwatch()
        self.pen_colour.setToolTip('Stroke · click to select for palette; double-click to choose colour; right-click for None')
        self.pen_colour.clicked.connect(lambda: self._select_palette_channel('stroke'))
        self.pen_colour.colourEditRequested.connect(lambda: self._pick_appearance_color('stroke'))
        self.pen_colour.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.pen_colour.customContextMenuRequested.connect(
            lambda point: self._swatch_menu(self.pen_colour, point, 'stroke'))
        stroke_row.addWidget(self.pen_colour)
        paint_stack.addWidget(self.stroke_paint_row)

        self.fill_paint_row = QWidget()
        fill_row = QHBoxLayout(self.fill_paint_row)
        fill_row.setContentsMargins(0, 0, 0, 0)
        fill_row.setSpacing(4)
        fill_label = QLabel('Fill')
        fill_label.setMinimumWidth(53)
        fill_row.addWidget(fill_label)
        self.fill_colour = AnnotationColourSwatch()
        self.fill_colour.setToolTip('Fill · click to select for palette; double-click to choose colour; right-click for No Fill')
        self.fill_colour.clicked.connect(lambda: self._select_palette_channel('fill'))
        self.fill_colour.colourEditRequested.connect(lambda: self._pick_appearance_color('fill'))
        self.fill_colour.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.fill_colour.customContextMenuRequested.connect(
            lambda point: self._swatch_menu(self.fill_colour, point, 'fill'))
        fill_row.addWidget(self.fill_colour)
        paint_stack.addWidget(self.fill_paint_row)
        paint_layout.addLayout(paint_stack)
        self.swap_colours_button = QToolButton()
        self.swap_colours_button.setText('⇅')
        self.swap_colours_button.setToolTip('Swap stroke and fill colours (opacity unchanged)')
        self.swap_colours_button.setFixedSize(28, 28)
        self.swap_colours_button.clicked.connect(self._swap_annotation_colours)
        paint_layout.addWidget(self.swap_colours_button)
        appearance_layout.addWidget(paint_widget)

        # A continuous slider and an exact numeric field control the SAME width.
        # The slider commits only when the user finishes, so undo remains one step.
        self.quick_thickness_row = QWidget(self.appearance_panel)
        # Put the numeric input beside the caption and the slider on its own
        # full-width row. This prevents overlap even when the preview is narrow.
        thickness_row = QVBoxLayout(self.quick_thickness_row)
        thickness_row.setContentsMargins(1, 3, 1, 3)
        thickness_row.setSpacing(5)
        thickness_caption = QHBoxLayout()
        thickness_caption.setContentsMargins(0, 0, 0, 0)
        thickness_caption.addWidget(QLabel('Thickness'))
        thickness_caption.addStretch(1)
        self.quick_thickness = AnnotationOpacitySlider(Qt.Orientation.Horizontal)
        self.quick_thickness.setRange(5, 1000)
        self.quick_thickness.setSingleStep(5)
        self.quick_thickness.setPageStep(25)
        self.quick_thickness.setToolTip('Drag to adjust 0.5–100 pt; release for one Undo step')
        self.quick_thickness.setMinimumWidth(100)
        self.stroke_width_control = QDoubleSpinBox(self.appearance_panel)
        self.stroke_width_control.setObjectName('quickThicknessNumber')
        self.stroke_width_control.setRange(0.5, 100)
        self.stroke_width_control.setDecimals(1)
        self.stroke_width_control.setSingleStep(0.5)
        self.stroke_width_control.setValue(3)
        self.stroke_width_control.setSuffix(' pt')
        self.stroke_width_control.setMinimumWidth(82)
        self.stroke_width_control.setToolTip('Enter an exact line or highlight thickness')
        self.stroke_width_control.valueChanged.connect(self._sync_thickness_slider_from_spinbox)
        self.stroke_width_control.valueChanged.connect(self._preview_annotation_appearance)
        self.stroke_width_control.editingFinished.connect(self._appearance_changed)
        self.quick_thickness.valueChanged.connect(self._quick_thickness_preview)
        self.quick_thickness.editFinished.connect(self._appearance_changed)
        thickness_caption.addWidget(self.stroke_width_control)
        thickness_row.addLayout(thickness_caption)
        thickness_row.addWidget(self.quick_thickness)
        appearance_layout.addWidget(self.quick_thickness_row)

        # Opacity controls are no longer a nested popup. Both appear directly
        # in the reusable floating appearance editor, saving clicks and state.
        self._opacity_labels = {}
        self._opacity_rows = {}
        for target, initial in (('stroke', 100), ('fill', 30)):
            opacity_row = QWidget(self.appearance_panel)
            opacity_layout = QVBoxLayout(opacity_row)
            opacity_layout.setContentsMargins(1, 2, 1, 2)
            opacity_layout.setSpacing(3)
            captions = QHBoxLayout()
            title = QLabel('Stroke opacity' if target == 'stroke' else 'Fill opacity')
            value = QLabel(f'{initial}%')
            value.setMinimumWidth(39)
            value.setAlignment(Qt.AlignmentFlag.AlignRight)
            captions.addWidget(title)
            captions.addStretch(1)
            captions.addWidget(value)
            opacity_layout.addLayout(captions)
            slider = AnnotationOpacitySlider(Qt.Orientation.Horizontal)
            slider.setRange(0, 100)
            slider.setSingleStep(1)
            slider.setPageStep(5)
            slider.setValue(initial)
            slider.valueChanged.connect(lambda number, out=value: out.setText(f'{number}%'))
            slider.valueChanged.connect(self._preview_annotation_appearance)
            slider.editFinished.connect(self._appearance_changed)
            opacity_layout.addWidget(slider)
            appearance_layout.addWidget(opacity_row)
            self._opacity_rows[target] = opacity_row
            self._opacity_labels[target] = title
            if target == 'stroke':
                self.stroke_opacity_control = slider
            else:
                self.fill_opacity_control = slider

        # A fixed, bounded grid has a real minimum height and prevents colour
        # swatches from vanishing beneath the bottom of the floating window.
        # In particular, it must not use WrapBar's custom FlowLayout here.
        quick = QWidget(self.appearance_panel)
        quick.setObjectName('quickAnnotationPalette')
        quick_layout = QVBoxLayout(quick)
        quick_layout.setContentsMargins(1, 4, 1, 2)
        quick_layout.setSpacing(5)
        quick_layout.addWidget(QLabel('Colours:'))
        quick_grid = QGridLayout()
        quick_grid.setContentsMargins(0, 0, 0, 0)
        quick_grid.setHorizontalSpacing(5)
        quick_grid.setVerticalSpacing(5)
        self._palette_swatches = ('#252525', '#ffffff', '#f17889', '#efa35b',
                                   '#f3d66b', '#8ccf9c', '#29b6a6', '#7bade9',
                                   '#a991e8', '#eca8d7')
        for i, colour in enumerate(self._palette_swatches):
            swatch = QToolButton(quick)
            swatch.setFixedSize(24, 24)
            swatch.setToolTip(f'{colour} · applies to the active Stroke/Fill swatch; right-click for choice')
            swatch.setStyleSheet(f'QToolButton {{ background: {colour}; border: 1px solid #818696; border-radius: 5px; }}')
            swatch.clicked.connect(lambda _checked=False, c=colour: self._apply_palette_colour(
                c, self._effective_palette_target()))
            swatch.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            swatch.customContextMenuRequested.connect(
                lambda point, b=swatch, c=colour: self._palette_menu(b, point, c))
            quick_grid.addWidget(swatch, i // 5, i % 5)
        self._recent_colours = []
        self._recent_swatches = []
        for i in range(3):
            recent = QToolButton(quick)
            recent.setFixedSize(24, 24)
            recent.setVisible(False)
            recent.setToolTip('Recently used custom colour')
            recent.clicked.connect(lambda _checked=False, b=recent:
                self._apply_palette_colour(b.property('recentColour'), self._effective_palette_target()))
            recent.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            recent.customContextMenuRequested.connect(
                lambda point, b=recent: self._palette_menu(b, point, b.property('recentColour')))
            quick_grid.addWidget(recent, 2, i)
            self._recent_swatches.append(recent)
        custom = QToolButton(quick)
        custom.setText('+ Colour')
        custom.setMinimumHeight(27)
        custom.setToolTip('Choose a custom colour (opacity is set separately)')
        custom.clicked.connect(lambda: self._pick_appearance_color(self._effective_palette_target()))
        quick_grid.addWidget(custom, 2, 3, 1, 2)
        quick_layout.addLayout(quick_grid)
        appearance_layout.addWidget(quick)
        self.arrow_size_row = QWidget()
        arrow_size_layout = QVBoxLayout(self.arrow_size_row)
        arrow_size_layout.setContentsMargins(1, 4, 1, 1)
        arrow_size_layout.setSpacing(3)
        arrow_size_layout.addWidget(QLabel('Arrowhead dimensions'))
        self.arrow_head_sliders = {}
        for key, caption, initial in (('head_width', 'Head width', 18),
                                      ('head_length', 'Head length', 25)):
            row = QHBoxLayout()
            row.addWidget(QLabel(caption))
            slider = AnnotationOpacitySlider(Qt.Orientation.Horizontal)
            slider.setRange(2, 200)
            slider.setValue(initial)
            slider.setMinimumWidth(110)
            slider.valueChanged.connect(self._preview_arrow_head)
            slider.editFinished.connect(self._commit_arrow_head)
            row.addWidget(slider, 1)
            arrow_size_layout.addLayout(row)
            self.arrow_head_sliders[key] = slider
        appearance_layout.addWidget(self.arrow_size_row)
        self.arrow_size_row.hide()
        # Split the *existing* controls into two columns, never clone signal
        # handlers or annotation state. Switch QBoxLayout direction on resize.
        for widget in (paint_widget, quick, self.quick_thickness_row,
                       self._opacity_rows['stroke'], self._opacity_rows['fill'],
                       self.arrow_size_row):
            appearance_layout.removeWidget(widget)
        self._quick_columns = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self._quick_columns.setSpacing(12)
        left_controls = QVBoxLayout()
        left_controls.setSpacing(5)
        left_controls.addWidget(paint_widget)
        left_controls.addWidget(quick)
        left_controls.addStretch(1)
        right_controls = QVBoxLayout()
        right_controls.setSpacing(5)
        right_controls.addWidget(self.quick_thickness_row)
        right_controls.addWidget(self._opacity_rows['stroke'])
        right_controls.addWidget(self._opacity_rows['fill'])
        right_controls.addWidget(self.arrow_size_row)
        right_controls.addStretch(1)
        self._quick_columns.addLayout(left_controls, 1)
        self._quick_columns.addLayout(right_controls, 1)
        appearance_layout.addLayout(self._quick_columns)
        self.quick_palette = quick
        # The one appearance_panel is embedded in Quick Edit below, whether
        # the user edits a selected object or chooses defaults via Colour.
        self._annotation_selection_changed(-1, None)

        page_nav_row = QHBoxLayout()
        page_nav_row.setContentsMargins(0, 0, 0, 0)
        page_nav_row.setSpacing(5)
        page_nav_row.addStretch(1)
        self.preview_previous = QToolButton()
        self.preview_previous.setText('‹')
        self.preview_previous.setFixedSize(24, 23)
        self.preview_previous.setToolTip(
            f'Previous page · {PRIMARY}{ALT}↑' if IS_MAC
            else 'Previous page · Ctrl+Alt+Up')
        self.preview_previous.clicked.connect(lambda: self.move_selection(-1))
        page_nav_row.addWidget(self.preview_previous)
        self.page_position = QLabel('No page selected')
        self.page_position.setObjectName('hintLabel')
        self.page_position.setAlignment(Qt.AlignmentFlag.AlignCenter)
        page_nav_row.addWidget(self.page_position)
        self.preview_next = QToolButton()
        self.preview_next.setText('›')
        self.preview_next.setFixedSize(24, 23)
        self.preview_next.setToolTip(
            f'Next page · {PRIMARY}{ALT}↓' if IS_MAC
            else 'Next page · Ctrl+Alt+Down')
        self.preview_next.clicked.connect(lambda: self.move_selection(1))
        page_nav_row.addWidget(self.preview_next)
        page_nav_row.addStretch(1)
        cl.addLayout(page_nav_row)
        self._create_annotation_quick_edit()
        self.splitter.addWidget(canvas_panel)

        defaults = {
            'font': self.settings.value('defaultFont', 'Nunito'),
            'font_size': int(self.settings.value('defaultFontSize', 13)),
            'bold': str(self.settings.value('defaultBold', 'false')).lower() == 'true',
            'italic': str(self.settings.value('defaultItalic', 'false')).lower() == 'true',
            'alignment': self.settings.value('defaultAlignment', 'Left'),
            'show_web_link': str(self.settings.value('showWebLink', 'false')).lower() == 'true',
            'show_jump_edit': str(self.settings.value('showJumpEditPosition', 'false')).lower() == 'true',
        }
        # Each tab has its own collection of note documents. One shared
        # NotesEditor swaps native QTextDocuments, preserving per-page rich
        # formatting, links and Qt undo stacks without 100 heavyweight editors.
        self.project.note_pages, self.project.active_note_id = validated_note_pages(
            self.project.note_pages, self.project.active_note_id,
            self.project.notes_html, self.project.notes_scroll,
            self.project.notes_page_setup)
        self._note_documents = {}
        self._note_document_ids = {}
        self._changing_note_page = False
        self._notes_defaults = defaults
        self.notes = NotesEditor(defaults=defaults)
        self.notes.setObjectName('notePane')
        self.notes.setMinimumWidth(280)
        first_note = self._current_note_page()
        self.notes.set_html(first_note['html'])
        self.notes.set_page_setup(
            NotesPageSetup.from_dict(first_note['page_setup'])
            if first_note['page_setup'] is not None else None, from_load=True)
        first_doc = self.notes.editor.document()
        self._note_documents[first_note['id']] = first_doc
        self._note_document_ids[id(first_doc)] = first_note['id']
        # The navigator is a compact row INSIDE the existing rich-text pane;
        # no duplicate notes editor, toolbar or Markdown conversion.
        self._setup_notes_page_navigation()

        self.notes.pageSetupRequested.connect(self.show_notes_page_setup)
        # Restore notes reading position after Qt has laid out the editor.
        # This is independent from which PDF page is selected. A view-state
        # save never resets the notes QTextDocument (and therefore Undo/Redo).
        self._restoring_notes_scroll = True
        self._scroll_idle_timer = QTimer(self)
        self._scroll_idle_timer.setSingleShot(True)
        self._scroll_idle_timer.setInterval(650)
        self._scroll_idle_timer.timeout.connect(self._scroll_position_settled)
        self.notes.editor.verticalScrollBar().valueChanged.connect(self._notes_scrolled)
        # QTextEdit's scrollbar range is not final while a project pane is
        # hidden or before it has joined the visible tab widget. Defer its
        # first restore until activate(), after the Qt layout pass.
        self._notes_scroll_restored = False
        self._celebrate_on_next_manual_save = False
        self.notes.changed.connect(self._notes_modified)
        self.notes.pageLinkClicked.connect(self.select_page_id)
        self.notes.externalLinkClicked.connect(self.open_external_url)
        self.notes.pageLinkRequested.connect(self.link_current_page)
        self.notes.fontSetAsDefault.connect(self.use_default_font)
        self.notes.editor.link_tooltip_resolver = self.describe_link
        notes_backdrop = AmbientPanel()
        notes_backdrop.setObjectName('notesBackdrop')
        self.notes_backdrop = notes_backdrop
        notes_layout = QVBoxLayout(notes_backdrop)
        notes_layout.setContentsMargins(0, 0, 0, 0)
        # Reuse the editor's EXISTING heading rather than adding another row.
        # The handle belongs to the live NotesEditor; dragging reorders the
        # surrounding notes_backdrop without recreating the text document.
        notes_heading = self.notes.layout().itemAt(0).widget()
        self.notes.layout().removeWidget(notes_heading)
        self.notes_header = PanelDropHeader('notes', self._reorder_token, notes_heading)
        self.notes_header.moveRequested.connect(self.move_workspace_panel)
        self.notes.layout().insertWidget(0, self.notes_header)
        notes_layout.addWidget(self.notes)
        self._notes_ambient_timer = QTimer(self)
        self._notes_ambient_timer.setSingleShot(True)
        self._notes_ambient_timer.setInterval(95)
        self._notes_ambient_timer.timeout.connect(
            lambda: notes_backdrop.scroll_pulse(
                self.notes.editor.verticalScrollBar().value()))
        self.notes.editor.verticalScrollBar().valueChanged.connect(
            lambda _value: self._notes_ambient_timer.start())
        self.splitter.addWidget(notes_backdrop)
        self._panel_widgets = {'pages': self.shelf, 'preview': self.canvas_panel,
                               'notes': self.notes_backdrop}
        # Older projects have no panel_order and open in classic mode. New
        # projects restore all six arrangements without changing format v4.
        self.apply_panel_order(project.panel_order, initializing=True)
        # splitter_sizes is intentionally stored in *classic* keyed order to
        # remain usable by 0.3.4c and older apps, which ignore panel_order.
        saved_widths = dict(zip(PANEL_KEYS, project.splitter_sizes))
        self.splitter.setSizes([saved_widths[key] for key in self._panel_order])
        reduced = str(self.settings.value('reducedMotion', 'false')).lower() == 'true'
        for panel in (self.shelf, self.canvas_panel, self.notes_backdrop):
            panel.set_reduce_motion(reduced)
        self._splitter_scroll_anchor = None
        self._splitter_scroll_token = 0
        self._splitter_handles = [self.splitter.handle(i) for i in (1, 2)]
        for handle in self._splitter_handles:
            handle.installEventFilter(self)
        self.splitter.splitterMoved.connect(self._navigator_splitter_moved)
        self.load_pages()
        # Splitter widths become valid only after the first layout pass.
        QTimer.singleShot(0, self._sync_navigator_width)
        if not self._navigator_requested_visible:
            # Hide explicitly even if this tab is not yet shown by its parent.
            self.set_navigator_visible(False, persist=False)
        if project.selected_page:
            self.select_page_id(project.selected_page)
        elif project.pages:
            self.pages_list.setCurrentRow(0)

    def apply_panel_order(self, order, initializing=False):
        """Move the SAME live widgets inside QSplitter; never duplicate views.

        Widths follow their panel identities, so moving Notes to the left
        doesn't unexpectedly give it the page navigator's narrow width.
        """
        if not valid_panel_order(list(order)):
            return
        order = list(order)
        if order == self._panel_order and not initializing:
            return
        before = dict(zip(self._panel_order, self.splitter.sizes()))
        self.splitter.blockSignals(True)
        try:
            for index, key in enumerate(order):
                self.splitter.insertWidget(index, self._panel_widgets[key])
            for index, key in enumerate(order):
                self.splitter.setStretchFactor(index, {'pages': 0, 'preview': 2, 'notes': 1}[key])
            if not initializing and all(size > 0 for size in before.values()):
                self.splitter.setSizes([before[key] for key in order])
        finally:
            self.splitter.blockSignals(False)
        self._panel_order = order
        self.project.panel_order = list(order)
        if not initializing:
            self._sync_navigator_width()
            self.schedule_save()
            self.statusMessage.emit('Workspace: ' + ' · '.join(key.title() for key in order))

    def move_workspace_panel(self, source: str, target: str, after: bool):
        """Insert the dragged panel before/after the chosen target header."""
        if source == target or source not in PANEL_KEYS or target not in PANEL_KEYS:
            return
        order = list(self._panel_order)
        order.remove(source)
        index = order.index(target) + (1 if after else 0)
        order.insert(index, source)
        self.apply_panel_order(order)

    def reset_workspace_layout(self):
        self.apply_panel_order(list(PANEL_KEYS))
        sizes = self.splitter.sizes()
        total = max(900, sum(sizes))
        self.splitter.setSizes([round(total * .17), round(total * .48), round(total * .35)])
        self._sync_navigator_width()
        self.schedule_save()

    def eventFilter(self, watched, event):
        if watched is getattr(self, 'annotation_quick_edit', None):
            if event.type() in (QEvent.Type.Move, QEvent.Type.Resize,
                                QEvent.Type.Show, QEvent.Type.Hide):
                # A hidden panel may still resize during layout updates.
                # Do not show a ghost backdrop until Quick Edit is shown.
                self._sync_annotation_quick_edit_backdrop(
                    visible=(event.type() == QEvent.Type.Show or
                             (event.type() != QEvent.Type.Hide and watched.isVisible())))
        if watched is getattr(self, 'quick_resize_handle', None):
            panel = getattr(self, 'annotation_quick_edit', None)
            if panel is not None:
                kind = event.type()
                if kind == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                    self._quick_edit_resize_start = (event.globalPosition().toPoint(),
                                                     panel.width())
                    event.accept()
                    return True
                if kind == QEvent.Type.MouseMove and self._quick_edit_resize_start is not None:
                    origin, start_width = self._quick_edit_resize_start
                    self._quick_edit_user_width = max(290, min(620,
                        start_width + event.globalPosition().toPoint().x() - origin.x()))
                    self._position_annotation_quick_edit()
                    event.accept()
                    return True
                if kind == QEvent.Type.MouseButtonRelease and self._quick_edit_resize_start is not None:
                    self._quick_edit_resize_start = None
                    event.accept()
                    return True
        if watched in (getattr(self, 'quick_drag_handle', None),
                       getattr(self, 'quick_title', None)):
            panel = getattr(self, 'annotation_quick_edit', None)
            if panel is not None:
                kind = event.type()
                if kind == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                    self._quick_edit_drag_start = (event.globalPosition().toPoint(), panel.pos())
                    watched.setCursor(Qt.CursorShape.ClosedHandCursor)
                    event.accept()
                    return True
                if kind == QEvent.Type.MouseMove and self._quick_edit_drag_start is not None:
                    point, start = self._quick_edit_drag_start
                    delta = event.globalPosition().toPoint() - point
                    viewport = self.canvas.viewport()
                    x = max(4, min(viewport.width()-panel.width()-4, start.x()+delta.x()))
                    y = max(4, min(viewport.height()-panel.height()-4, start.y()+delta.y()))
                    panel.move(x, y)
                    self._quick_edit_custom_position = True
                    event.accept()
                    return True
                if kind == QEvent.Type.MouseButtonRelease and self._quick_edit_drag_start is not None:
                    self._quick_edit_drag_start = None
                    watched.setCursor(Qt.CursorShape.OpenHandCursor)
                    event.accept()
                    return True
        if (hasattr(self, 'canvas') and watched is self.canvas.viewport()
                and event.type() == QEvent.Type.Resize):
            QTimer.singleShot(0, self._position_annotation_quick_edit)
            QTimer.singleShot(0, self._update_annotation_toolbar_layout)

        # Capture a real text-line anchor BEFORE QSplitter starts changing the
        # editor viewport. Reflow then keeps that line at its former screen Y.
        if watched in getattr(self, '_splitter_handles', ()):
            if event.type() == QEvent.Type.MouseButtonPress:
                editor = self.notes.editor
                cursor = editor.textCursor()
                rect = editor.cursorRect(cursor)
                if not (0 <= rect.center().y() < editor.viewport().height()):
                    cursor = editor.cursorForPosition(QPoint(8, min(24, editor.viewport().height()-1)))
                    rect = editor.cursorRect(cursor)
                self._splitter_scroll_anchor = (cursor, rect.top())
            elif event.type() == QEvent.Type.MouseButtonRelease:
                self._splitter_scroll_token += 1
                token = self._splitter_scroll_token
                QTimer.singleShot(0, lambda: self._align_after_splitter(token, clear=True))
        return super().eventFilter(watched, event)

    def _align_after_splitter(self, token, clear=False):
        if token != self._splitter_scroll_token or not self._splitter_scroll_anchor:
            return
        cursor, original_y = self._splitter_scroll_anchor
        editor = self.notes.editor
        delta = editor.cursorRect(cursor).top() - original_y
        if delta:
            bar = editor.verticalScrollBar()
            bar.setValue(bar.value() + delta)
        if clear:
            self._splitter_scroll_anchor = None

    def _navigator_splitter_moved(self, *_):
        # Preserve the active line while updating navigator geometry.
        self._sync_navigator_width()
        if self._splitter_scroll_anchor:
            self._splitter_scroll_token += 1
            token = self._splitter_scroll_token
            QTimer.singleShot(0, lambda: self._align_after_splitter(token))
        self.schedule_save()

    def _sync_navigator_width(self):
        """Pick the matching layout from the *actual* sidebar width.

        Switching modes changes a few widgets and thumbnail row dimensions;
        it never loads additional page pixmaps or alters the 20-icon cache.
        """
        if not self._navigator_visible:
            return
        width = self.shelf.width()
        if width <= 0:
            return
        mode = 'mini' if width < 100 else 'compact' if width < 248 else 'normal'
        # The groups widget follows its own finer-grained density steps.
        # Neither conversion reconstructs page/group metadata or thumbnails.
        self.group_tree.set_navigator_density(width)
        mode_changed = mode != self._nav_mode
        self._nav_mode = mode
        normal = mode == 'normal'
        mini = mode == 'mini'
        self.shelf_layout.setContentsMargins(*( (4, 7, 4, 7) if mini else
                                               (6, 9, 6, 8) if not normal else
                                               (8, 10, 7, 8)))
        self.shelf_heading.setVisible(normal)
        # The mini rail has only enough room for its drag grip; page arrows
        # remain available beside the preview's page counter.
        self.navigator_previous.setVisible(not mini)
        self.navigator_next.setVisible(not mini)
        self.counter.setVisible(normal)
        self.reading_summary.setVisible(normal)
        self.reading_progress.setVisible(not mini)
        self.nav_hint.setVisible(normal)
        self.nav_actions.setVisible(normal)
        # Compact/mini modes must not force the old 74px navigator wider.
        # All actions remain available via the overflow/context menu.
        self.show_groups_button.setText('G' if mini else 'Groups' if not normal else '▸ Groups')
        self.show_thumbs_button.setText('▦' if mini else 'Individual' if not normal else '▦ Individual')
        self.new_group_button.setVisible(normal)
        self.blank_button.setVisible(False)
        # Mini rail has only room for the width toggle and the overflow.
        # Import/Smart Import/Blank remain in the overflow menu.
        self.import_button.setVisible(not mini)
        self.import_button.setText('+Add' if normal else '+')
        self.import_button.setMinimumWidth(0)
        self.nav_overflow.setVisible(not normal)
        self.nav_cycle.setToolTip(
            'Cycle page navigator width: Normal → Compact → Mini → Normal.\n'
            'Dragging the column divider also changes the layout automatically.')
        self.nav_cycle.setText('▦')
        self.pages_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # The navigator grows the icon rectangle with its actual column width.
        # Only visible rows can receive larger thumbnails on demand. The 20
        # resident-icon cap stays unchanged and off-screen rows are released.
        if mini:
            icon_width, icon_height = 40, 49
        elif not normal:
            icon_width = max(45, min(105, width - 28))
            icon_height = round(icon_width * 1.28)
        else:
            icon_width = min(420, max(105, round((width - 32) * 0.87)))
            icon_height = round(icon_width * 1.28)
        new_height = icon_height + (28 if mini else 37)
        old_size = self.pages_list.iconSize()
        if (not mode_changed and old_size == QSize(icon_width, icon_height)
                and getattr(self.pages_list, '_responsive_row_height', 0) == new_height):
            return
        self.pages_list.setIconSize(QSize(icon_width, icon_height))
        self.pages_list._responsive_row_height = new_height
        # Debounce width changes; visible rows get an appropriate raster at
        # the settled width. Old 110px thumbs remain the default fallback.
        self._thumb_rescale_timer.start()
        # UniformItemSizes avoids O(page-count) model modifications on drag.
        if self.pages_list.count():
            self.pages_list.item(0).setSizeHint(QSize(55, new_height))
            self.pages_list.doItemsLayout()
        self.schedule_thumbnails()

    def set_navigator_visible(self, visible, persist=True):
        """Hide or restore the existing live page shelf without recreating it."""
        visible = bool(visible)
        if self._navigator_visible == visible and self.shelf.isHidden() == (not visible):
            return
        if not visible:
            sizes = self.splitter.sizes()
            if len(sizes) == 3:
                width = sizes[self._panel_order.index('pages')]
                if width >= 74:  # preserve saved width before first layout
                    self._navigator_restore_width = width
        self._navigator_visible = visible
        self.shelf.setVisible(visible)
        if visible:
            sizes = self.splitter.sizes()
            if len(sizes) == 3:
                idx = self._panel_order.index('pages')
                other = [i for i in range(3) if i != idx]
                total = sum(sizes)
                target = min(540, max(74, getattr(self, '_navigator_restore_width', 225)))
                available = max(2, total-target)
                weight = max(1, sum(sizes[i] for i in other))
                sizes[idx] = target
                sizes[other[0]] = round(available * sizes[other[0]] / weight)
                sizes[other[1]] = available-sizes[other[0]]
                self.splitter.setSizes(sizes)
            QTimer.singleShot(0, self._sync_navigator_width)
        self.navigator_toggle.setText('▤' if visible else '▥')
        self.navigator_toggle.setToolTip('Hide page navigator' if visible else 'Show page navigator')
        if persist:
            self.settings.setValue('showPageNavigator', visible)
        owner = self.window()
        if hasattr(owner, '_sync_navigator_menu_action'):
            owner._sync_navigator_menu_action()

    def toggle_navigator_visibility(self):
        owner = self.window()
        if hasattr(owner, '_set_all_navigator_visibility'):
            owner._set_all_navigator_visibility(not self._navigator_visible)
        else:
            self.set_navigator_visible(not self._navigator_visible)

    def cycle_navigator_mode(self):
        """Cycle preset widths while retaining centre/notes proportions."""
        sizes = self.splitter.sizes()
        if not sizes or sum(sizes) < 200:
            return
        modes = ('normal', 'compact', 'mini')
        current = self._nav_mode or 'normal'
        next_mode = modes[(modes.index(current) + 1) % len(modes)]
        target = {'normal': 305, 'compact': 185, 'mini': 92}[next_mode]
        pages_index = self._panel_order.index('pages')
        other_indices = [i for i in range(3) if i != pages_index]
        free = max(0, sum(sizes) - target)
        total = max(1, sum(sizes[i] for i in other_indices))
        new_sizes = list(sizes)
        new_sizes[pages_index] = target
        new_sizes[other_indices[0]] = round(free * sizes[other_indices[0]] / total)
        new_sizes[other_indices[1]] = free - new_sizes[other_indices[0]]
        self.splitter.setSizes(new_sizes)
        self._sync_navigator_width()
        self.schedule_save()

    def _thumbnail_decoration(self, pixmap: QPixmap) -> QPixmap:
        """Retain the original page aspect and pixels for delegate painting.

        In particular, do NOT pre-scale into a fixed portrait-shaped icon
        canvas: that caused landscape page previews to appear stuck at the top
        or placed oddly in their cards. The delegate now centres the original
        artwork itself, independently from the footer and card shape.
        Exactly one pixmap per visible row, with the existing 20-row cap.
        """
        return pixmap

    def _thumbnail_width_for_view(self) -> int:
        """Small quantised width buckets avoid one new file per drag pixel."""
        logical = self.pages_list.iconSize().width()
        if logical <= 110:
            return 110
        # Width changes smaller than 48px won't keep causing rerenders.
        # On a HiDPI display use more source pixels where budget allows.
        screen = self.pages_list.screen()
        dpr = min(1.5, max(1.0, screen.devicePixelRatio() if screen else 1.0))
        requested = min(LARGE_THUMB_MAX_WIDTH, round(logical * dpr))
        return min(LARGE_THUMB_MAX_WIDTH, max(160, math.ceil(requested / 48) * 48))

    def _thumb_cache_path(self, page: dict) -> Path:
        pid = page['id']
        if self._thumbnail_bucket > 110:
            return self.project.asset_path(f'cache/thumbs-responsive/{pid}_{self._thumbnail_bucket}.jpg')
        return self.project.asset_path(f'cache/thumbs/{pid}.jpg')

    def _rescale_visible_thumb_icons(self):
        """Refresh visible thumbs from their size-matched disposable JPEGs."""
        if not self._active or self.window().isMinimized():
            return
        bucket = self._thumbnail_width_for_view()
        if bucket != self._thumbnail_bucket:
            self._thumbnail_bucket = bucket
            self._generation += 1  # obsolete queued jobs return without work
            self._thumb_pending.clear()
            for row in self._loaded_thumb_rows:
                if row < self.pages_list.count():
                    self.pages_list.item(row).setIcon(QIcon())
            self._loaded_thumb_rows.clear()
            self.schedule_thumbnails()
            return
        for row in list(self._loaded_thumb_rows)[:THUMB_LIMIT]:
            if not 0 <= row < self.pages_list.count() or row >= len(self.project.pages):
                continue
            cached = self._thumb_cache_path(self.project.pages[row])
            if not cached.is_file():
                continue
            reader = QImageReader(str(cached))
            decoded = reader.read()
            if not decoded.isNull():
                self.pages_list.item(row).setData(Qt.ItemDataRole.DecorationRole,
                                                  self._thumbnail_decoration(QPixmap.fromImage(decoded)))

    def current_page(self) -> dict | None:
        item = self.pages_list.currentItem()
        return self.project.page_by_id(item.data(Qt.ItemDataRole.UserRole)) if item else None

    def load_pages(self, select_id=None):
        if select_id is None:
            select_id = self.project.selected_page
        self._loading = True
        self._generation += 1
        self._thumb_pending.clear()
        self._thumb_failed.clear()
        self._loaded_thumb_rows.clear()
        if hasattr(self, '_group_thumb_pending'):
            self._group_thumb_pending.clear()
            self._wanted_group_thumb_ids = frozenset()
        self.pages_list.clear()
        for page in self.project.pages:
            item = QListWidgetItem(page['title'])
            item.setData(Qt.ItemDataRole.UserRole, page['id'])
            item.setSizeHint(QSize(155, 82 if self._nav_mode == 'mini' else 112 if self._nav_mode == 'compact' else self.pages_list.ROW_HEIGHT))
            # Titles remain in DisplayRole for old projects, renaming and
            # accessibility; the delegate hides them visually until hover.
            item.setToolTip(page['title'])
            item.setData(Qt.ItemDataRole.AccessibleTextRole, page['title'])
            self.pages_list.addItem(item)
        count = len(self.project.pages)
        self.counter.setText(f'{count:,} page' + ('' if count == 1 else 's'))
        self._loading = False
        if select_id:
            row = next((i for i,p in enumerate(self.project.pages) if p['id'] == select_id), -1)
            if row >= 0:
                self.pages_list.setCurrentRow(row)
        # Read only IDs/names for the group tree; no extra page pixmaps.
        if hasattr(self, 'group_tree'):
            self._refresh_group_tree()
        # Page count may have changed in the traditional thumbnail view.
        self.readingChanged.emit()
        self.schedule_thumbnails()

    def _visible_rows(self) -> set[int]:
        """Calculate scroll-visible rows plus up to 2 rows of padding, capped at 20."""
        count = self.pages_list.count()
        if not count:
            return set()
        view = self.pages_list
        height = view.viewport().height()
        probe = view.indexAt(QPoint(max(10, view.viewport().width() // 2), 3))
        if probe.isValid():
            first = probe.row()
        else:
            # During batched layout, itemAt may briefly fail; use rough estimate.
            first = min(count - 1, view.verticalScrollBar().value() // (getattr(view, '_responsive_row_height', view.ROW_HEIGHT) + view.spacing()))
        approx = max(1, height // (getattr(view, '_responsive_row_height', view.ROW_HEIGHT) + view.spacing()) + 3)
        last = min(count, first + approx)
        # Bounded memory even on unusually tall monitors.
        start = max(0, first - 2)
        end = min(count, last + 2, start + THUMB_LIMIT)
        return set(range(start, end))

    def schedule_thumbnails(self):
        if self._active and not self._closed and not self.window().isMinimized():
            self._thumb_timer.start()

    def update_visible_thumbnails(self):
        if not self._active or self._closed or self.window().isMinimized():
            return
        if getattr(self, '_navigator_view', 'thumbnails') == 'groups':
            self._update_group_thumbnails()
            return
        wanted = self._visible_rows()
        # Workers may be queued after a fast scroll. They can check this
        # lightweight immutable snapshot before decoding an obsolete page.
        self._wanted_thumbnail_ids = frozenset(self.project.pages[row]['id'] for row in wanted)
        for row in self._loaded_thumb_rows - wanted:
            self.pages_list.item(row).setIcon(QIcon())
        self._loaded_thumb_rows.intersection_update(wanted)
        # No more than 20 thumbnail QIcons are resident; on-demand worker jobs
        # are kept small even when scrolling a large document quickly.
        for row in sorted(wanted - self._loaded_thumb_rows):
            page = self.project.pages[row]
            pid = page['id']
            generation = self._generation
            bucket = self._thumbnail_bucket
            if (generation, pid) in self._thumb_pending or pid in self._thumb_failed or len(self._thumb_pending) >= THUMB_LIMIT:
                continue
            self._thumb_pending.add((generation, pid))
            def worker(page=page, generation=generation, pid=pid, bucket=bucket):
                if (generation != self._generation or not self._active
                        or pid not in self._wanted_thumbnail_ids):
                    return None
                return image_for_page(self.project, page, thumbnail=True,
                                      thumb_width=bucket if bucket > 110 else None)
            def complete(result, error, pid=pid, generation=generation):
                self._thumb_pending.discard((generation, pid))
                if error and generation == self._generation:
                    self._thumb_failed.add(pid)
                if self._active and generation == self._generation and not error and result:
                    matching = next((i for i, p in enumerate(self.project.pages) if p['id'] == pid), -1)
                    if matching in self._visible_rows():
                        # Avoid QPixmap(filename), which places another copy in
                        # Qt's global cache after the row scrolls off-screen.
                        reader = QImageReader(str(result))
                        decoded = reader.read()
                        pix = QPixmap.fromImage(decoded) if not decoded.isNull() else QPixmap()
                        if not pix.isNull():
                            self.pages_list.item(matching).setData(Qt.ItemDataRole.DecorationRole,
                                                              self._thumbnail_decoration(pix))
                            self._loaded_thumb_rows.add(matching)
                if self._active and generation == self._generation:
                    self.schedule_thumbnails()
            start_task(self, worker, complete, priority=-1)

    def _update_group_thumbnails(self):
        """Load only visible group-tree thumbnails using the old cache.

        Each page retains one original source document.  We decode
        only a small cached JPEG, and release offscreen QIcons promptly.
        This avoids another thumbnail engine and unbounded QPixmaps.
        """
        wanted = self.group_tree.visible_page_ids(limit=THUMB_LIMIT)
        visible = frozenset(wanted)
        self._wanted_group_thumb_ids = visible
        self.group_tree.discard_other_thumbnails(visible)
        lookup = {page['id']: page for page in self.project.pages}
        for pid in wanted:
            if pid in self.group_tree._thumb_ids or pid in self._thumb_failed:
                continue
            path = self.project.asset_path(f'cache/thumbs/{pid}.jpg')
            if path.is_file() and path.stat().st_size:
                reader = QImageReader(str(path))
                decoded = reader.read()
                if not decoded.isNull():
                    self.group_tree.set_page_thumbnail(
                        pid, QPixmap.fromImage(decoded))
                    continue
            if pid in self._group_thumb_pending or len(self._group_thumb_pending) >= THUMB_LIMIT:
                continue
            page = lookup.get(pid)
            if page is None:
                continue
            generation = self._generation
            self._group_thumb_pending.add(pid)

            def worker(page=page, generation=generation, pid=pid):
                if (generation != self._generation or not self._active
                        or pid not in self._wanted_group_thumb_ids):
                    return None
                return image_for_page(self.project, page, thumbnail=True)

            def complete(result, error, pid=pid, generation=generation):
                self._group_thumb_pending.discard(pid)
                if error and generation == self._generation:
                    # A broken source should not trigger an endless
                    # queue/retry cycle whenever the timer fires.
                    self._thumb_failed.add(pid)
                if (generation == self._generation and self._active
                        and not error and result
                        and pid in self._wanted_group_thumb_ids):
                    reader = QImageReader(str(result))
                    decoded = reader.read()
                    if not decoded.isNull():
                        self.group_tree.set_page_thumbnail(
                            pid, QPixmap.fromImage(decoded))
                if self._active and generation == self._generation:
                    self.schedule_thumbnails()

            start_task(self, worker, complete, priority=-1)

    def set_navigation_view(self, view, *, persist=True):
        """Switch views while preserving the actual reading page."""
        self._navigator_view = view
        self.nav_views.setCurrentWidget(
            self.group_tree if view == 'groups' else self.pages_list)
        self.show_groups_button.setChecked(view == 'groups')
        self.show_thumbs_button.setChecked(view == 'thumbnails')
        # Invalidate jobs from the now-hidden view.  Both navigators
        # reuse on-disk JPEGs, but only one needs resident QPixmaps.
        self._generation += 1
        self._thumb_pending.clear()
        self._group_thumb_pending.clear()
        self._wanted_thumbnail_ids = frozenset()
        self._wanted_group_thumb_ids = frozenset()
        if view == 'thumbnails':
            self.group_tree.discard_other_thumbnails(set())
            self._thumbnail_bucket = self._thumbnail_width_for_view()
        else:
            for row in self._loaded_thumb_rows:
                if row < self.pages_list.count():
                    self.pages_list.item(row).setIcon(QIcon())
            self._loaded_thumb_rows.clear()
            # The active marker follows the preview even if that page
            # sits inside a collapsed chapter folder.
            self.group_tree.mark_active(self.project.selected_page)
        self.schedule_thumbnails()
        if persist:
            self.settings.setValue('pageNavigatorView', view)
            self.schedule_save()

    def _refresh_group_tree(self):
        """Rebuild labels only; PDF thumbnails stay in the original list."""
        ids = [page['id'] for page in self.project.pages]
        if self.project.page_groups is None:
            self.project.page_groups = flat_tree(ids)
        else:
            self.project.page_groups = reconcile_group_tree(
                self.project.page_groups, ids)
        # Rebuilds happen on rename, imports and Undo.  Keep intentional
        # group/page selections; the active-reading marker is separate.
        selected = [(item.data(0, ROLE_KIND), item.data(0, ROLE_ID))
                    for item in self.group_tree.selectedItems()]
        self.group_tree.load_tree(
            self.project.page_groups, self.project.pages,
            self.project.selected_page, self.project.read_page_ids)
        for kind, identifier in selected:
            item = self.group_tree.find_item(kind, identifier)
            if item is not None:
                item.setSelected(True)
        self._group_thumb_pending.clear()
        self._wanted_group_thumb_ids = frozenset()
        self.schedule_thumbnails()
        self._refresh_reading_summary()

    def _refresh_reading_summary(self):
        """Keep the current tab's progress in sync with its live pages."""
        if not hasattr(self, 'reading_summary'):
            return
        live = {p['id'] for p in self.project.pages}
        done = len(live & set(self.project.read_page_ids))
        total = len(live)
        self.reading_summary.setText(
            f'Read {done:,} / {total:,} · '
            f'{percentage(done, total)}%' if total else 'Read 0 / 0')
        self.reading_progress.set_progress(100.0 * done / total if total else 0,
                                           animate=True, flash=True)

    def _apply_read_snapshot(self, ids):
        """Undo or Redo one completion change without touching note HTML.

        Qt group items are rebuilt from stable IDs on each update.
        Their checkboxes must never become the source of truth.
        """
        self.project.read_page_ids = sorted(ids)
        self._refresh_group_tree()
        self._celebrate_on_next_manual_save = True
        self.schedule_save()
        self.readingChanged.emit()

    def _toggle_read_status(self, kind, identifier, checked):
        """Tick one page or all descendants in exactly one history step."""
        try:
            if kind == 'page':
                targets = [identifier]
            else:
                from .page_groups import get_group
                from .reading_progress import descendants
                node = get_group(self.project.page_groups, identifier)
                if node is None:
                    return
                targets = list(descendants(node['children']))
            if not targets:
                self._refresh_group_tree()
                return
            previous = set(self.project.read_page_ids)
            new = set_read_status(
                previous, [p['id'] for p in self.project.pages],
                targets, checked)
            if new == previous:
                self._refresh_group_tree()
                return
            # Capture completion boundaries before the one-step history action.
            # Never celebrate on Undo/Redo, file loading, or page imports.
            completed_groups = []
            if checked:
                from .reading_progress import group_counts
                def scan(nodes):
                    for group in nodes:
                        if group['type'] != 'group':
                            continue
                        before, total = group_counts(group, previous)
                        after, _ = group_counts(group, new)
                        if total and before < total == after:
                            completed_groups.append((group['name'], total))
                        scan(group['children'])
                scan(self.project.page_groups)
            tab_was_complete = bool(self.project.pages) and len(previous) >= len(self.project.pages)
            tab_now_complete = bool(self.project.pages) and len(new) >= len(self.project.pages)
            self._separate_text_commands()
            self.history.perform(CallbackAction(
                'Mark Pages Read' if checked else 'Mark Pages Unread',
                lambda: self._apply_read_snapshot(previous),
                lambda: self._apply_read_snapshot(new),
                160 + len(targets) * 36))
            # Emit exactly once for a deliberate checkbox action, never for
            # Undo/Redo, imports, tab switches or loading a saved notebook.
            # Completion messages are display-only observers of this event.
            level, name = '', ''
            if checked and tab_now_complete and not tab_was_complete:
                level = 'tab'
            elif checked and completed_groups:
                # Prefer the outermost/largest newly completed group.
                name, _ = max(completed_groups, key=lambda item: item[1])
                level = 'group'
            live = {page['id'] for page in self.project.pages}
            delta = len(new & live) - len(previous & live)
            self.readingAction.emit(level, name, delta)
        except ValueError as exc:
            self._refresh_group_tree()
            QMessageBox.warning(self, 'Reading progress', str(exc))

    def _apply_group_snapshot(self, tree, pages, selected):
        """Apply one validated data snapshot for a group Undo/Redo action."""
        order = [page['id'] for page in pages]
        validate_group_tree(tree, order)
        self.project.pages = list(pages)
        self.project.page_groups = copy.deepcopy(tree)
        self.project.selected_page = (
            selected if selected in order else (order[0] if order else None))
        self.load_pages(select_id=self.project.selected_page)
        if not order:
            self.select_item(None, None)
        self._celebrate_on_next_manual_save = True
        self.schedule_save()
        self.readingChanged.emit()

    def _commit_group_edit(self, tree, label, *, removed_ids=()):
        """One hierarchy change is ONE per-tab Undoable history entry.

        Qt items are only a view.  The final source of truth is a valid
        tree whose page IDs match the project's flat reading sequence.
        """
        previous_tree = copy.deepcopy(self.project.page_groups)
        previous_pages = list(self.project.pages)
        previous_selected = self.project.selected_page
        remove = set(removed_ids)
        lookup = {p['id']: p for p in previous_pages}
        order = flatten(tree)
        if (len(order) != len(set(order))
                or set(order) != (set(lookup) - remove)):
            raise ValueError('This page move would lose or duplicate pages.')
        validate_group_tree(tree, order)
        new_pages = [lookup[pid] for pid in order]
        if (tree == previous_tree and
                order == [p['id'] for p in previous_pages]):
            self._refresh_group_tree()
            return
        self._separate_text_commands()
        new_tree = copy.deepcopy(tree)
        self.history.perform(CallbackAction(
            label,
            lambda: self._apply_group_snapshot(
                previous_tree, previous_pages, previous_selected),
            lambda: self._apply_group_snapshot(
                new_tree, new_pages, previous_selected),
            512 + len(order) * 72,
        ))

    def _move_whole_group(self, group_id, destination_id, index):
        """Commit a dragged folder and ALL its descendants in one action.

        Moving a folder updates the actual flat page order as well as
        the tree.  Reading completion and source PDF bytes are untouched.
        """
        try:
            new_tree = move_group(
                self.project.page_groups, group_id, destination_id, index)
            self._commit_group_edit(new_tree, 'Move Page Group')
        except (ValueError, KeyError, TypeError) as exc:
            self._refresh_group_tree()
            QMessageBox.warning(self, 'Cannot move group', str(exc))

    def _group_tree_dropped(self):
        """Validate a drag before it changes persistent group/page order."""
        try:
            self._commit_group_edit(
                self.group_tree.extract_tree(), 'Reorganise Page Groups')
        except (ValueError, KeyError, TypeError) as exc:
            self._refresh_group_tree()
            QMessageBox.warning(self, 'Cannot move pages', str(exc))

    def _group_collapse_changed(self, group_id, collapsed):
        """Collapsing changes visibility, never reading order."""
        self.project.page_groups = set_collapsed(
            self.project.page_groups, group_id, collapsed)
        self.group_tree.mark_active(self.project.selected_page)
        self.schedule_thumbnails()
        self.schedule_save()

    def _chosen_group(self):
        # Only an explicitly selected group is an organisation target.
        # The displayed page must not silently decide import placement.
        return self.group_tree.selected_group_id()

    def create_page_group(self, parent_id=None, *, root=False):
        """Make an empty folder, optionally nested below a selected group."""
        if parent_id is None and not root:
            parent_id = self._chosen_group()
        name, ok = QInputDialog.getText(
            self, 'New page group', 'Group name:')
        if not ok or not name.strip():
            return
        try:
            tree, _gid = insert_group_node(
                self.project.page_groups, name, parent_id=parent_id)
            self._commit_group_edit(tree, 'Create Page Group')
        except ValueError as exc:
            QMessageBox.warning(self, 'Cannot create group', str(exc))

    def group_selected_pages(self):
        """Group only adjacent page leaves with the same parent folder."""
        ids = self.group_tree.selected_page_ids()
        if not ids:
            QMessageBox.information(self, 'Group pages',
                'Select adjacent pages in Groups view first.')
            return
        name, ok = QInputDialog.getText(
            self, 'Group selected pages', 'Name for this group:')
        if not ok or not name.strip():
            return
        try:
            tree, _gid = wrap_group_pages(
                self.project.page_groups, ids, name)
            self._commit_group_edit(tree, 'Group Selected Pages')
        except ValueError as exc:
            QMessageBox.warning(self, 'Cannot group pages', str(exc))

    def rename_page_group(self, group_id):
        group = next((node for node in self._walk_groups()
                      if node['id'] == group_id), None)
        if group is None:
            return
        name, ok = QInputDialog.getText(
            self, 'Rename group', 'Group name:', text=group['name'])
        if ok and name.strip():
            try:
                self._commit_group_edit(
                    change_group_name(self.project.page_groups, group_id, name),
                    'Rename Page Group')
            except ValueError as exc:
                QMessageBox.warning(self, 'Cannot rename group', str(exc))

    def _walk_groups(self):
        def walk(nodes):
            for node in nodes:
                if node['type'] == 'group':
                    yield node
                    yield from walk(node['children'])
        return walk(self.project.page_groups or [])

    def ungroup_page_group(self, group_id):
        try:
            self._commit_group_edit(
                dissolve_group(self.project.page_groups, group_id),
                'Ungroup Pages')
        except ValueError as exc:
            QMessageBox.warning(self, 'Cannot ungroup pages', str(exc))

    def delete_page_group(self, group_id):
        try:
            tree, removed = remove_group_and_pages(
                self.project.page_groups, group_id)
        except ValueError as exc:
            QMessageBox.warning(self, 'Cannot delete group', str(exc))
            return
        answer = QMessageBox.question(
            self, 'Delete group and its pages',
            f'Delete this group and its {len(removed)} page(s)?\n\n'
            'The original pages can be restored with Undo during this session.\n'
            'Use Ungroup to keep them instead.',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if answer == QMessageBox.StandardButton.Yes:
            self._commit_group_edit(
                tree, 'Delete Group and Pages', removed_ids=removed)

    def move_pages_into_group(self, group_id):
        ids = self.group_tree.selected_page_ids()
        if not ids:
            return
        try:
            tree = move_pages_to_group(
                self.project.page_groups, ids, group_id)
            self._commit_group_edit(tree, 'Move Pages Into Group')
        except ValueError as exc:
            QMessageBox.warning(self, 'Cannot move pages', str(exc))

    def group_context_menu(self, point):
        """Context options depend on whether a page or folder was clicked."""
        item = self.group_tree.itemAt(point)
        if item is not None and not item.isSelected():
            self.group_tree.clearSelection()
            self.group_tree.setCurrentItem(item)
        group_id = (item.data(0, ROLE_ID)
                    if item is not None and
                    item.data(0, ROLE_KIND) == 'group' else None)
        menu = QMenu(self.group_tree)
        if item is not None:
            kind = item.data(0, ROLE_KIND)
            identifier = item.data(0, ROLE_ID)
            checked = kind == 'page' and identifier in self.project.read_page_ids
            if kind == 'group':
                from .page_groups import get_group
                node = get_group(self.project.page_groups, identifier)
                if node is not None:
                    done, total = group_counts(
                        node, set(self.project.read_page_ids))
                    checked = bool(total and done == total)
            menu.addAction(
                'Mark all unread' if checked and kind == 'group'
                else 'Mark as unread' if checked
                else 'Mark all read' if kind == 'group'
                else 'Mark as read',
                lambda _=False, k=kind, pid=identifier, value=not checked:
                self._toggle_read_status(k, pid, value))
            if kind == 'page':
                menu.addAction('Remove this page…',
                    lambda _=False, pid=identifier: self.remove_page_ids_confirmed([pid]))
            menu.addSeparator()
        menu.addAction('New group…', lambda: self.create_page_group(root=True))
        menu.addAction('Group selected pages…', self.group_selected_pages)
        if group_id:
            menu.addSeparator()
            menu.addAction('Add subgroup…',
                           lambda gid=group_id: self.create_page_group(gid))
            menu.addAction('Rename group…',
                           lambda gid=group_id: self.rename_page_group(gid))
            menu.addAction('Ungroup (keep pages)',
                           lambda gid=group_id: self.ungroup_page_group(gid))
            menu.addAction('Delete group AND pages…',
                           lambda gid=group_id: self.delete_page_group(gid))
        if item is not None and item.data(0, ROLE_KIND) == 'page':
            self._reading_page_menu(menu, item.data(0, ROLE_ID))
        if group_id:
            selected_groups = [i.data(0, ROLE_ID) for i in
                self.group_tree.selectedItems()
                if i.data(0, ROLE_KIND) == 'group']
            self._reading_group_menu(menu, selected_groups or [group_id])
        if self.group_tree.selected_page_ids():
            move_menu = menu.addMenu('Move selected pages into…')
            for group in self._walk_groups():
                move_menu.addAction(group['name'],
                    lambda _=False, gid=group['id']:
                    self.move_pages_into_group(gid))
        menu.addSeparator()
        menu.addAction('Undo', self.undo_remove_pages).setEnabled(
            self.history.can_undo)
        menu.exec(self.group_tree.viewport().mapToGlobal(point))

    def activate(self):
        self._active = True
        # A pane can be laid out at a near-zero width while its tab is
        # hidden. Re-evaluate the REAL visible width before thumbnails are
        # requested, or the previous Mini/Rail mode may hide page labels.
        QTimer.singleShot(0, self._sync_navigator_width)
        if not self._notes_scroll_restored:
            # Once the tab becomes visible, the editor has a real viewport
            # height and its scroll maximum can be calculated correctly.
            QTimer.singleShot(35, self._restore_notes_scroll)
        # Old 10%/25% and HD files are disposable; cleanup does not touch
        # the live page, original documents, notes or normal caches.
        if not getattr(self, '_old_tiers_cleanup_started', False):
            self._old_tiers_cleanup_started = True
            start_task(self, lambda: clear_obsolete_preview_tiers(self.project),
                       lambda *_: None, priority=-3)
        self._thumbnail_bucket = self._thumbnail_width_for_view()
        self.schedule_thumbnails()
        if self.current_page():
            self.display_current()

    def deactivate(self):
        # A tab switch hides the OCR UI but does not cancel its worker.
        # The result will remain available when this tab is reactivated.
        if hasattr(self, 'ocr_bar') and self.ocr_bar.isVisible():
            self.leave_ocr_mode(cancel_running=False)
        self._capture_displayed_reading_position()
        self._view_scroll_timer.stop()
        self._view_displayed_page_id = None
        self._view_restoring = True
        self._active = False
        self._generation += 1
        self._preview_token += 1
        self._quality_token += 1
        self._quality_timer.stop()
        self._thumb_rescale_timer.stop()
        self._thumb_timer.stop()
        self.canvas.stop_bicubic()
        for row in self._loaded_thumb_rows:
            if row < self.pages_list.count():
                self.pages_list.item(row).setIcon(QIcon())
        self._loaded_thumb_rows.clear()
        self._thumb_pending.clear()
        self._wanted_thumbnail_ids = frozenset()
        self.canvas.show_image(None)
        self._view_restoring = False

    def select_page_id(self, page_id: str):
        row = next((i for i,p in enumerate(self.project.pages) if p['id'] == page_id), -1)
        if row < 0:
            self.statusMessage.emit('The referenced page is no longer in this project.')
        else:
            self.pages_list.setCurrentRow(row)
            self.pages_list.scrollToItem(self.pages_list.item(row))
            self.schedule_thumbnails()

    def select_item(self, item, previous):
        # Changing the PDF page must not throw away completed OCR text.
        # Explicit Cancel/Escape still stops recognition normally.
        if hasattr(self, 'ocr_bar') and self.ocr_bar.isVisible():
            self.leave_ocr_mode(cancel_running=False)
        if self._loading:
            return
        page = self.current_page()
        self.project.selected_page = page['id'] if page else None
        if page:
            self.page_title.setText(page['title'])
            self.page_title._has_page = True
            self.page_position.setText(f'{self.pages_list.currentRow()+1:,} / {self.pages_list.count():,}')
        else:
            self.page_title.setText('PAGE PREVIEW')
            self.page_title._has_page = False
            self.page_position.setText('No page selected')
        if hasattr(self, 'group_tree') and page:
            self.group_tree.mark_active(page['id'])
        self.display_current()
        self.schedule_save()

    def display_current(self):
        # Selection already points to the NEXT page. Capture the
        # actual displayed page before clearing its graphics scene.
        self._capture_displayed_reading_position()
        self._view_scroll_timer.stop()
        self._view_displayed_page_id = None
        self._view_restoring = True
        self._preview_token += 1
        self._quality_token += 1
        self._clarity_token += 1
        self._clarity_applied_signature = None
        self._displayed_cache_path = None
        self._quality_timer.stop()
        self._normal_preview_path = None
        self._quality_level = 1.0
        token = self._preview_token
        self.canvas.show_image(None)
        page = self.current_page()
        if not page or not self._active:
            self._view_restoring = False
            return
        self.statusMessage.emit('Loading page…')
        def worker():
            if token != self._preview_token or not self._active:
                return None
            return image_for_page(self.project, page, thumbnail=False)
        def done(path, error):
            if token != self._preview_token or not self._active:
                return
            if error:
                self._view_restoring = False
                self.statusMessage.emit('Could not render page: ' + error)
            elif path:
                if self.canvas.show_image(path):
                    self._normal_preview_path = Path(path)
                    self._displayed_cache_path = Path(path)
                    self._quality_level = 1.0
                    self._clarity_token += 1
                    self._clarity_applied_signature = None
                    self.canvas.set_annotations(self.project.annotations.get(page['id'], []))
                    self._view_displayed_page_id = page['id']
                    # Defer until layout/scroll ranges are stable; stale
                    # callbacks are rejected using the render token.
                    QTimer.singleShot(0, lambda pid=page['id'], ticket=token:
                        self._apply_loaded_reading_view(pid, ticket))
                    # The first fit-page emission preceded _normal_preview_path;
                    # schedule progressive quality now that the base is known.
                    self._quality_timer.start()
                    self.statusMessage.emit('Page ready')
                    self.prefetch_neighbours(token)
                else:
                    self._view_restoring = False
                    self.statusMessage.emit('Could not decode the cached page preview.')
        start_task(self, worker, done, priority=3)

    def prefetch_neighbours(self, token):
        row = self.pages_list.currentRow()
        for offset in (-1, 1):
            index = row + offset
            if 0 <= index < len(self.project.pages):
                page = self.project.pages[index]
                def worker(page=page):
                    if token != self._preview_token or not self._active:
                        return None
                    return image_for_page(self.project, page, thumbnail=False)
                start_task(self, worker, lambda *_: None, priority=-3)

    # --- Reading View Memory: per-page scroll, inherited root-group zoom ---
    def _reading_flag(self, key, default=True):
        value = self.settings.value(key, 'true' if default else 'false')
        return str(value).lower() in ('true', '1', 'yes')

    def _reading_data(self):
        # An opt-out still remembers scroll/zoom during this open session,
        # but never writes those ephemeral values into a saved notebook.
        if not self._reading_flag('readingViewPersist'):
            return self._session_reading_view
        if not isinstance(self.project.reading_view, dict):
            self.project.reading_view = empty_view()
        for key, fallback in empty_view().items():
            if key not in self.project.reading_view:
                self.project.reading_view[key] = fallback
        return self.project.reading_view

    def _reading_scroll_moved(self, *_):
        if (self._view_restoring or not self._view_displayed_page_id
                or not self._active or not self._reading_flag('readingViewRememberScroll')):
            return
        # One 650ms idle snapshot; never serialize on every trackpad pixel.
        self._view_scroll_timer.start()

    def _capture_displayed_reading_position(self):
        pid = self._view_displayed_page_id
        if (not pid or self._view_restoring
                or not self._reading_flag('readingViewRememberScroll')):
            return
        position = self.canvas.capture_reading_position()
        if position is None:
            return
        positions = self._reading_data()['positions']
        if positions.get(pid) != position:
            positions[pid] = position
            self.schedule_save()

    def _record_visible_reading_zoom(self, percentage, is_fit):
        pid = self._view_displayed_page_id
        if not pid or self._view_restoring or not self._active or percentage <= 0:
            return
        state = {'mode': 'fit'} if is_fit else {
            'mode': 'manual', 'scale': percentage / 100.0}
        view = self._reading_data()
        prior = effective_zoom(view, self.project.page_groups, pid,
                               self._reading_flag('readingViewSharedZoom'))
        if prior != normalise_zoom(state):
            remember_zoom(view, self.project.page_groups, pid, state,
                          self._reading_flag('readingViewSharedZoom'))
            self.schedule_save()
        self._reading_scroll_moved()

    def _apply_loaded_reading_view(self, pid, token):
        # This is deferred until Qt has laid out the real canvas viewport.
        # A late worker or rapid page switch must NEVER apply stale state.
        current = self.current_page()
        if (token != self._preview_token or not self._active
                or self._view_displayed_page_id != pid
                or current is None or current['id'] != pid):
            return
        self._view_restoring = True
        try:
            view = self._reading_data()
            zoom = effective_zoom(view, self.project.page_groups, pid,
                                  self._reading_flag('readingViewSharedZoom'))
            self.canvas.apply_reading_zoom(zoom)
            position = (view['positions'].get(pid)
                        if self._reading_flag('readingViewRememberScroll') else None)
            self.canvas.restore_reading_position(position,
                start_at_top=self._reading_flag('readingViewStartAtTop'))
        finally:
            self._view_restoring = False

    def _refresh_visible_reading_view(self):
        # Used after an explicit context-menu reset or inheritance toggle.
        pid = self._view_displayed_page_id
        if pid and self._active and not self.canvas.image_item.pixmap().isNull():
            self._view_scroll_timer.stop()
            self._apply_loaded_reading_view(pid, self._preview_token)

    def _change_page_zoom_sharing(self, page_id, independent):
        view = self._reading_data()
        set_page_independent(view, self.project.page_groups, page_id,
                             independent, self._reading_flag('readingViewSharedZoom'))
        self.schedule_save()
        if page_id == self._view_displayed_page_id:
            self._refresh_visible_reading_view()

    def _reset_page_reading_state(self, page_id, kind):
        view = self._reading_data()
        if kind == 'position':
            view['positions'].pop(page_id, None)
        else:
            root = root_for_page(self.project.page_groups, page_id)
            if root:
                set_page_independent(view, self.project.page_groups, page_id, True)
            view['page_zooms'][page_id] = fit_zoom()
        self.schedule_save()
        if page_id == self._view_displayed_page_id:
            self._refresh_visible_reading_view()

    def _reading_page_menu(self, menu, page_id):
        view = self._reading_data()
        sub = menu.addMenu('Reading view')
        root = root_for_page(self.project.page_groups, page_id)
        if root:
            independent = page_id in view['independent_pages']
            use_group = sub.addAction('Use group zoom')
            use_group.setCheckable(True)
            use_group.setChecked(not independent and
                root not in view['unshared_roots'])
            use_group.triggered.connect(
                lambda checked=False, pid=page_id:
                self._change_page_zoom_sharing(pid, False))
            use_independent = sub.addAction('Use independent zoom')
            use_independent.setCheckable(True)
            use_independent.setChecked(independent or
                root in view['unshared_roots'])
            use_independent.triggered.connect(
                lambda checked=False, pid=page_id:
                self._change_page_zoom_sharing(pid, True))
            sub.addSeparator()
        sub.addAction('Reset this page zoom to Fit',
            lambda _=False, pid=page_id:
                self._reset_page_reading_state(pid, 'zoom'))
        sub.addAction('Reset this page reading position',
            lambda _=False, pid=page_id:
                self._reset_page_reading_state(pid, 'position'))

    def _toggle_root_zoom_sharing(self, roots, shared):
        view = self._reading_data()
        for root in roots:
            set_root_shared(view, self.project.page_groups, root, shared)
        self.schedule_save()
        self._refresh_visible_reading_view()

    def _reset_group_reading_state(self, group_ids, kind):
        view = self._reading_data()
        all_pages = set()
        roots = set()
        for gid in group_ids:
            all_pages.update(pages_in_group(self.project.page_groups, gid))
            root = root_for_group(self.project.page_groups, gid)
            if root:
                roots.add(root)
        if kind in ('positions', 'all'):
            for page_id in all_pages:
                view['positions'].pop(page_id, None)
        if kind in ('zoom', 'all'):
            # A subgroup inherits its root's zoom. Resetting that zoom affects
            # the other pages of the same root group, as expected.
            for root in roots:
                view['group_zooms'][root] = fit_zoom()
        if kind in ('overrides', 'zoom', 'all'):
            independent = set(view['independent_pages'])
            independent.difference_update(all_pages)
            view['independent_pages'] = sorted(independent)
            for page_id in all_pages:
                view['page_zooms'].pop(page_id, None)
        if kind == 'all':
            view['unshared_roots'] = sorted(
                set(view['unshared_roots']) - roots)
        self.schedule_save()
        if self._view_displayed_page_id in all_pages or kind in ('zoom', 'all'):
            self._refresh_visible_reading_view()

    def _reading_group_menu(self, menu, group_ids):
        group_ids = list(dict.fromkeys(group_ids))
        roots = sorted({root_for_group(self.project.page_groups, gid)
                        for gid in group_ids} - {None})
        if not roots:
            return
        view = self._reading_data()
        label = ('Reading view · selected groups' if len(group_ids) > 1
                 else 'Reading view · group')
        sub = menu.addMenu(label)
        sharing = all(root not in view['unshared_roots'] for root in roots)
        shared_action = sub.addAction('Share zoom across root group')
        shared_action.setCheckable(True)
        shared_action.setChecked(sharing)
        shared_action.triggered.connect(
            lambda checked, selected=tuple(roots):
                self._toggle_root_zoom_sharing(selected, checked))
        sub.addSeparator()
        sub.addAction('Reset group zoom to Fit',
            lambda _=False, selected=tuple(group_ids):
                self._reset_group_reading_state(selected, 'zoom'))
        sub.addAction('Reset reading positions',
            lambda _=False, selected=tuple(group_ids):
                self._reset_group_reading_state(selected, 'positions'))
        sub.addAction('Clear individual zoom overrides',
            lambda _=False, selected=tuple(group_ids):
                self._reset_group_reading_state(selected, 'overrides'))
        sub.addSeparator()
        sub.addAction('Reset all reading view settings',
            lambda _=False, selected=tuple(group_ids):
                self._reset_group_reading_state(selected, 'all'))

    def _on_preview_zoom(self, percentage: float, is_fit: bool):
        # Invalidate any *in-flight* image before the 260 ms debounce runs.
        # Otherwise an old zoom render could land after a fast pinch back.
        self._quality_token += 1
        self._clarity_token += 1  # prevent stale sharpening on pan/zoom
        self._clarity_applied_signature = None
        if hasattr(self, 'fit_action'):
            # setChecked() never triggers a new command, so wheel/pinch/100%
            # can turn off the visible indicator without recursion.
            self.fit_action.setChecked(is_fit if percentage else self.canvas._fit)
        if hasattr(self, 'preview_zoom_label'):
            self.preview_zoom_label.setText('Page · ' +
                (f'{percentage:.0f}%' + (' (Fit)' if is_fit else '')
                 if percentage else '—'))
        if self._active and self._normal_preview_path and percentage > 0:
            self._quality_timer.start()
        self._record_visible_reading_zoom(percentage, is_fit)

    def _update_adaptive_quality(self):
        """One small on-demand render matching any settled zoom below 100%.

        Users can zoom freely, without fixed 10/25/100/200 tiers. We snap
        requested *raster quality* up to 5% buckets only to avoid spamming the
        disk during a smooth pinch. Beyond 100% Qt smoothly enlarges the
        original normal bitmap, as requested; there is no HD bitmap cache.
        """
        if (not self._active or self.window().isMinimized()
                or self.canvas.image_item.pixmap().isNull()):
            return
        page = self.current_page()
        if not page or self._normal_preview_path is None:
            return
        screen = self.canvas.screen()
        dpr = min(2.0, max(1.0, screen.devicePixelRatio() if screen else 1.0))
        effective = abs(self.canvas.transform().m11()) * dpr
        target = (1.0 if effective >= .96 else
                  max(.10, min(1.0, math.ceil((effective - 1e-9) * 20) / 20)))
        if target == self._quality_level:
            return
        self._quality_token += 1
        variant_token = self._quality_token
        page_token = self._preview_token
        page_id = page['id']
        if target == 1.0:
            self._apply_preview_quality(self._normal_preview_path, target,
                                        variant_token, page_token, page_id)
            return

        def worker(page=page, target=target):
            if (page_token != self._preview_token or variant_token != self._quality_token
                    or not self._active):
                return None
            return image_for_page(self.project, page, thumbnail=False, level=target)

        def done(path, error):
            if error:
                self.statusMessage.emit('Adaptive preview: ' + error)
            elif path:
                self._apply_preview_quality(path, target, variant_token,
                                            page_token, page_id)

        start_task(self, worker, done, priority=2)

    def _apply_preview_quality(self, path, target, variant_token, page_token, page_id):
        if (variant_token != self._quality_token or
                page_token != self._preview_token or not self._active or
                self.window().isMinimized() or
                not self.current_page() or self.current_page()['id'] != page_id):
            return
        if self.canvas.replace_quality_image(Path(path)):
            self._displayed_cache_path = Path(path)
            self._quality_level = target
            self._clarity_token += 1
            self._clarity_applied_signature = None
            self._schedule_preview_clarity()

    def _schedule_preview_clarity(self):
        """Soft text sharpening for an already-downscaled *active* preview.

        Only low-zoom cached JPEGs are considered. We reject rasters over
        1.5 MP and display original pixels immediately while a single
        background job works. No disk writes, new caches or duplicate PDFs.
        """
        mode = str(self.settings.value('previewClarity', 'crisp')).lower()
        if (mode not in ('gentle', 'crisp') or self._quality_level >= .96
                or self._clarity_in_flight or not self._active
                or self.window().isMinimized() or not self.current_page()
                or not self._displayed_cache_path):
            return
        page_id = self.current_page()['id']
        path = Path(self._displayed_cache_path)
        signature = (page_id, str(path), self._quality_level, mode)
        if signature == self._clarity_applied_signature:
            return
        token = self._clarity_token
        page_token = self._preview_token
        self._clarity_in_flight = True

        def worker():
            if token != self._clarity_token:
                return None
            return sharpen_cached_preview(path, mode)

        def done(result, error):
            self._clarity_in_flight = False
            if (token != self._clarity_token or page_token != self._preview_token
                    or not self._active or self.window().isMinimized()
                    or not self.current_page()
                    or self.current_page()['id'] != page_id
                    or str(self._displayed_cache_path) != str(path)):
                # If zoom changed while the old job ran, schedule the latest.
                if self._active and not self.window().isMinimized():
                    self._schedule_preview_clarity()
                return
            if error:
                self.statusMessage.emit('Text clarity refinement: ' + str(error))
            elif result:
                w, h, pixels = result
                if self.canvas.replace_quality_rgb(w, h, pixels):
                    self._clarity_applied_signature = signature

        start_task(self, worker, done, priority=-2)

    def update_preview_clarity(self):
        """Preference changed: restore original JPEG before optional re-sharp."""
        self._clarity_token += 1
        self._clarity_applied_signature = None
        if self._displayed_cache_path and self.current_page():
            self.canvas.replace_quality_image(self._displayed_cache_path)
            self._schedule_preview_clarity()

    def canvas_fit(self, *_):
        # Pressing an already active Fit toggle turns *off* automatic fitting
        # without jumping the image; the current view transform remains.
        if self.canvas._fit:
            self.canvas.disable_fit()
        else:
            self.canvas.fit_page()

    def canvas_actual(self):
        self.canvas.actual_pixels()

    def move_selection(self, delta):
        target = self.pages_list.currentRow() + delta
        if 0 <= target < self.pages_list.count():
            self.pages_list.setCurrentRow(target)

    def _selected_insertion_index(self):
        row = self.pages_list.currentRow()
        return row + 1 if row >= 0 else len(self.project.pages)

    def _apply_page_order(self, tab_id, order):
        if tab_id != getattr(self, '_tab_id', None):
            return
        lookup = {page['id']: page for page in self.project.pages}
        if set(lookup) != set(order):
            raise ValueError('Page order has changed since the edit.')
        selected = self.project.selected_page
        self.project.pages = [lookup[pid] for pid in order]
        # The thumbnail list is the legacy flat-order editor.  Reconcile
        # any affected group spans without changing actual page objects.
        self.project.page_groups = reconcile_group_tree(
            self.project.page_groups or flat_tree(order), order)
        self._generation += 1
        self.load_pages(select_id=selected)
        if selected:
            self.select_page_id(selected)
        self._celebrate_on_next_manual_save = True
        self.schedule_save()

    def move_page(self, delta):
        row = self.pages_list.currentRow()
        target = row + delta
        if 0 <= row < self.pages_list.count() and 0 <= target < self.pages_list.count():
            item = self.pages_list.takeItem(row)
            self.pages_list.insertItem(target, item)
            self.pages_list.setCurrentItem(item)
            self.reorder_pages()

    def reorder_pages(self):
        before = [p['id'] for p in self.project.pages]
        order = [self.pages_list.item(i).data(Qt.ItemDataRole.UserRole)
                 for i in range(self.pages_list.count())]
        if before == order:
            return
        # Snapshot the group tree too.  Reordering the thumbnail list can
        # split a group; Undo must restore its original hierarchy exactly.
        previous_tree = copy.deepcopy(self.project.page_groups)
        pages_by_id = {p['id']: p for p in self.project.pages}
        selected = self.project.selected_page
        self._separate_text_commands()
        # Drag already moved the list widget; apply and record exactly once.
        self._apply_page_order(self._tab_id, order)
        new_tree = copy.deepcopy(self.project.page_groups)
        def apply_order(tabid, ids):
            if tabid != self._tab_id:
                return
            tree = previous_tree if ids == before else new_tree
            self._apply_group_snapshot(
                tree, [pages_by_id[pid] for pid in ids], selected)
        self.history.record_applied(reorder_pages_action(
            self._tab_id, before, order, apply_order))

    def _import_group_destinations(self):
        """Selectable group destinations independent of the active preview page.

        Only a group selected in the navigator preselects the dialog. Users
        may explicitly choose any other folder, or the root of this tab.
        """
        destinations = []
        def walk(nodes, ancestors):
            for node in nodes:
                if node['type'] == 'group':
                    path = ancestors + [node['name']]
                    destinations.append((node['id'], ' / '.join(path)))
                    walk(node['children'], path)
        walk(self.project.page_groups or [], [])
        return destinations

    def choose_files_at(self, position):
        self.choose_files(position)

    def choose_files(self, position=None, *, smart_default=False):
        """Ask where imported files go and how their pages are labelled.

        Import is explicit: no selected group means root.  Smart Import
        nests a new document group in the selected group, if any.
        """
        group_id = (self._chosen_group()
                    if self._navigator_view == 'groups' else None)
        filters = ('Supported files (*.pdf *.epub *.doc *.docx *.odt *.rtf *.ppt *.pptx '
                   '*.odp *.xls *.xlsx *.ods *.txt *.png *.jpg *.jpeg *.tif *.tiff '
                   '*.bmp *.gif *.webp);;All files (*)')
        start = self.settings.value('lastImportDir', str(Path.home() / 'Documents'))
        paths, _ = QFileDialog.getOpenFileNames(
            self, 'Import pages and images', start, filters)
        if not paths:
            return
        self.settings.setValue('lastImportDir', str(Path(paths[0]).parent))
        preset = str(self.settings.value('importLabelFormat',
                                         'filename_page'))
        dialog = ImportOptionsDialog(
            self, smart=smart_default, file_count=len(paths),
            target_group=group_id, destination_groups=self._import_group_destinations(),
            preset=preset, files=paths,
            custom=str(self.settings.value(
                'importCustomLabel', '{filename} · Page {n}')),
            collapse_new_groups=self.settings.value(
                'smartImportCollapseGroups', True, type=bool))
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        options = dialog.options()
        self.settings.setValue('importLabelFormat', options['label_format'])
        self.settings.setValue('importCustomLabel', options['custom_format'])
        self.settings.setValue(
            'smartImportCollapseGroups', options['collapse_new_groups'])
        # The destination is explicitly chosen *in the dialog*. The preview
        # page is never an implicit destination for incoming pages.
        chosen_destination = options.pop('group_id')
        self.import_paths(
            paths, position if type(position) is int else len(self.project.pages),
            group_id=chosen_destination, **options)

    def import_paths(self, paths: list[str], position: int | None = None,
                     group_id: str | None = None, *,
                     smart_import=False, label_format=None,
                     custom_format='', group_label='',
                     smart_group_mode='per_file', structure_mode='auto',
                     page_interval=20, max_subgroup_depth=2,
                     collapse_new_groups=True):
        """Import using safe filenames, then place each batch deliberately.

        The worker touches only files and Python data; it NEVER creates
        or changes Qt widgets.  The GUI callback owns the entire grouping
        and Undo transaction when all successful files have been indexed.
        """
        paths = [str(Path(p)) for p in paths if p]
        if not paths:
            return
        # A notebook is never a document/page import. In particular, a drop
        # over a previewed page must not anchor a whole-tab exchange there.
        notebook_paths = [p for p in paths if Path(p).suffix.lower() in
                          ('.yomunote', '.yominote')]
        if notebook_paths:
            if len(paths) == 1 and len(notebook_paths) == 1:
                self.notebookDropped.emit(notebook_paths[0])
            else:
                self.statusMessage.emit('Drop one .yomunote notebook at a time; '
                                        'do not mix notebook files and documents.')
            return
        if self._importing:
            self.statusMessage.emit(
                'An import is already in progress; please let it finish.')
            return
        position = len(self.project.pages) if position is None else max(0, position)
        self._importing = True
        self.import_button.setEnabled(False)
        self.statusMessage.emit('Importing documents in the background…')
        def worker():
            batches, errors, structures = [], [], []
            for path_text in paths:
                path = Path(path_text)
                pages = None
                if path.suffix.lower() not in ALL_EXTS:
                    errors.append(f'{path.name}: unsupported format')
                    continue
                try:
                    pages = import_document(self.project, path)
                    if label_format is not None and not (
                            smart_import and smart_group_mode == 'combined'):
                        label_imported_pages(pages, path.stem,
                                             label_format, custom_format)
                    batches.append((path.stem, pages))
                    # Outline detection is for SELECTION as well as grouping.
                    # Even when users request no new chapter groups, detected
                    # bookmarks must remain available as inclusion filters.
                    structures.append(detected_structure(self.project, pages)
                                      if len(pages) > 1 and structure_mode != 'ranges'
                                      else {'page_count':len(pages), 'sections': [],
                                            'source':'Manual / fixed ranges', 'warnings':[]})
                except Exception as exc:
                    if pages:
                        cleanup_uncommitted(self.project, [(path.stem, pages)])
                    errors.append(f'{path.name}: {exc}')
            if (smart_import and smart_group_mode == 'combined' and
                    label_format is not None):
                total = sum(len(pages) for _name, pages in batches)
                counter = 0
                try:
                    for name, pages in batches:
                        for page in pages:
                            counter += 1
                            page['title'] = make_title(
                                name, counter, total,
                                label_format, custom_format)
                except ValueError as exc:
                    # Even late label failures must not leave unreferenced
                    # originals behind or commit a half-labelled batch.
                    cleanup_uncommitted(self.project, batches)
                    return [], errors + [f'Page labels: {exc}'], []
            return batches, errors, structures
        def done(result, error):
            self._importing = False
            self.import_button.setEnabled(True)
            if error:
                QMessageBox.warning(self, 'Import failed', error)
                return
            batches, errors, structures = result
            added = [page for _name, batch in batches for page in batch]
            # A chosen destination may have been deleted while indexing took
            # place. Fail closed: never silently re-route into the root.
            if (added and group_id is not None and not any(
                    target_id == group_id for target_id, _label
                    in self._import_group_destinations())):
                cleanup_uncommitted(self.project, batches)
                QMessageBox.warning(self, 'Import destination changed',
                    'The selected group no longer exists. Nothing was added. '
                    'Choose a new destination and import again.')
                return
            # Keep a handle to ALL staged assets until the transaction commits.
            # An omitted page can share a PDF original with an included page.
            original_batches = batches
            omitted_batches = []
            sections_by_file = [[] for _ in batches]
            needs_review = bool(added and (smart_import or any(
                len(pages) > 1 for _name, pages in batches)))
            if needs_review:
                label = ('Root of this tab' if group_id is None else next(
                    (name for target_id, name in self._import_group_destinations()
                     if target_id == group_id), 'Selected group'))
                try:
                    review = SmartImportReviewDialog(
                        self, self.project, batches, structures,
                        destination_label=label, arrangement=smart_group_mode,
                        structure_mode=(structure_mode if smart_import and structure_mode != 'none' else 'auto'),
                        page_interval=page_interval,
                        max_subgroup_depth=max_subgroup_depth,
                        selection_only=not smart_import)
                    accepted = review.exec() == QDialog.DialogCode.Accepted
                    if accepted:
                        sections_by_file = review.sections_by_file()
                        selected_page_numbers = review.selected_pages_by_file()
                except (ValueError, TypeError) as exc:
                    cleanup_uncommitted(self.project, original_batches)
                    QMessageBox.warning(self, 'Cannot review document structure', str(exc))
                    return
                if not accepted:
                    cleanup_uncommitted(self.project, original_batches)
                    self.statusMessage.emit('Smart Import cancelled; no pages were added.')
                    return
            if added and needs_review and label_format == 'custom':
                # Chapter labels must use the user's FINAL boundaries, not
                # the original detected PDF bookmarks. Keep all changes on
                # staged pages until the validated group plan is committed.
                from .import_labels import (uses_chapter_token,
                                            relabel_reviewed_chapters)
                if uses_chapter_token(custom_format):
                    try:
                        relabel_reviewed_chapters(
                            batches, sections_by_file, custom_format,
                            combined=(smart_group_mode == 'combined'))
                    except ValueError as exc:
                        cleanup_uncommitted(self.project, original_batches)
                        QMessageBox.warning(self, 'Invalid chapter labels', str(exc))
                        return
            if needs_review:
                # Resolve [chapter] labels against ORIGINAL, reviewed chapter
                # numbers before we make gaps in the source-page sequence.
                # Then remove unselected pages from the commit candidates only.
                from .import_selection import filter_staged_import
                try:
                    batches, sections_by_file, omitted_batches = filter_staged_import(
                        original_batches, sections_by_file, selected_page_numbers)
                except ValueError as exc:
                    cleanup_uncommitted(self.project, original_batches)
                    QMessageBox.warning(self, 'Invalid page selection', str(exc))
                    return
                added = [page for _name, pages in batches for page in pages]
            if added:
                i = min(position, len(self.project.pages))
                old_pages = list(self.project.pages)
                old_tree = copy.deepcopy(self.project.page_groups)
                old_selected = self.project.selected_page
                # Build the entire hierarchy in a pure-Python planner.
                # No Qt tree or live project data changes until the plan
                # has been validated against every original and new ID.
                ids = [page['id'] for page in added]
                try:
                    new_tree, target_available = plan_import(
                        old_tree, [p['id'] for p in old_pages],
                        [(name, [p['id'] for p in pages])
                         for name, pages in batches],
                        position=i, group_id=group_id,
                        smart=smart_import,
                        single_group_label=group_label,
                        group_mode=smart_group_mode,
                        # Bookmark filtering is independent of whether the
                        # user wants chapter folders created in the navigator.
                        sections_by_file=(sections_by_file if smart_import and
                                          structure_mode != 'none' else
                                          [[] for _ in batches]),
                        strict_target=True,
                        collapse_new_groups=collapse_new_groups)
                    lookup = {p['id']: p for p in old_pages + added}
                    new_pages = [lookup[pid] for pid in flatten(new_tree)]
                except (ValueError, TypeError, KeyError) as exc:
                    cleanup_uncommitted(self.project, original_batches)
                    QMessageBox.warning(
                        self, 'Import organisation failed',
                        f'Pages were not added: {exc}')
                    return
                # strict_target=True rejects missing destinations before commit.
                self._separate_text_commands()
                self._apply_group_snapshot(new_tree, new_pages, ids[0])
                new_pages = list(self.project.pages)
                new_tree = copy.deepcopy(self.project.page_groups)
                self.history.record_applied(CallbackAction(
                    'Smart Import' if smart_import else 'Import Pages',
                    lambda: self._apply_group_snapshot(
                        old_tree, old_pages, old_selected),
                    lambda: self._apply_group_snapshot(
                        new_tree, new_pages, ids[0]),
                    512 + 140 * len(added)))
                self.save()
                # Only after selected pages are part of the notebook can we
                # safely remove excluded assets; some share the same original.
                if omitted_batches:
                    cleanup_uncommitted(self.project, omitted_batches)
                self.readingChanged.emit()
                self.statusMessage.emit(
                    f'Indexed {len(added):,} page(s). '
                    'Pages render as you read.')
            if errors:
                QMessageBox.warning(
                    self, 'Some files could not be imported',
                    '\n\n'.join(errors[:12]))
        start_task(self, worker, done, priority=2)

    def _insert_pages_at(self, index, pages):
        present = {page['id'] for page in self.project.pages}
        inserted = [page for page in pages if page['id'] not in present]
        if not inserted:
            return
        self.project.pages[min(index, len(self.project.pages)):min(index, len(self.project.pages))] = inserted
        self._celebrate_on_next_manual_save = True
        self.load_pages(select_id=inserted[0]['id'])
        self.select_page_id(inserted[0]['id'])
        self.schedule_save()

    def _remove_page_ids(self, ids):
        removed = set(ids)
        first = next((i for i, page in enumerate(self.project.pages) if page['id'] in removed), 0)
        self.project.pages = [page for page in self.project.pages if page['id'] not in removed]
        # Keep annotations by stable ID during the session, for Redo.
        self.project.selected_page = None
        self.load_pages()
        if self.project.pages:
            self.pages_list.setCurrentRow(min(first, len(self.project.pages) - 1))
        else:
            self.select_item(None, None)
        self._celebrate_on_next_manual_save = True
        self.schedule_save()

    def _separate_text_commands(self):
        """Move the cursor transiently to prevent Qt typing from merging
        backwards across a non-text change in the shared undo timeline.
        Neither the document's contents nor the selected reading passage is
        changed; selections are kept untouched.
        """
        editor = self.notes.editor
        saved = editor.textCursor()
        if not saved.hasSelection():
            moved = QTextCursor(saved)
            direction = (QTextCursor.MoveOperation.Left if saved.position() > 0
                         else QTextCursor.MoveOperation.Right)
            if moved.movePosition(direction):
                # setTextCursor scrolls the caret into view. When the user is
                # reading elsewhere, an annotation must not jump the notes.
                bar = editor.verticalScrollBar()
                reading_position = bar.value()
                try:
                    editor.setTextCursor(moved)
                    editor.setTextCursor(saved)
                finally:
                    bar.setValue(max(bar.minimum(),
                                     min(bar.maximum(), reading_position)))

    def add_blank(self, position=None):
        position = position if type(position) is int else self._selected_insertion_index()
        position = max(0, min(position, len(self.project.pages)))
        page = blank_page(self.project)
        self._separate_text_commands()
        self.history.perform(CallbackAction(
            'Add Blank Page',
            lambda pid=page['id']: self._remove_page_ids([pid]),
            lambda pos=position, obj=page: self._insert_pages_at(pos, [obj]),
            estimated_bytes=512))

    def rename_page(self):
        """Open the same inline editor from the context menu or name label."""
        if self.current_page():
            self.page_title.start_edit()

    def _apply_page_title(self, page_id, title):
        page = self.project.page_by_id(page_id)
        if page is None:
            raise ValueError('Cannot rename a page that no longer exists.')
        page['title'] = title
        for row in range(self.pages_list.count()):
            item = self.pages_list.item(row)
            if item.data(Qt.ItemDataRole.UserRole) == page_id:
                item.setText(title)
                item.setToolTip(title)
                item.setData(Qt.ItemDataRole.AccessibleTextRole, title)
                break
        if hasattr(self, 'group_tree'):
            self._refresh_group_tree()
        if self.current_page() and self.current_page()['id'] == page_id:
            self.page_title.setText(title)
        self._celebrate_on_next_manual_save = True
        self.schedule_save()

    def rename_page_to(self, title):
        """One history step, with stable page ID even after reordering."""
        page = self.current_page()
        new = title.strip()
        if page and new and new != page['title']:
            self._separate_text_commands()
            self.history.perform(rename_action('page', page['id'], page['title'], new,
                                               self._apply_page_title))

    def _notes_modified(self):
        """Differentiate meaningful edits from merely changing the reading page."""
        self._celebrate_on_next_manual_save = True
        self.schedule_save()

    def selected_pages(self):
        items = self.pages_list.selectedItems()
        if not items and self.pages_list.currentItem():
            items = [self.pages_list.currentItem()]
        ids = {item.data(Qt.ItemDataRole.UserRole) for item in items}
        return [(i, p) for i, p in enumerate(self.project.pages) if p['id'] in ids]

    def page_context_menu(self, position):
        item = self.pages_list.itemAt(position)
        if item and not item.isSelected():
            self.pages_list.clearSelection()
            self.pages_list.setCurrentItem(item)
        menu = QMenu(self.pages_list)
        if item is not None:
            clicked_id = item.data(Qt.ItemDataRole.UserRole)
            completed = clicked_id in self.project.read_page_ids
            menu.addAction(
                'Mark as unread' if completed else 'Mark as read',
                lambda _=False, pid=clicked_id, value=not completed:
                self._toggle_read_status('page', pid, value))
            menu.addSeparator()
        if item is not None:
            self._reading_page_menu(menu, clicked_id)
        link = menu.addAction(f'↗ Link page in notes  ·  {docs_shortcut("page_link")}')
        link.setEnabled(self.current_page() is not None)
        link.triggered.connect(self.link_current_page)
        menu.addSeparator()
        delete = menu.addAction('Remove selected page(s)  ·  Delete')
        delete.setEnabled(bool(self.selected_pages()))
        delete.triggered.connect(self.remove_page)
        restore = menu.addAction(f'Undo  ·  {PRIMARY}Z')
        restore.setEnabled(self.history.can_undo)
        restore.triggered.connect(self.undo_remove_pages)
        redo = menu.addAction(f'Redo  ·  {PRIMARY}⇧Z')
        redo.setEnabled(self.history.can_redo)
        redo.triggered.connect(self.redo_annotation)
        menu.addSeparator()
        menu.addSeparator()
        menu.addAction(f'Select all pages  ·  {PRIMARY}A', self.pages_list.selectAll)
        menu.addAction('Import File after selection…', lambda: self.choose_files(self._selected_insertion_index()))
        menu.addAction('Add Blank Page after selection', self.add_blank)
        menu.exec(self.pages_list.mapToGlobal(position))

    def remove_page_ids_confirmed(self, ids):
        """Context-menu removal targets the clicked page ID, not preview focus."""
        original = {p['id'] for p in self.project.pages}
        ids = [pid for pid in ids if pid in original]
        if not ids:
            return
        if QMessageBox.question(
                self, 'Remove page',
                'Remove this page from the notebook? You can undo this.',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        before_pages = list(self.project.pages)
        before_tree = copy.deepcopy(self.project.page_groups)
        selected = self.project.selected_page
        remaining = [p for p in before_pages if p['id'] not in set(ids)]
        after_tree = reconcile_group_tree(before_tree, [p['id'] for p in remaining])
        self._separate_text_commands()
        self.history.perform(CallbackAction(
            'Remove Page',
            lambda: self._apply_group_snapshot(before_tree, before_pages, selected),
            lambda: self._apply_group_snapshot(after_tree, remaining, selected),
            512 + 140 * len(ids)))
        self._update_page_undo_availability()

    def remove_page(self):
        selected = self.selected_pages()
        if not selected:
            return
        count = len(selected)
        label = 'page' if count == 1 else 'pages'
        answer = QMessageBox.question(self, 'Remove pages',
                    f'Remove {count:,} selected {label}? This can be undone.',
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        # Save the exact hierarchy as well as the page objects.
        # Undo must not silently turn previously grouped pages into root
        # pages after a deletion from the old thumbnail view.
        before_pages = list(self.project.pages)
        before_tree = copy.deepcopy(self.project.page_groups)
        selected_id = self.project.selected_page
        ids = [page['id'] for _index, page in selected]
        remaining = [p for p in before_pages if p['id'] not in ids]
        after_tree = reconcile_group_tree(
            before_tree, [p['id'] for p in remaining])
        self._separate_text_commands()
        self.history.perform(CallbackAction(
            'Remove Pages',
            lambda: self._apply_group_snapshot(
                before_tree, before_pages, selected_id),
            lambda: self._apply_group_snapshot(
                after_tree, remaining, selected_id),
            512 + 140 * len(ids)))
        self._update_page_undo_availability()

    def undo_remove_pages(self):
        if self.history.can_undo:
            self.history.undo()
        self._update_page_undo_availability()

    def _update_page_undo_availability(self):
        available = self.history.can_undo
        if hasattr(self, '_nav_undo_action'):
            self._nav_undo_action.setEnabled(available)
            label = self.history.next_undo_label or 'Edit'
            self._nav_undo_action.setText(f'Undo {label} · {PRIMARY}Z')
        if hasattr(self, '_page_undo_button'):
            self._page_undo_button.setEnabled(available)

    def describe_link(self, link: str):
        if link.startswith(('sumi://page/', 'yomu://page/')):
            page = self.project.page_by_id(link.rsplit('/', 1)[-1])
            if page:
                index = next((i for i, item in enumerate(self.project.pages)
                              if item['id'] == page['id']), -1)
                return f'↗ Page {index+1:,}: {page["title"]}'
            return '↗ This page has been removed.'
        return link

    def _current_note_page(self):
        return next((page for page in self.project.note_pages
                     if page['id'] == self.project.active_note_id),
                    self.project.note_pages[0])

    def _setup_notes_page_navigation(self):
        """Add a tiny navigator above the existing font toolbar.

        It is per-tab, not per-PDF-page. The original NotesEditor and all its
        formatting/link actions remain in use for whichever document is active.
        """
        row = QHBoxLayout()
        row.setContentsMargins(3, 1, 3, 5)
        row.setSpacing(4)
        caption = QLabel('Notes')
        caption.setToolTip('Independent rich-text note pages in this tab')
        row.addWidget(caption)
        self.note_previous = QToolButton()
        self.note_previous.setText('‹')
        self.note_previous.setFixedSize(22, 23)
        self.note_previous.setToolTip('Previous notes page')
        self.note_previous.clicked.connect(lambda: self.cycle_note_page(-1))
        row.addWidget(self.note_previous)
        self.note_page_select = QComboBox()
        self.note_page_select.setMinimumWidth(60)
        self.note_page_select.setSizePolicy(QSizePolicy.Policy.Expanding,
                                            QSizePolicy.Policy.Fixed)
        self.note_page_select.setToolTip('Choose a notes page in this tab')
        self.note_page_select.currentIndexChanged.connect(self._on_note_page_combo)
        row.addWidget(self.note_page_select, 1)
        self.note_next = QToolButton()
        self.note_next.setText('›')
        self.note_next.setFixedSize(22, 23)
        self.note_next.setToolTip('Next notes page')
        self.note_next.clicked.connect(lambda: self.cycle_note_page(1))
        row.addWidget(self.note_next)
        for symbol, tip, handler in (
                ('+', 'Add a new notes page', self.add_note_page),
                ('✎', 'Rename this notes page', self.rename_note_page),
                ('−', 'Remove this notes page (its content can be restored with Undo)',
                 self.remove_note_page)):
            button = QToolButton()
            button.setText(symbol)
            button.setFixedSize(22, 23)
            button.setToolTip(tip)
            button.clicked.connect(handler)
            row.addWidget(button)
            if symbol == '−':
                self.note_remove_button = button
        self.notes.layout().insertLayout(1, row)
        self._refresh_note_page_selector()

    def _refresh_note_page_selector(self):
        from PySide6.QtCore import QSignalBlocker
        with QSignalBlocker(self.note_page_select):
            self.note_page_select.clear()
            for entry in self.project.note_pages:
                self.note_page_select.addItem(entry['title'], entry['id'])
            index = self.note_page_select.findData(self.project.active_note_id)
            self.note_page_select.setCurrentIndex(max(0, index))
        count = len(self.project.note_pages)
        self.note_previous.setEnabled(count > 1)
        self.note_next.setEnabled(count > 1)
        self.note_remove_button.setEnabled(count > 1)

    def _on_note_page_combo(self, index):
        if index >= 0 and not self._changing_note_page:
            self.select_note_page(self.note_page_select.itemData(index))

    def cycle_note_page(self, step):
        pages = self.project.note_pages
        index = next((i for i, p in enumerate(pages)
                      if p['id'] == self.project.active_note_id), 0)
        self.select_note_page(pages[(index + step) % len(pages)]['id'])

    def _save_note_page_view(self):
        entry = self._current_note_page()
        entry['html'] = self.notes.html()
        entry['scroll'] = self.notes.editor.verticalScrollBar().value()
        entry['page_setup'] = (self.notes.page_setup.as_dict()
                              if self.notes.page_setup is not None else None)
        if entry is self.project.note_pages[0]:
            # Keep the old single-notes API synchronised even BEFORE autosave.
            self.project.notes_html = entry['html']
            self.project.notes_scroll = entry['scroll']
            self.project.notes_page_setup = copy.deepcopy(entry['page_setup'])

    def select_note_page(self, identifier):
        """Swap QTextDocuments, never flatten or discard formatting.

        Qt keeps Undo for every document in the current tab. Document state
        is saved to its entry when leaving; the editor viewport belongs only
        to the active entry. A page link still resolves by its PDF page ID.
        """
        if identifier == self.project.active_note_id:
            return
        entry = next((p for p in self.project.note_pages
                      if p['id'] == identifier), None)
        if entry is None:
            return
        self._changing_note_page = True
        self._splitter_scroll_anchor = None
        self._scroll_idle_timer.stop()
        self._restoring_notes_scroll = True
        try:
            self._save_note_page_view()
            current_doc = self.notes.editor.document()
            # QTextEdit may delete a document it owns when setDocument()
            # replaces it. Reparent first so this tab owns ALL note histories.
            current_doc.setParent(self)
            self._note_documents[self.project.active_note_id] = current_doc
            document = self._note_documents.get(identifier)
            new_doc = document is None
            if new_doc:
                document = QTextDocument(self)
                # Empty/new pages must inherit the same default typography
                # and document margins as the original notes page.
                document.setDefaultFont(current_doc.defaultFont())
                document.setDocumentMargin(current_doc.documentMargin())
                self._note_documents[identifier] = document
                self._note_document_ids[id(document)] = identifier
            editor = self.notes.editor
            notes_were_blocked = self.notes.blockSignals(True)
            editor.blockSignals(True)
            try:
                editor.setDocument(document)
                self.notes._view_zoom_overlay.setDocument(document)
                setup = (NotesPageSetup.from_dict(entry['page_setup'])
                         if entry['page_setup'] is not None else None)
                if new_doc:
                    self.notes.set_html(entry['html'])
                    self.notes.set_page_setup(setup, from_load=True)
                    document.clearUndoRedoStacks()
                    document.contentsChange.connect(
                        self.notes._remember_edit_from_contents_change)
                    callback = getattr(self, 'on_note_document', None)
                    if callback:
                        callback(identifier, document)
                else:
                    self.notes.restore_page_setup_metadata(
                        setup, update_frame=False)
                self.notes._last_edit_cursor = None
            finally:
                editor.blockSignals(False)
                self.notes.blockSignals(notes_were_blocked)
            self.project.active_note_id = identifier
            self._notes_scroll_restored = False
            self._refresh_note_page_selector()
            self.notes.update_font_toolbar(editor.currentCharFormat())
            QTimer.singleShot(0, self._restore_notes_scroll)
            self.schedule_save()
        finally:
            self._changing_note_page = False

    def _insert_note_page(self, entry, index, *, select=True):
        if not any(p['id'] == entry['id'] for p in self.project.note_pages):
            self._save_note_page_view()
            self.project.note_pages.insert(min(index, len(self.project.note_pages)),
                                           copy.deepcopy(entry))
        self._refresh_note_page_selector()
        if select:
            self.select_note_page(entry['id'])
        self.schedule_save()

    def _delete_note_page(self, identifier):
        if len(self.project.note_pages) <= 1:
            return
        if identifier == self.project.active_note_id:
            # Select another EXISTING entry before removing this one, so the
            # outgoing HTML can never be accidentally written into Page 1.
            other_id = next(p['id'] for p in self.project.note_pages
                            if p['id'] != identifier)
            self.select_note_page(other_id)
        self.project.note_pages = [p for p in self.project.note_pages
                                   if p['id'] != identifier]
        first = self.project.note_pages[0]
        self.project.notes_html = first['html']
        self.project.notes_scroll = first['scroll']
        self.project.notes_page_setup = copy.deepcopy(first['page_setup'])
        self._refresh_note_page_selector()
        self.schedule_save()

    def add_note_page(self):
        if len(self.project.note_pages) >= 128:
            QMessageBox.information(self, 'Notes limit',
                                    'Each tab supports up to 128 notes pages.')
            return
        self._separate_text_commands()
        entry = {'id': short_id(), 'title': f'Notes {len(self.project.note_pages) + 1}',
                 'html': '', 'scroll': 0,
                 'page_setup': copy.deepcopy(self._current_note_page()['page_setup'])}
        index = len(self.project.note_pages)
        old_id = self.project.active_note_id
        self.history.perform(CallbackAction(
            'Add Notes Page',
            lambda: (self._delete_note_page(entry['id']),
                     self.select_note_page(old_id)),
            lambda: self._insert_note_page(entry, index)))

    def rename_note_page(self):
        entry = self._current_note_page()
        name, ok = QInputDialog.getText(
            self, 'Rename notes page', 'Notes page name:', text=entry['title'])
        if not ok or not name.strip() or name.strip() == entry['title']:
            return
        if len(name.strip()) > 100:
            QMessageBox.warning(self, 'Name too long', 'Use 100 characters or fewer.')
            return
        page_id, before, after = entry['id'], entry['title'], name.strip()
        def apply(label):
            page = next((p for p in self.project.note_pages
                         if p['id'] == page_id), None)
            if page is not None:
                page['title'] = label
                self._refresh_note_page_selector()
                self.schedule_save()
        self.history.perform(CallbackAction(
            'Rename Notes Page', lambda: apply(before), lambda: apply(after)))

    def remove_note_page(self):
        if len(self.project.note_pages) < 2:
            return
        current = self._current_note_page()
        if QMessageBox.question(
                self, 'Remove notes page',
                f'Remove “{current["title"]}”? Its content can be restored with Undo.',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        self._save_note_page_view()
        snapshot = copy.deepcopy(current)
        index = self.project.note_pages.index(current)
        self._separate_text_commands()
        self.history.perform(CallbackAction(
            'Remove Notes Page',
            lambda: self._insert_note_page(snapshot, index),
            lambda: self._delete_note_page(snapshot['id'])))

    def _set_note_page_setup(self, identifier, value):
        entry = next((p for p in self.project.note_pages if p['id'] == identifier), None)
        if entry is not None:
            entry['page_setup'] = copy.deepcopy(value)
            if entry is self.project.note_pages[0]:
                self.project.notes_page_setup = copy.deepcopy(value)

    def show_notes_page_setup(self):
        """Change page defaults and document text in one Undoable operation.

        The visible paragraph formats live inside Qt's document.
        The selected defaults also live in the notebook's JSON data.
        We must restore BOTH when the user presses Undo or Redo.
        """
        current = self.notes.page_setup or NotesPageSetup(
            base_font_pt=self.notes._base_document_point_size())
        dialog = NotesPageSetupDialog(current, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        new_setup = dialog.result_setup()
        before = copy.deepcopy(self._current_note_page()['page_setup'])
        after = new_setup.as_dict()
        if before == after:
            return

        # MainWindow listens for Qt's single new native Undo command.
        # While this flag is set, it labels that command Page Setup and
        # attaches the old/new saved settings to the same history entry.
        self._pending_page_setup_history = (before, after)
        self._page_setup_history_recorded = False
        try:
            self.notes.set_page_setup(new_setup)
            self._set_note_page_setup(self.project.active_note_id, after)
        finally:
            self._pending_page_setup_history = None

        if not self._page_setup_history_recorded:
            # A change affecting metadata only may add no Qt text command.
            # It still needs one shared Undo entry for the notebook data.
            def restore(metadata):
                self.notes.restore_page_setup_metadata(
                    NotesPageSetup.from_dict(metadata)
                    if metadata is not None else None)
                self._set_note_page_setup(self.project.active_note_id, metadata)
                self.schedule_save()

            self.history.record_applied(CallbackAction(
                'Notes Page Setup',
                undo_callback=lambda: restore(before),
                redo_callback=lambda: restore(after)))
        self.schedule_save()
        self.statusMessage.emit('Notes page setup updated for this project.')

    def use_default_font(self, name):
        self.settings.setValue('defaultFont', name)
        self.statusMessage.emit(f'“{name}” will be used for new notes. Existing notes are unchanged.')

    def _set_pen_size(self, value):
        width = value/2.0
        self.canvas.tool_styles['pen']['width'] = width/1000.0
        self.pen_size_label.setText(f'{width:g}pt')
        self.settings.setValue('annotationPenWidth', width)

    def _update_ocr_region_count(self, count):
        if not hasattr(self, 'ocr_count'):
            return
        self.ocr_count.setText(f'{count} region' + ('' if count == 1 else 's'))
        enabled = not self._ocr_running
        self.ocr_undo_button.setEnabled(bool(count) and enabled)
        self.ocr_clear_button.setEnabled(bool(count) and enabled)
        self.ocr_recognise_button.setEnabled(bool(count) and enabled)

    def _load_ocr_languages(self):
        """Tesseract discovery happens off the GUI thread."""
        def worker():
            exe = find_tesseract()
            return installed_languages(exe) if exe else []
        def done(languages, error):
            if self._closed or not self.ocr_bar.isVisible():
                return
            if error or not languages:
                self.ocr_status.setText('OCR engine unavailable. Packaged builds include it; source runs need Tesseract installed.')
                return
            labels = {'eng':'English', 'fra':'French', 'deu':'German', 'spa':'Spanish',
                      'ita':'Italian', 'por':'Portuguese', 'nld':'Dutch', 'pol':'Polish',
                      'swe':'Swedish', 'dan':'Danish', 'nor':'Norwegian', 'fin':'Finnish'}
            saved = self.settings.value('ocrLanguage', 'eng')
            self.ocr_language.blockSignals(True)
            self.ocr_language.clear()
            for code in languages:
                if code in labels:
                    self.ocr_language.addItem(labels[code], code)
            index = self.ocr_language.findData(saved)
            self.ocr_language.setCurrentIndex(max(0, index))
            self.ocr_language.blockSignals(False)
            if self.ocr_language.count() == 0:
                self.ocr_status.setText('No supported Latin-script Tesseract language pack found.')
        start_task(self, worker, done)

    def enter_ocr_mode(self):
        page = self.current_page()
        if not page or page.get('kind') not in ('image', 'pdf'):
            QMessageBox.information(self, 'OCR selection', 'First choose an imported PDF or image page.')
            return
        if self._ocr_running:
            return
        self.set_annotation_mode('ocr')
        self.ocr_bar.show()
        self.ocr_status.setText('Drag rectangles over text · scroll or zoom to continue · Esc to exit')
        self.ocr_review_button.setEnabled(bool(self._ocr_last_text))
        self._update_ocr_region_count(0)
        self._load_ocr_languages()
        self.canvas.setFocus(Qt.FocusReason.OtherFocusReason)
        self.statusMessage.emit('OCR: draw one or more regions. Scrolling keeps each rectangle on the page.')

    def leave_ocr_mode(self, set_pan=True, cancel_running=True):
        if cancel_running and self._ocr_cancel_event is not None:
            self._ocr_cancel_event.set()
        self.ocr_bar.hide()
        if set_pan and self.canvas.annotation_tool == 'ocr':
            self.set_annotation_mode('pan')
        self.canvas.setEnabled(True)

    def _on_ocr_progress(self, index, total):
        if self._ocr_running and self._ocr_cancel_event is not None and not self._ocr_cancel_event.is_set():
            self.ocr_status.setText(f'Recognising region {index} of {total}…')

    def recognise_ocr_selection(self):
        if self._ocr_running:
            return
        regions = self.canvas.ocr_regions()
        page = self.current_page()
        if not page or not regions:
            return
        if not find_tesseract():
            QMessageBox.warning(self, 'Tesseract required',
                'The offline OCR engine could not be found. If you installed Yomu Note, please reinstall it.\n'
                'If running from Python source, install Tesseract on this computer.')
            return
        page_snapshot = dict(page)
        page_id = page_snapshot['id']
        dpi = int(self.ocr_dpi.currentData())
        language = self.ocr_language.currentData() or 'eng'
        self.settings.setValue('ocrLanguage', language)
        join_lines = self.ocr_join_lines.isChecked()
        event = threading.Event()
        self._ocr_cancel_event = event
        self._ocr_running = True
        self._ocr_entry_action.setEnabled(False)
        self.canvas.setEnabled(False)
        self.ocr_progress.show()
        self._update_ocr_region_count(len(regions))
        self.ocr_whole_button.setEnabled(False)
        self.ocr_status.setText(f'Recognising {len(regions)} region(s)…')
        def worker():
            return recognise_regions(self.project, page_snapshot, regions,
                dpi=dpi, language=language, join_lines=join_lines,
                cancel=event, progress=lambda i, n: self.ocrProgress.emit(i, n))
        def done(result, error):
            self._ocr_running = False
            self._ocr_cancel_event = None
            self._ocr_entry_action.setEnabled(True)
            self.canvas.setEnabled(True)
            self.ocr_progress.hide()
            self.ocr_whole_button.setEnabled(True)
            self._update_ocr_region_count(len(self.canvas.ocr_regions()))
            # The result belongs to the page where OCR began.
            # Switching pages or tabs must not throw that text away.
            if self._closed or event.is_set():
                return
            still_showing_source = bool(
                self._active and self.current_page()
                and self.current_page()['id'] == page_id
            )
            if error:
                self.ocr_status.setText('OCR failed — selections were preserved.')
                logger.warning('OCR task failed: %s', error)
                if still_showing_source:
                    QMessageBox.warning(self, 'OCR could not finish', str(error))
                return
            if not result or not result.strip():
                self.ocr_status.setText(
                    'No characters recognised. Try a wider selection or higher DPI.')
                return
            self._ocr_results_by_page[page_id] = result
            self._ocr_last_page_id = page_id
            self._ocr_last_text = result
            self.ocr_review_button.setEnabled(True)
            if not still_showing_source:
                # Don't overwrite a clipboard the user changed after
                # moving away. Reopen OCR mode to review this result.
                self.ocr_status.setText('OCR finished on another page · Review text')
                self.statusMessage.emit(
                    'OCR result saved in this tab. Open OCR and choose Review.')
                return
            QApplication.clipboard().setText(result)
            self.ocr_status.setText('Text copied! Review to correct any recognition errors.')
            self.statusMessage.emit('OCR text copied to clipboard.')
            self.show_ocr_review()
        start_task(self, worker, done, priority=2)

    def show_ocr_review(self):
        if not self._ocr_last_text:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle('Review recognised text · copied to clipboard')
        dialog.resize(610, 440)
        layout = QVBoxLayout(dialog)
        info = QLabel('Check punctuation and quotations against the original. Editing here does not change your notes.')
        info.setWordWrap(True)
        layout.addWidget(info)
        editor = QPlainTextEdit()
        editor.setObjectName('ocrReviewText')  # Scoped, theme-aware OCR editor palette.
        editor.setPlainText(self._ocr_last_text)
        editor.setToolTip('Edit any recognition errors, then copy the corrected text')
        layout.addWidget(editor, 1)
        buttons = QHBoxLayout()
        copy = QPushButton('Copy edited text')
        copy.setObjectName('primary')
        def copy_text():
            self._ocr_last_text = editor.toPlainText()
            if self._ocr_last_page_id:
                self._ocr_results_by_page[self._ocr_last_page_id] = self._ocr_last_text
            QApplication.clipboard().setText(self._ocr_last_text)
            self.statusMessage.emit('Corrected OCR text copied to clipboard.')
            dialog.accept()
        copy.clicked.connect(copy_text)
        buttons.addWidget(copy)
        buttons.addStretch(1)
        close = QPushButton('Close')
        close.clicked.connect(dialog.reject)
        buttons.addWidget(close)
        layout.addLayout(buttons)
        dialog.exec()

    def set_annotation_mode(self, tool):
        if self.canvas.annotation_tool == 'ocr' and tool != 'ocr':
            self.leave_ocr_mode(set_pan=False)
        self.canvas.set_annotation_tool(tool)
        self.pen_size_widget.setVisible(tool == 'pen')
        self._update_annotation_toolbar_layout()
        for name, button in self.annotation_mode_buttons.items():
            button.setChecked(name == tool)
        for group, members in self._annotation_groups.items():
            self._annotation_group_buttons[group].setChecked(tool in members)
            if tool in members:
                self._annotation_last_tool[group] = tool
        self._annotation_selection_changed(-1, None)
        self.statusMessage.emit({
            'pen': 'Pen: drag to draw a vector stroke.',
            'marker': 'Marker: draw with translucent Multiply blending.',
            'line': 'Line: drag to draw · Shift snaps to 45°.',
            'arrow': 'Arrow: drag to draw · Shift snaps to 45°.',
            'rectangle': 'Rectangle: drag to draw · Shift makes a square.',
            'ellipse': 'Ellipse: drag to draw · Shift makes a circle.',
            'select': 'Select: click a mark to edit colour/opacity/thickness; drag or resize.',
            'eraser': 'Eraser: hold the left mouse button and sweep across annotations; one Undo restores the gesture.',
            'pan': 'Pan: drag to move the page.',
            'ocr': 'OCR: draw one or more rectangles, scroll to continue, then Recognise.',
            'highlight': 'Rectangle highlighter: drag across a passage · Multiply.',
            'highlight_line': 'Straight-line highlighter: drag a flat-ended line · Shift snaps.',
        }[tool])

    def toggle_highlighter(self, checked=False):
        # Kept for callers using the existing public highlighter toggle.
        self.set_annotation_mode('highlight' if checked else 'pan')

    def _effective_palette_target(self):
        """Page highlighters share one ink, not separate outline/fill colours."""
        selected = self._appearance_selection_mark
        if selected is not None and selected.get('kind') in ('highlight', 'highlight_line'):
            return 'highlight'
        if selected is None and self.canvas.annotation_tool in ('highlight', 'highlight_line'):
            return 'highlight'
        return self._palette_channel

    def _select_palette_channel(self, channel):
        self._palette_channel = 'fill' if channel == 'fill' else 'stroke'
        self.pen_colour.set_active(self._palette_channel == 'stroke')
        self.fill_colour.set_active(self._palette_channel == 'fill')

    def _swatch_menu(self, button, point, target):
        """No Stroke/No Fill remain discoverable without permanent checkboxes."""
        self._select_palette_channel(target)
        menu = QMenu(button)
        selected = self._appearance_selection_mark
        active_shape = selected.get('shape') if selected and selected.get('kind') == 'shape' else self.canvas.annotation_tool
        allowed = (self.shape_fill_checkbox.isEnabled() if target == 'fill'
                   else self.stroke_enabled_checkbox.isEnabled() and active_shape in ('rectangle', 'ellipse'))
        if allowed:
            checkbox = self.shape_fill_checkbox if target == 'fill' else self.stroke_enabled_checkbox
            none_action = menu.addAction('No fill' if target == 'fill' else 'No stroke',
                           lambda: checkbox.setChecked(False))
            # Avoid an invisible annotation when both stroke and fill are None.
            if target == 'stroke' and not self.shape_fill_checkbox.isChecked():
                none_action.setEnabled(False)
            menu.addAction('Enable fill' if target == 'fill' else 'Enable stroke',
                           lambda: checkbox.setChecked(True))
            menu.addSeparator()
        menu.addAction('Choose colour…', lambda: self._pick_appearance_color(target))
        menu.exec(button.mapToGlobal(point))

    def _swap_annotation_colours(self):
        if not self.fill_colour.isEnabled():
            return
        stroke, fill = self.pen_colour.colour.name(), self.fill_colour.colour.name()
        self.pen_colour.set_colour(fill)
        self.fill_colour.set_colour(stroke)
        self._appearance_changed()

    def _annotation_selection_changed(self, index, mark):
        """Show selected mark's true properties; no changes to tool defaults."""
        previous = getattr(self, '_appearance_selection_mark', None)
        same_selection = (previous is not None and mark is not None and
                          getattr(self, '_appearance_selection_index', -1) == index and
                          previous.get('id') == mark.get('id') and
                          previous.get('kind') == mark.get('kind'))
        if not same_selection:
            self._quick_edit_custom_position = False
            self._quick_edit_defaults_mode = False
            if mark is not None:
                self._quick_edit_dismissed = False
        self._appearance_selection_index = index if mark is not None else -1
        self._appearance_selection_mark = copy.deepcopy(mark) if mark is not None else None
        tool = self.canvas.annotation_tool
        style = mark if mark is not None else self.canvas._tool_style(tool)
        kind = mark.get('kind', tool) if mark is not None else tool
        is_highlight = kind in ('highlight', 'highlight_line')
        supports_fill = ((kind == 'shape' and mark.get('shape') in ('rectangle', 'ellipse'))
                         if mark is not None else tool in ('rectangle', 'ellipse'))
        has_width = kind != 'highlight'
        has_stroke = not is_highlight and kind not in ('pan', 'select', 'eraser')
        self._syncing_appearance = True
        try:
            self.pen_colour.set_colour(style.get('color', '#d74685'))
            self.fill_colour.set_colour(style.get('fill') or style.get('color', '#d74685'))
            self.stroke_enabled_checkbox.setChecked(style.get('stroke_enabled', True))
            default_opacity = (round(100*92/255) if kind == 'highlight' else
                               round(100*135/255) if kind == 'stroke' and style.get('blend') == 'multiply' else 100)
            self.stroke_opacity_control.setValue(round(style.get('opacity', default_opacity)))
            self.stroke_width_control.setValue(max(.5, min(100, style.get('width', .003)*1000)))
            self.shape_fill_checkbox.setChecked(style.get('fill') is not None)
            fill_default = round(100 * 55/255) if mark is not None else 30
            self.fill_opacity_control.setValue(round(style.get('fill_opacity', fill_default)))
            self.shape_fill_checkbox.setEnabled(supports_fill)
            self.fill_paint_row.setVisible(supports_fill)
            self.swap_colours_button.setVisible(supports_fill)
            self._opacity_rows['fill'].setVisible(supports_fill)
            self._opacity_labels['stroke'].setText(
                'Highlight opacity' if is_highlight else 'Stroke opacity')
            self.stroke_colour_label.setText('Highlight' if is_highlight else 'Stroke')
            self.fill_colour.setEnabled(supports_fill)
            self.fill_opacity_control.setEnabled(supports_fill)
            self.stroke_enabled_checkbox.setEnabled(has_stroke and kind == 'shape')
            self.stroke_width_control.setEnabled(has_width and kind not in ('pan', 'select', 'eraser'))
            is_arrow = (mark.get('shape') == 'arrow' if mark is not None
                        else tool == 'arrow')
            self.arrow_size_row.setVisible(is_arrow)
            if is_arrow:
                for key, slider in self.arrow_head_sliders.items():
                    with QSignalBlocker(slider):
                        slider.setValue(round(1000*style.get(key, .018 if key == 'head_width' else .025)))
            self.quick_palette.setEnabled(mark is not None or tool not in ('pan', 'select', 'eraser'))
            self.stroke_opacity_control.setEnabled(kind not in ('pan', 'select', 'eraser'))
            self.pen_colour.setEnabled(kind not in ('pan', 'select', 'eraser'))
            self.pen_colour.set_paint_enabled(not
                (kind == 'shape' and not self.stroke_enabled_checkbox.isChecked()))
            self.fill_colour.set_paint_enabled(self.shape_fill_checkbox.isChecked())
            # Selecting an object starts with Stroke/Highlight; switching the
            # active swatch affects only the quick palette's destination.
            if not same_selection or not supports_fill:
                self._palette_channel = 'stroke'
            self._select_palette_channel(self._palette_channel)
        finally:
            self._syncing_appearance = False
        self._displayed_appearance = self._appearance_values()
        if hasattr(self, 'annotation_quick_edit'):
            self._sync_annotation_quick_edit(mark)

    def _create_annotation_quick_edit(self):
        """One reusable themed appearance editor, shared by Colour and Select."""
        # Separate opaque backdrop and input surface: painting the background
        # never re-renders the buttons, swatches or sliders.
        self._quick_edit_backdrop = AnnotationQuickEditBackdrop(self.canvas.viewport())
        self._quick_edit_backdrop.hide()
        panel = QFrame(self.canvas.viewport())
        panel.setObjectName('annotationQuickEdit')
        panel.setFrameShape(QFrame.Shape.NoFrame)
        panel.setAutoFillBackground(False)
        panel.setMinimumWidth(290)
        panel.setMaximumWidth(620)
        self._quick_edit_user_width = 490
        self._quick_edit_resize_start = None
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(6)
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        self.quick_drag_handle = QLabel('⠿', panel)
        self.quick_drag_handle.setFixedWidth(18)
        self.quick_drag_handle.setCursor(Qt.CursorShape.OpenHandCursor)
        self.quick_drag_handle.setToolTip('Drag to move Quick Edit')
        self.quick_drag_handle.installEventFilter(self)
        title_row.addWidget(self.quick_drag_handle)
        self.quick_title = QLabel('Appearance', panel)
        self.quick_title.setCursor(Qt.CursorShape.OpenHandCursor)
        self.quick_title.setToolTip('Drag to move Quick Edit')
        self.quick_title.installEventFilter(self)
        title_row.addWidget(self.quick_title, 1)
        close_button = QToolButton(panel)
        close_button.setText('×')
        close_button.setToolTip('Close Quick Edit (annotation remains selected)')
        close_button.clicked.connect(self._dismiss_annotation_quick_edit)
        title_row.addWidget(close_button)
        layout.addLayout(title_row)
        layout.addWidget(self.appearance_panel)
        resize_row = QHBoxLayout()
        resize_row.setContentsMargins(0, 0, 0, 0)
        resize_row.addStretch(1)
        self.quick_resize_handle = QLabel('◢', panel)
        self.quick_resize_handle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.quick_resize_handle.setFixedSize(21, 19)
        self.quick_resize_handle.setToolTip('Drag to resize Quick Edit')
        self.quick_resize_handle.setCursor(Qt.CursorShape.SizeFDiagCursor)
        self.quick_resize_handle.installEventFilter(self)
        resize_row.addWidget(self.quick_resize_handle)
        layout.addLayout(resize_row)
        self.annotation_quick_edit = panel
        panel.installEventFilter(self)  # synchronise the sibling on move/resize/show/hide
        self._quick_edit_dismissed = False
        self._quick_edit_defaults_mode = False
        self._quick_edit_custom_position = False
        self._quick_edit_drag_start = None
        self._quick_gesture_active = False
        panel.hide()
        self._theme_annotation_quick_edit(THEMES['washi'])
        self._theme_annotation_toolbar(THEMES['washi'])
        self.canvas.horizontalScrollBar().valueChanged.connect(self._position_annotation_quick_edit)
        self.canvas.verticalScrollBar().valueChanged.connect(self._position_annotation_quick_edit)
        self.canvas.zoomChanged.connect(self._position_annotation_quick_edit)
        self.canvas.editingGesture.connect(self._annotation_editing_gesture)
        self.canvas.viewport().installEventFilter(self)

    def _update_annotation_toolbar_layout(self):
        """One-row toolbar: labelled, icon-only, then compact, then overflow.

        Change size hints rather than scaling bitmaps; relative tool order and
        menu contents are unchanged. Only the footer reacts to preview width.
        """
        buttons = getattr(self, '_annotation_footer_buttons', None)
        if not buttons:
            return
        pen_active = (getattr(self, 'pen_size_widget', None) is not None and
                      not self.pen_size_widget.isHidden())
        available = self.canvas.viewport().width() - (96 if pen_active else 0)
        self.annotation_footer.layout().setSpacing(
            2 if pen_active and self.canvas.viewport().width() < 360 else 5)
        if available >= 700:
            mode = 'labels'
        elif available >= 390:
            mode = 'icons'
        else:
            mode = 'small'
        hidden = set()
        if available < 310:
            hidden.update((self._annotation_clear_button, self.appearance_button,
                           self._annotation_link_button))
        if available < 250:
            hidden.add(self.annotation_mode_buttons['eraser'])
        for button in buttons:
            if button is self._annotation_overflow:
                button.setVisible(bool(hidden))
            else:
                button.setVisible(button not in hidden)
            label = self._annotation_label_text.get(button, '')
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon
                                      if mode == 'labels' and label else
                                      Qt.ToolButtonStyle.ToolButtonIconOnly)
            if mode != 'labels':
                button.setText('' if button is not self.highlight_button else '')
            else:
                button.setText(label if label else '')
            size = (21 if button is self.annotation_mode_buttons.get('select') else 18)
            if mode == 'small':
                size = 16 if button is self.annotation_mode_buttons.get('select') else 14
            button.setIconSize(QSize(size, size))
            button.setFixedHeight(39 if mode == 'labels' else 33 if mode == 'icons' else 29)
            if mode == 'labels':
                button.setMinimumWidth(54 if label else 39)
                button.setMaximumWidth(205 if button is self.highlight_button else 130)
            else:
                very_compact_pen = pen_active and self.canvas.viewport().width() < 360
                button.setMinimumWidth(32 if mode == 'icons' else 22 if very_compact_pen else 26)
                button.setMaximumWidth(42 if mode == 'icons' else 26 if very_compact_pen else 30)
            button.setStyleSheet('QToolButton#annotationToolbarButton {'
                'padding: 4px 6px; margin: 0;}' if mode == 'labels' else
                'QToolButton#annotationToolbarButton {padding: 2px; margin: 0;}')
        # Shrink only the contextual slider at narrow widths, never the text
        # editor or the PDF view. The normal tools keep their relative order.
        if hasattr(self, 'pen_size_slider'):
            narrow = self.canvas.viewport().width() < 430
            self.pen_size_slider.setMaximumWidth(52 if narrow else 82)
            self.pen_size_label.setMinimumWidth(0)
        # Preserve highlight menu arrow in compact mode; Qt owns its hit area.
        # Hide the little colour dot when the compact menu arrow needs its space.
        self.highlight_button.setProperty('annotationCompact', mode != 'labels')
        self.highlight_button.update()
        self.highlight_button.setMinimumSize(32 if mode == 'icons' else 26, 29)
        self.highlight_button.setMaximumSize(205 if mode == 'labels' else 42 if mode == 'icons' else 30,
                                             39 if mode == 'labels' else 33 if mode == 'icons' else 29)
        # On extremely narrow screens, hide the trailing tools behind an
        # overflow menu; buttons never clip or wrap to a second line.
        self.annotation_footer.updateGeometry()

    def _theme_annotation_toolbar(self, colours):
        """Saturated theme accents with contrast correction for both themes.

        No global icon or text styling is changed: this targets the annotation
        tools only, using the existing SVG icons at native DPI.
        """
        bg = QColor(colours['btn'])
        active_bg = QColor(colours['btn2'])
        def luminance(col):
            def channel(n):
                s = n / 255.0
                return s / 12.92 if s <= .04045 else ((s + .055) / 1.055)**2.4
            return (.2126*channel(col.red()) + .7152*channel(col.green()) +
                    .0722*channel(col.blue()))
        def ratio(a, b):
            x, y = sorted((luminance(a), luminance(b)), reverse=True)
            return (x + .05) / (y + .05)
        for i, button in enumerate(getattr(self, '_annotation_footer_buttons', ())):
            name = button.property('annotationIconName')
            if not name:
                continue
            tint = QColor(colours['accent'] if i % 2 == 0 else colours['accent2'])
            ink = QColor(colours['ink'])
            # Nudge pastel-on-white or dark-on-dark accents toward high-contrast
            # ink while keeping the chosen theme's distinctive colour.
            for _ in range(12):
                if min(ratio(tint, bg), ratio(tint, active_bg)) >= 3.1:
                    break
                tint = QColor(blend_colour(tint.name(), ink.name(), .14))
            button.setIcon(line_icon(name, tint.name()))
        self._annotation_palette = colours
        self.canvas.set_ocr_colour(colours['accent'])
        if hasattr(self, 'ocr_bar'):
            self.ocr_bar.setStyleSheet(
                f"QFrame#ocrSelectionBar {{ background: {colours['panel']}; "
                f"border: 1px solid {colours['border']}; border-radius: 7px; }}")

    def _theme_annotation_quick_edit(self, colours):
        """Explicit theme colours, including the QDoubleSpinBox line editor."""
        panel = getattr(self, 'annotation_quick_edit', None)
        if panel is None:
            return
        panel.setStyleSheet(f"""
            QFrame#annotationQuickEdit {{background: transparent;
                color: {colours['ink']}; border: none;}}
            QFrame#annotationQuickEdit QLabel {{color: {colours['ink']}; border: none;
                background: transparent;}}
            QFrame#annotationQuickEdit QDoubleSpinBox {{
                background: {colours['paper']}; color: {colours['ink']};
                border: 1px solid {colours['border']}; border-radius: 5px;
                padding: 2px 3px; selection-background-color: {colours['accent']};}}
            QFrame#annotationQuickEdit QDoubleSpinBox QLineEdit {{
                color: {colours['ink']}; background: {colours['paper']};
                selection-background-color: {colours['accent']};}}
            QFrame#annotationQuickEdit QSlider::groove:horizontal {{
                height: 5px; background: {colours['border']}; border-radius: 2px;}}
            QFrame#annotationQuickEdit QSlider::sub-page:horizontal {{
                background: {colours['accent']}; border-radius: 2px;}}
            QFrame#annotationQuickEdit QSlider::handle:horizontal {{
                width: 13px; margin: -5px 0; background: {colours['accent']};
                border: 1px solid {colours['ink']}; border-radius: 6px;}}
        """)
        self._quick_edit_backdrop.set_theme(colours)

    def _sync_annotation_quick_edit_backdrop(self, visible=None):
        """Track the panel without a graphics effect on any interactive widget."""
        panel = getattr(self, 'annotation_quick_edit', None)
        backing = getattr(self, '_quick_edit_backdrop', None)
        if panel is None or backing is None:
            return
        if visible is False or (visible is None and not panel.isVisible()):
            backing.hide()
            return
        margin = AnnotationQuickEditBackdrop.MARGIN
        backing.setGeometry(panel.geometry().adjusted(-margin, -margin, margin, margin))
        backing.show()
        backing.stackUnder(panel)

    def show_annotation_appearance(self):
        """Colour toolbar opens the very same window used for selected marks."""
        panel = self.annotation_quick_edit
        mark = self._appearance_selection_mark
        self._quick_edit_dismissed = False
        self._quick_edit_defaults_mode = mark is None
        self._quick_edit_custom_position = False
        self._sync_annotation_quick_edit(mark)
        panel.adjustSize()
        self._position_annotation_quick_edit()

    def _annotation_editing_gesture(self, active):
        self._quick_gesture_active = bool(active)
        if active:
            self.annotation_quick_edit.hide()
        else:
            self._position_annotation_quick_edit()

    def _dismiss_annotation_quick_edit(self):
        self._quick_edit_dismissed = True
        self.annotation_quick_edit.hide()

    def _sync_annotation_quick_edit(self, mark):
        panel = self.annotation_quick_edit
        if mark is None and not self._quick_edit_defaults_mode:
            panel.hide()
            self._quick_edit_dismissed = False
            return
        if mark is not None:
            self._quick_edit_defaults_mode = False
        if self._quick_edit_dismissed:
            return
        kind = (mark.get('kind', '') if mark else self.canvas.annotation_tool)
        shape = mark.get('shape', '') if mark else ''
        title = ('Highlight' if kind.startswith('highlight') else
                 shape.replace('_', ' ').title() if shape else
                 'Marker' if mark and mark.get('blend') == 'multiply' else
                 'Pen' if mark and kind == 'stroke' else 'Drawing defaults')
        self.quick_title.setText(title + ' · Quick Edit')
        self.quick_thickness_row.setVisible(kind != 'highlight')
        self.arrow_size_row.setVisible(shape == 'arrow' or self.canvas.annotation_tool == 'arrow' and mark is None)
        with QSignalBlocker(self.quick_thickness):
            self.quick_thickness.setValue(round(self.stroke_width_control.value()*10))
        self.appearance_panel.layout().activate()
        panel.layout().activate()
        panel.adjustSize()
        self._position_annotation_quick_edit()

    def _position_annotation_quick_edit(self, *_):
        panel = getattr(self, 'annotation_quick_edit', None)
        if (panel is None or self._quick_edit_dismissed or self._quick_gesture_active):
            return
        viewport = self.canvas.viewport()
        # A wide, short panel is the default. Stack columns only when narrow.
        available = viewport.width() - 12
        if available < 290:
            panel.hide()
            return
        desired_width = min(self._quick_edit_user_width, available)
        direction = (QBoxLayout.Direction.LeftToRight if desired_width >= 420
                     else QBoxLayout.Direction.TopToBottom)
        if self._quick_columns.direction() != direction:
            self._quick_columns.setDirection(direction)
        if panel.width() != desired_width:
            panel.setFixedWidth(desired_width)
        self.appearance_panel.layout().activate()
        panel.layout().activate()
        panel.adjustSize()
        if viewport.width() < panel.width()+8 or viewport.height() < panel.height()+8:
            panel.hide()
            return
        if self._quick_edit_custom_position:
            x = max(4, min(viewport.width()-panel.width()-4, panel.x()))
            y = max(4, min(viewport.height()-panel.height()-4, panel.y()))
            panel.move(x, y)
            panel.show()
            panel.raise_()
            return
        item = self.canvas._selected_stroke
        if item is None or item not in self.canvas._item_marks:
            if not self._quick_edit_defaults_mode:
                panel.hide()
                return
            x, y = max(4, viewport.width()-panel.width()-10), 10
        else:
            bounds = item.mapRectToScene(item.path().boundingRect())
            tl = self.canvas.mapFromScene(bounds.topLeft())
            br = self.canvas.mapFromScene(bounds.bottomRight())
            if br.y() < 0 or tl.y() > viewport.height():
                panel.hide()
                return
            x = max(4, min(viewport.width()-panel.width()-4,
                           (tl.x()+br.x()-panel.width())//2))
            above, below = tl.y()-panel.height()-11, br.y()+11
            y = above if above >= 4 else (below if below+panel.height() <= viewport.height()-4
                                            else max(4, min(viewport.height()-panel.height()-4, above)))
        panel.move(int(x), int(y))
        panel.show()
        panel.raise_()

    def _sync_thickness_slider_from_spinbox(self, value):
        with QSignalBlocker(self.quick_thickness):
            self.quick_thickness.setValue(round(value*10))

    def _quick_thickness_preview(self, value):
        if not self._syncing_appearance:
            self.stroke_width_control.setValue(value/10)

    def _arrow_candidate(self, width_value=None, length_value=None):
        selected = self._appearance_selection_mark
        if selected is None or selected.get('shape') != 'arrow':
            return None
        width = (width_value if width_value is not None else
                 self.arrow_head_sliders['head_width'].value()) / 1000
        length = (length_value if length_value is not None else
                  self.arrow_head_sliders['head_length'].value()) / 1000
        return {**selected, 'head_width': width, 'head_length': length}

    def _preview_arrow_head(self, *_):
        if self._syncing_appearance:
            return
        arrow = self._arrow_candidate()
        if arrow and valid_vector(arrow):
            self.canvas.preview_selected_geometry(arrow)

    def _commit_arrow_head(self):
        arrow = self._arrow_candidate()
        if arrow is None:
            # Arrow tool's default head settings are independently remembered.
            if self.canvas.annotation_tool == 'arrow':
                style = self.canvas.tool_styles['arrow']
                for key, slider in self.arrow_head_sliders.items():
                    style[key] = slider.value()/1000
            return
        if not valid_vector(arrow):
            return
        before = self._appearance_selection_mark
        if before == arrow:
            return
        page = self.current_page()
        index = self._appearance_selection_index
        if page is None or index < 0:
            return
        marks = self.project.annotations.get(page['id'], [])
        if index >= len(marks) or marks[index] != before:
            return
        old, replacement = copy.deepcopy(before), copy.deepcopy(arrow)
        page_id = page['id']
        self._separate_text_commands()
        self.history.perform(CallbackAction(
            'Change Arrowhead',
            lambda: self._edit_stroke_marks(page_id,
                 lambda items: self._replace_annotation(items, index, old)),
            lambda: self._edit_stroke_marks(page_id,
                 lambda items: self._replace_annotation(items, index, replacement)), 320))

    def _appearance_values(self):
        return (self.pen_colour.colour.name(), self.stroke_opacity_control.value(),
                self.stroke_width_control.value(), self.stroke_enabled_checkbox.isChecked(),
                self.fill_colour.colour.name(), self.shape_fill_checkbox.isChecked(),
                self.fill_opacity_control.value())

    def _candidate_appearance_mark(self):
        current = self._appearance_selection_mark
        if current is None:
            return None
        changed = dict(current)
        changed['color'] = self.pen_colour.colour.name()
        changed['opacity'] = self.stroke_opacity_control.value()
        if changed['kind'] in ('stroke', 'shape', 'highlight_line'):
            changed['width'] = self.stroke_width_control.value()/1000
        if changed['kind'] == 'shape':
            changed['stroke_enabled'] = self.stroke_enabled_checkbox.isChecked()
            if changed['shape'] in ('rectangle', 'ellipse'):
                changed['fill'] = (self.fill_colour.colour.name()
                                   if self.shape_fill_checkbox.isChecked() else None)
                changed['fill_opacity'] = self.fill_opacity_control.value()
        return changed

    def _preview_annotation_appearance(self, *_):
        if self._syncing_appearance:
            return
        candidate = self._candidate_appearance_mark()
        if candidate is not None and valid_vector(candidate):
            self.canvas.preview_selected_appearance(candidate)

    def _appearance_changed(self, *_):
        """One history command per completed property edit, not per render frame."""
        if self._syncing_appearance:
            return
        self.pen_colour.set_paint_enabled(self.stroke_enabled_checkbox.isChecked())
        self.fill_colour.set_paint_enabled(self.shape_fill_checkbox.isChecked())
        values = self._appearance_values()
        if values == getattr(self, '_displayed_appearance', None):
            return
        current = self._appearance_selection_mark
        if current is None:
            tool = self.canvas.annotation_tool
            if tool not in self.canvas.tool_styles:
                return
            style = self.canvas.tool_styles[tool]
            style['color'] = self.pen_colour.colour.name()
            style['opacity'] = self.stroke_opacity_control.value()
            if tool != 'highlight':
                style['width'] = self.stroke_width_control.value()/1000
            if tool in ('rectangle', 'ellipse'):
                style['stroke_enabled'] = self.stroke_enabled_checkbox.isChecked()
                style['fill'] = (self.fill_colour.colour.name()
                                 if self.shape_fill_checkbox.isChecked() else None)
                style['fill_opacity'] = self.fill_opacity_control.value()
            self.canvas.pen_color = style['color']
            self.canvas.pen_width = style['width']
            if tool in ('highlight', 'highlight_line', 'marker'):
                self.canvas.highlight_color = style['color']
                self.highlight_button.set_colour(style['color'])
                self.project.highlight_color = style['color']
                self.schedule_save()
            self._displayed_appearance = values
            return
        idx = self._appearance_selection_index
        page = self.current_page()
        if not page or idx < 0:
            return
        marks = self.project.annotations.get(page['id'], [])
        if idx >= len(marks) or marks[idx] != current:
            return
        changed = self._candidate_appearance_mark()
        if changed == current or not valid_vector(changed):
            return
        before, after = copy.deepcopy(current), copy.deepcopy(changed)
        page_id = page['id']
        def apply(replacement):
            def change(items):
                updated = list(items)
                if idx < len(updated):
                    updated[idx] = replacement
                return updated
            self._edit_stroke_marks(page_id, change)
        self._separate_text_commands()
        self.history.perform(CallbackAction(
            'Change Annotation Appearance', lambda: apply(before),
            lambda: apply(after), 256 + 90 * len(after.get('points', []))))
        self._displayed_appearance = values

    def _apply_palette_colour(self, color, target):
        """A palette action changes only its chosen channel (stroke/fill/ink)."""
        if not isinstance(color, str) or not QColor(color).isValid():
            return
        if target == 'highlight':
            selected = self._appearance_selection_mark
            if ((selected is None) or (selected.get('kind') not in ('highlight', 'highlight_line')
                                      and selected.get('blend') != 'multiply')):
                self._set_highlight_defaults(color)
                if selected is None and self.canvas.annotation_tool in ('highlight', 'highlight_line', 'marker'):
                    self._annotation_selection_changed(-1, None)
                return
        if target == 'fill':
            if not self.shape_fill_checkbox.isEnabled():
                return
            self._select_palette_channel('fill')
            self.fill_colour.set_colour(color)
            with QSignalBlocker(self.shape_fill_checkbox):
                self.shape_fill_checkbox.setChecked(True)
            self._appearance_changed()
        else:
            self._select_palette_channel('stroke')
            if self.stroke_enabled_checkbox.isEnabled():
                with QSignalBlocker(self.stroke_enabled_checkbox):
                    self.stroke_enabled_checkbox.setChecked(True)
            self.pen_colour.set_colour(color)
            self._appearance_changed()

    def _set_highlight_defaults(self, color, opacity=None):
        """Explicit palette choice changes highlight presets, not a selected shape."""
        for tool in ('highlight', 'highlight_line', 'marker'):
            self.canvas.tool_styles[tool]['color'] = color
            if opacity is not None and tool != 'marker':
                self.canvas.tool_styles[tool]['opacity'] = opacity
        self.canvas.highlight_color = color
        self.project.highlight_color = color
        self.highlight_button.set_colour(color)
        self.schedule_save()

    def _remember_recent_colour(self, color):
        if color in self._palette_swatches:
            return
        self._recent_colours = [color] + [c for c in self._recent_colours if c != color]
        self._recent_colours = self._recent_colours[:3]
        for widget, saved in zip(self._recent_swatches, self._recent_colours):
            widget.setProperty('recentColour', saved)
            widget.setStyleSheet(
                f'QToolButton {{ background: {saved}; border: 1px solid #818696; border-radius: 5px; }}')
            widget.setToolTip(f'Recent custom colour {saved}')
            widget.show()

    def _palette_menu(self, button, point, colour):
        menu = QMenu(button)
        menu.addAction('Apply to Stroke', lambda: self._apply_palette_colour(colour, 'stroke'))
        menu.addAction('Apply to Fill', lambda: self._apply_palette_colour(colour, 'fill'))
        menu.addAction('Apply to Highlight', lambda: self._apply_palette_colour(colour, 'highlight'))
        menu.exec(button.mapToGlobal(point))

    def _pick_appearance_color(self, target='stroke'):
        selected = self._appearance_selection_mark
        if target == 'highlight' and selected is None:
            initial = QColor(self.canvas.tool_styles['highlight']['color'])
            colour = QColorDialog.getColor(initial, self, 'Highlight colour')
            if colour.isValid():
                self._remember_recent_colour(colour.name())
                self._set_highlight_defaults(colour.name())
                if self.canvas.annotation_tool in ('highlight', 'highlight_line'):
                    self._annotation_selection_changed(-1, None)
            return
        if target == 'fill' and not self.shape_fill_checkbox.isEnabled():
            return
        self._select_palette_channel(target)
        control = self.fill_colour if target == 'fill' else self.pen_colour
        colour = QColorDialog.getColor(QColor(control.colour), self,
                    'Fill colour' if target == 'fill' else 'Stroke / highlight colour')
        if not colour.isValid():
            return
        self._remember_recent_colour(colour.name())
        self._syncing_appearance = True
        try:
            control.set_colour(colour.name())
            checkbox = self.shape_fill_checkbox if target == 'fill' else self.stroke_enabled_checkbox
            if checkbox.isEnabled():
                checkbox.setChecked(True)
        finally:
            self._syncing_appearance = False
        self._appearance_changed()

    def pick_pen_color(self):
        self._pick_appearance_color('stroke')

    def pick_highlight_color(self):
        # The existing right-click shortcut still changes highlighter ink only.
        # Transparency remains exclusively in the unified Opacity pop-up.
        colour = QColorDialog.getColor(QColor(self.canvas.tool_styles['highlight']['color']),
                                       self, 'Page highlight colour')
        if colour.isValid():
            self._remember_recent_colour(colour.name())
            self._set_highlight_defaults(colour.name())
            if self.canvas.annotation_tool in ('highlight', 'highlight_line'):
                self._annotation_selection_changed(-1, None)
            self.schedule_save()

    def _apply_annotation_snapshot(self, page_id: str, marks: list[dict]):
        # The project model is authoritative; the scene is only a transient
        # view.  Rebuild the marks only when their page is displayed.
        if marks:
            self.project.annotations[page_id] = copy.deepcopy(marks)
        else:
            self.project.annotations.pop(page_id, None)
        active = self.current_page()
        if active is not None and active['id'] == page_id:
            self.canvas.set_annotations(self.project.annotations.get(page_id, []))
        self._celebrate_on_next_manual_save = True
        self.schedule_save()

    def add_highlight(self, mark):
        self._add_vector(mark, 'Highlight Page', auto_select=True)

    def _edit_stroke_marks(self, page_id, change):
        """Apply a compact stroke delta; snapshots never retain every stroke.

        The canvas is a disposable rendering of the model. Only the changed
        stroke needs to live inside its Undo action, even on a crowded page.
        """
        current = self.project.annotations.get(page_id, [])
        self._apply_annotation_snapshot(page_id, change(current))

    def add_stroke(self, mark):
        self._add_vector(mark, 'Draw Marker' if mark.get('blend') == 'multiply'
                         else 'Draw Stroke')

    def add_shape(self, mark):
        self._add_vector(mark, 'Draw Shape', auto_select=True)

    def _add_vector(self, mark, label, *, auto_select=False):
        page = self.current_page()
        if not page:
            return
        page_id = page['id']
        before = self.project.annotations.get(page_id, [])
        if len(before) >= 1000:
            self.canvas.set_annotations(before)
            self.statusMessage.emit('This page has reached the annotation limit.')
            return
        stroke = copy.deepcopy(mark)
        # Old saved rectangle highlights may have no ID. When one is ADDED as
        # a new annotation, give the copy a stable ID so the existing vector
        # Undo/Redo and selection helpers can identify exactly this mark.
        # Do not rewrite already-loaded legacy marks or mutate the caller.
        if stroke.get('kind') == 'highlight' and 'id' not in stroke:
            stroke['id'] = uuid4().hex
        self._separate_text_commands()
        self.history.perform(CallbackAction(
            label,
            lambda: self._edit_stroke_marks(page_id,
                                            lambda marks: remove_stroke(marks, stroke['id'])),
            lambda: self._edit_stroke_marks(page_id,
                                            lambda marks: add_mark(marks, stroke)),
            256 + 50 * len(stroke.get('points', []))))
        if auto_select:
            self.set_annotation_mode('select')
            self.canvas.select_mark_by_id(stroke['id'])

    @staticmethod
    def _replace_annotation(items, index, mark):
        """Index replacement also supports v0.5.0's anonymous rectangles."""
        updated = list(items)
        if 0 <= index < len(updated):
            updated[index] = mark
        return updated

    def move_stroke(self, index, delta):
        page = self.current_page()
        if not page:
            return
        page_id = page['id']
        marks = self.project.annotations.get(page_id, [])
        if not 0 <= index < len(marks) or marks[index].get('kind') not in ('stroke', 'shape', 'highlight', 'highlight_line'):
            return
        original = copy.deepcopy(marks[index])
        moved = translated_vector(original, delta['dx'], delta['dy'])
        if moved == original:
            self.canvas.set_annotations(marks)
            return
        self._separate_text_commands()
        self.history.perform(CallbackAction(
            'Move Annotation',
            lambda: self._edit_stroke_marks(page_id,
                                            lambda items: self._replace_annotation(items, index, original)),
            lambda: self._edit_stroke_marks(page_id,
                                            lambda items: self._replace_annotation(items, index, moved)),
            256 + 100 * len(moved.get('points', []))))

    def resize_stroke(self, index, resized):
        """One undo step for each completed shape/pen resize gesture."""
        page = self.current_page()
        if not page:
            return
        page_id = page['id']
        marks = self.project.annotations.get(page_id, [])
        if not 0 <= index < len(marks) or marks[index].get('kind') not in ('stroke', 'shape', 'highlight', 'highlight_line'):
            return
        original = copy.deepcopy(marks[index])
        if resized.get('id') != original.get('id') or resized == original:
            return
        replacement = copy.deepcopy(resized)
        self._separate_text_commands()
        self.history.perform(CallbackAction(
            'Resize Annotation',
            lambda: self._edit_stroke_marks(page_id,
                                            lambda items: self._replace_annotation(items, index, original)),
            lambda: self._edit_stroke_marks(page_id,
                                            lambda items: self._replace_annotation(items, index, replacement)),
            256 + 100 * len(replacement.get('points', []))))

    def erase_strokes(self, indexes):
        """Commit a mouse sweep as one per-tab, per-page history action.

        Snapshot only the erased marks, not every mark on a possibly large PDF.
        Original indices also handle legacy annotations without stable IDs.
        """
        page = self.current_page()
        if not page or not indexes:
            return
        page_id = page['id']
        items = self.project.annotations.get(page_id, [])
        selected = sorted(set(int(i) for i in indexes
                              if 0 <= int(i) < len(items)))
        if not selected:
            return
        removed = [(i, copy.deepcopy(items[i])) for i in selected]
        target = set(selected)

        def undo_marks(marks):
            output = list(marks)
            for i, mark in removed:
                output.insert(min(i, len(output)), copy.deepcopy(mark))
            return output

        def redo_marks(marks):
            # Undo/redo is serial within each tab; the marks at these stable
            # indices are the same marks as at the beginning of the gesture.
            return [mark for i, mark in enumerate(marks) if i not in target]

        self._separate_text_commands()
        self.history.perform(CallbackAction(
            'Erase Annotations' if len(removed) > 1 else 'Erase Annotation',
            lambda: self._edit_stroke_marks(page_id, undo_marks),
            lambda: self._edit_stroke_marks(page_id, redo_marks),
            160 + sum(180 + 64*len(mark.get('points', [])) for _, mark in removed)))

    def erase_stroke(self, index):
        page = self.current_page()
        if not page:
            return
        page_id = page['id']
        marks = self.project.annotations.get(page_id, [])
        if not 0 <= index < len(marks) or marks[index].get('kind') not in ('stroke', 'shape', 'highlight', 'highlight_line'):
            return
        original = copy.deepcopy(marks[index])
        self._separate_text_commands()
        self.history.perform(CallbackAction(
            'Erase Annotation',
            lambda: self._edit_stroke_marks(page_id,
                                            lambda items: restore_stroke(items, index, original)),
            lambda: self._edit_stroke_marks(page_id,
                                            lambda items: (items[:index] + items[index+1:]
                                                if original.get('id') is None else
                                                remove_stroke(items, original['id']))),
            256 + 50 * len(original.get('points', []))))

    def undo_annotation(self):
        if self.history.can_undo:
            self.history.undo()

    def redo_annotation(self):
        if self.history.can_redo:
            self.history.redo()

    def clear_highlights(self):
        page = self.current_page()
        if page and self.project.annotations.get(page['id']):
            answer = QMessageBox.question(self, 'Clear annotations', 'Remove all marks on this page?',
                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if answer == QMessageBox.StandardButton.Yes:
                before = self.project.annotations.get(page['id'], [])
                command = AnnotationChangeCommand(self, page['id'], before, [], 'Clear marks')
                self._separate_text_commands()
                self.history.perform(CallbackAction('Clear Marks', command.undo,
                                                    command.redo, 256 + 160 * len(before)))

    def link_current_page(self):
        page = self.current_page()
        if page:
            self.notes.insert_page_link(page['id'], page['title'])
        else:
            QMessageBox.information(self, 'Link to page', 'First select a page from the left column.')

    def open_external_url(self, url):
        parsed = urlsplit(url)
        if parsed.scheme in ('http', 'https') and parsed.netloc:
            QDesktopServices.openUrl(QUrl(url))

    def _restore_notes_scroll(self):
        if self._notes_scroll_restored or not self._active or self._closed:
            return
        bar = self.notes.editor.verticalScrollBar()
        entry = self._current_note_page()
        target = max(bar.minimum(), min(bar.maximum(), int(entry['scroll'])))
        bar.setValue(target)
        self._notes_scroll_restored = True
        self._restoring_notes_scroll = False

    def _notes_scrolled(self, _value):
        if not self._restoring_notes_scroll and not self._loading and not self._closed:
            # Coalesce wheel/touchpad movement; no disk writes on every tick.
            self._scroll_idle_timer.start()

    def _scroll_position_settled(self):
        position = self.notes.editor.verticalScrollBar().value()
        if position != self._current_note_page()['scroll']:
            self.schedule_save()

    def schedule_save(self):
        if self._loading or self._closed:
            return
        if not self._dirty:
            self._dirty = True
        if not self._save_timer.isActive():
            self._save_timer.start()  # first unsaved edit starts a 60s window
        # Do not restart for each keystroke or continuous typing never saves.

    def _autosave(self):
        if not self._dirty or self._closed:
            return
        try:
            self.save()
        except Exception as exc:
            # Keep dirty state, let the user continue, and retry without
            # emitting repetitive modal error dialogs while typing.
            self.statusMessage.emit(f'Autosave could not finish: {exc}')
            self._save_timer.start()  # retry next minute, not every 5 seconds

    def save(self):
        self._capture_displayed_reading_position()
        # Serialise only; never call setHtml()/reload the editor here, because
        # that would destroy its native QTextDocument undo/redo history.
        html = self.notes.html()
        current_widths = dict(zip(self._panel_order, self.splitter.sizes()))
        if not self._navigator_visible:
            current_widths['pages'] = max(74, self._navigator_restore_width)
        widths = [current_widths[key] for key in PANEL_KEYS]
        current = self._current_note_page()
        current['html'] = html
        current['scroll'] = self.notes.editor.verticalScrollBar().value()
        current['page_setup'] = (self.notes.page_setup.as_dict()
            if self.notes.page_setup is not None else None)
        # The old keys remain a read-only compatibility mirror of Page 1.
        first = self.project.note_pages[0]
        self.project.notes_html = first['html']
        self.project.notes_scroll = first['scroll']
        self.project.notes_page_setup = copy.deepcopy(first['page_setup'])
        self.project.splitter_sizes = widths
        self.project.panel_order = list(self._panel_order)
        self.project.save()  # tab-local v4 manifest; cached renders excluded
        container_save = getattr(self, 'on_container_save', None)
        if container_save:
            container_save()  # incremental v5 SQLite commit, never reload QTextDocument
        self._dirty = False
        self._save_timer.stop()
        self.titleChanged.emit(self.project.name)

    def save_copy_as(self):
        if self._importing:
            raise RuntimeError('Finish importing before saving a copy of the project.')
        self.save()
        start = self.settings.value('lastSaveDir', str(self.project.path.parent))
        parent = QFileDialog.getExistingDirectory(self, 'Choose folder for saved copy', start)
        if not parent:
            return None
        name, ok = QInputDialog.getText(self, 'Save project as', 'Project name:', text=self.project.name + ' Copy')
        if ok and name.strip():
            self.settings.setValue('lastSaveDir', parent)
            return self.project.duplicate_to(Path(parent), name)
        return None

    def export_html(self):
        start = self.settings.value('lastSaveDir', str(self.project.path.parent))
        output, _ = QFileDialog.getSaveFileName(self, 'Export notes as HTML',
                              str(Path(start) / f'{self.project.name}-notes.html'), 'HTML (*.html)')
        if output:
            Path(output).write_text(self.notes.html(), encoding='utf-8')
            self.settings.setValue('lastSaveDir', str(Path(output).parent))
            self.statusMessage.emit('Exported notes as HTML.')

    def close_project(self):
        if self._importing:
            raise RuntimeError('A document is importing. Finish the import before closing this tab.')
        self.save()
        self.deactivate()
        self._closed = True


class TabTrashButton(QToolButton):
    """Show the delete glyph even when the mouse enters via the button area."""
    hovered = Signal()

    def enterEvent(self, event):
        self.hovered.emit()
        super().enterEvent(event)


class HoverDeleteTabBar(QTabBar):
    """Reserve trash-button width but show its red glyph only on hover."""
    hoveredTabChanged = Signal(int)
    pagesDropped = Signal(str, str, list, bool)
    notebookDropped = Signal(str)
    geometryChanged = Signal()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.geometryChanged.emit()

    def tabLayoutChange(self):
        super().tabLayoutChange()
        self.geometryChanged.emit()

    def _external_notebook(self, event):
        urls = event.mimeData().urls() if event.mimeData().hasUrls() else []
        return (urls[0].toLocalFile() if len(urls) == 1 and urls[0].isLocalFile()
                and Path(urls[0].toLocalFile()).suffix.lower() in
                ('.yomunote', '.yominote') else None)

    def dragEnterEvent(self, event):
        if (event.mimeData().hasFormat(DropPageList.PAGE_MIME)
                or self._external_notebook(event)):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if self._external_notebook(event):
            event.acceptProposedAction()
            return
        index = self.tabAt(event.position().toPoint())
        if index >= 0 and event.mimeData().hasFormat(DropPageList.PAGE_MIME):
            event.acceptProposedAction()
        elif event.mimeData().hasFormat(DropPageList.PAGE_MIME):
            event.ignore()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        notebook_path = self._external_notebook(event)
        if notebook_path:
            event.acceptProposedAction()
            # Never run a modal selection dialog inside Qt's native drag event.
            QTimer.singleShot(0, lambda p=notebook_path: self.notebookDropped.emit(p))
            return
        index = self.tabAt(event.position().toPoint())
        if not event.mimeData().hasFormat(DropPageList.PAGE_MIME):
            super().dropEvent(event)
            return
        if index < 0:
            event.ignore()
            return
        try:
            data = json.loads(bytes(event.mimeData().data(DropPageList.PAGE_MIME)).decode('utf-8'))
            parent = self.parent()
            pane = parent.widget(index) if isinstance(parent, QTabWidget) else None
            if pane is None or pane._tab_id == data['source']:
                event.ignore()
                return
            self.pagesDropped.emit(data['source'], pane._tab_id,
                                   data['pages'], bool(event.keyboardModifiers() &
                                   (Qt.KeyboardModifier.ControlModifier |
                                    Qt.KeyboardModifier.AltModifier)))
            event.acceptProposedAction()
        except (ValueError, KeyError, TypeError, AttributeError):
            event.ignore()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        # Qt owns the tab overflow arrows and tracks their scroll offset.
        # Keep that native machinery; do not simulate scroll by selecting tabs.
        self.setUsesScrollButtons(True)
        self.setElideMode(Qt.TextElideMode.ElideNone)
        self._hovered = -1

    def wheelEvent(self, event):
        """Scroll the TAB STRIP sideways, not the selected notebook page.

        Ordinary up/down mouse wheels and horizontal trackpad gestures both
        work. Qt's own scroll-arrow controls remain responsible for the scroll
        offset, so dragging tabs, hover-to-delete and keyboard selection keep
        their native behaviour on Windows, macOS and Linux.
        """
        buttons = {button.arrowType(): button
                   for button in self.findChildren(QToolButton)
                   if button.isVisible() and button.arrowType() in (
                       Qt.ArrowType.LeftArrow, Qt.ArrowType.RightArrow)}
        if (not buttons or self.count() < 2):
            super().wheelEvent(event)
            return
        angled = event.angleDelta()
        pixels = event.pixelDelta()
        delta = angled.x() if angled.x() else angled.y()
        if not delta:
            delta = pixels.x() if pixels.x() else pixels.y()
        if not delta:
            event.ignore()
            return
        # Positive wheel/up/left reveals earlier tabs; down/right reveals later.
        arrow = Qt.ArrowType.LeftArrow if delta > 0 else Qt.ArrowType.RightArrow
        button = buttons.get(arrow)
        if button and button.isEnabled():
            repetitions = max(1, min(4, round(abs(delta) / 120)))
            for _ in range(repetitions):
                if button.isEnabled():
                    button.click()
        event.accept()

    def mouseMoveEvent(self, event):
        index = self.tabAt(event.position().toPoint())
        if index != self._hovered:
            self._hovered = index
            self.hoveredTabChanged.emit(index)
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self._hovered = -1
        self.hoveredTabChanged.emit(-1)
        super().leaveEvent(event)


class DeleteNotebookTabCommand(QUndoCommand):
    """Keep deleted tab source files in a temporary working folder for Undo."""
    def __init__(self, window, tabid):
        super().__init__('Delete project tab')
        self.window = window
        self.tabid = tabid
        self.deleted = None

    def redo(self):
        notebook = self.window.notebook
        self.window._save_current_tab()
        self.deleted = notebook.delete_tab(self.tabid)
        self.window._resync_notebook_tabs()
        notebook.save()

    def undo(self):
        notebook = self.window.notebook
        index, entry = self.deleted
        notebook.restore_tab(index, entry)
        self.window._resync_notebook_tabs()
        notebook.save()


class MainWindow(QMainWindow):
    """Top-level controller for notebooks, tab widgets, menus and sharing.

    Beginners: Qt sends events to slots (callback methods) on this object.
    ``self.notebook`` stores the current on-disk data; ``self.tabs`` is the
    visible QTabWidget. They must stay in sync after import/Undo/Redo.
    Tab Exchange is staged off-thread and committed from the GUI thread.
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Yomu Note  ·  よむ')
        self.resize(1450, 900)
        self.setMinimumSize(760, 600)
        self.settings = QSettings('Yomu Note', 'Yomu Note')
        # Import known preferences from the old app namespace once, without
        # modifying the original settings or reopening old project files.
        if not self.settings.value('preferencesMigrated', False, type=bool):
            previous = QSettings('Sumi Study', 'Sumi Study')
            for key in ('theme', 'defaultFont', 'defaultFontSize', 'defaultBold',
                        'defaultItalic', 'defaultAlignment', 'lastOpenDir',
                        'lastSaveDir', 'recentProjects', 'openProjects'):
                if not self.settings.contains(key) and previous.contains(key):
                    self.settings.setValue(key, previous.value(key))
            self.settings.setValue('preferencesMigrated', True)
        self.theme = self.settings.value('theme', 'washi')
        if self.theme not in THEME_NAMES:
            self.theme = 'washi'
        self.notebook = None
        self._exchange_busy = False
        self._exchange_cancel = None
        self._exchange_progress = None
        self.setAcceptDrops(True)
        self._reordering_tabs = False
        self._changing_notebook = False
        # One chronological history per tab, shared by that tab's notes,
        # annotations and pages. This is unrelated to the incremental tab UI.
        self._history_clock = 0
        self._fallback_history = UnifiedHistory(max_actions=1000,
                                                max_memory_bytes=200 * 1024 * 1024,
                                                sequence_provider=self._next_history_sequence)
        # Deleting a tab must remain undoable from every surviving tab.
        # This is separate from all per-tab notes/annotation histories.
        self._notebook_history = UnifiedHistory(max_actions=1000,
                                                max_memory_bytes=200 * 1024 * 1024,
                                                sequence_provider=self._next_history_sequence)
        self._notebook_history.on_changed(lambda *_: self._update_undo_actions())
        self._parked_panes = {}  # preserve native text undo while a tab is deleted
        # Whole notebook workspaces can be reclaimed once their queued render
        # workers have finished.  This does NOT change within-notebook Undo.
        self._retired_resources = RetiredNotebookQueue()
        self._retirement_timer = QTimer(self)
        self._retirement_timer.setInterval(750)
        self._retirement_timer.timeout.connect(self._drain_retired_resources)
        # The status bar must exist BEFORE its permanent progress widgets.
        # Replacing it later destroys those Qt children, leaving Python with
        # deleted QLabel/QProgressBar wrappers during tab and checkbox updates.
        self.setStatusBar(QStatusBar())
        # One read summary across ALL tabs.  It is derived from each
        # tab's live pages, so an empty or closed tab cannot count twice.
        self._notebook_progress_label = QLabel('Notebook: 0 / 0')
        self._notebook_progress_bar = ReadingProgressBar()
        self._notebook_progress_bar.setObjectName('readingProgress')
        self._notebook_progress_bar.set_reduced_motion(
            str(self.settings.value('reducedMotion', 'false')).lower() == 'true')
        self._notebook_progress_bar.setFixedHeight(7)
        self._notebook_progress_bar.setTextVisible(False)
        # These are added to the persistent header below, not the status bar.
        self.tabs = QTabWidget()
        self.tabs.setMovable(True)
        self.tabs.setTabsClosable(False)
        self.tabs.setTabBar(HoverDeleteTabBar())
        bar = self.tabs.tabBar()
        bar.hoveredTabChanged.connect(self._show_tab_trash_on_hover)
        bar.pagesDropped.connect(self._transfer_tab_pages)
        bar.notebookDropped.connect(self.import_notebook_tabs)
        bar.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        bar.customContextMenuRequested.connect(self.show_tab_context_menu)
        bar.tabMoved.connect(self._on_tab_moved)
        bar.setMovable(True)  # Native drag reorder, not the delete icon.
        bar.tabBarDoubleClicked.connect(self.rename_tab)
        bar.setExpanding(False)
        bar.setDocumentMode(False)
        self.tabs.currentChanged.connect(self.change_tab)
        # Keep the corner a CONSTANT 38px. Expanding a QTabWidget corner to
        # consume empty space actually covers draggable tabs on Windows and
        # makes the + appear pinned at the far right. Instead float the inline
        # control directly above the spare tab-bar area. When tabs overflow,
        # show a separate always-accessible + in that fixed-width corner.
        self._tab_plus_layout_pending = False
        self._add_tab_button = QToolButton(self.tabs)
        self._add_tab_button.setText('＋')
        self._add_tab_button.setObjectName('insertPlus')
        self._add_tab_button.setToolTip('Add a new tab to this project')
        self._add_tab_button.setFixedSize(32, 30)
        self._add_tab_button.clicked.connect(self.add_tab)
        self._add_tab_button.hide()
        self._tab_plus_corner = QWidget(self.tabs)
        self._tab_plus_corner.setObjectName('tabAddCorner')
        plus_row = QHBoxLayout(self._tab_plus_corner)
        plus_row.setContentsMargins(3, 0, 3, 0)
        plus_row.setSpacing(0)
        self._overflow_add_tab_button = QToolButton(self._tab_plus_corner)
        self._overflow_add_tab_button.setText('＋')
        self._overflow_add_tab_button.setObjectName('insertPlus')
        self._overflow_add_tab_button.setToolTip('Add a new tab to this project')
        self._overflow_add_tab_button.setFixedSize(32, 30)
        self._overflow_add_tab_button.clicked.connect(self.add_tab)
        plus_row.addWidget(self._overflow_add_tab_button, 0, Qt.AlignmentFlag.AlignVCenter)
        self._tab_plus_corner.setFixedSize(38, 34)
        self._tab_plus_corner.setSizePolicy(QSizePolicy.Policy.Fixed,
                                           QSizePolicy.Policy.Preferred)
        self.tabs.setCornerWidget(self._tab_plus_corner, Qt.Corner.TopRightCorner)
        bar.geometryChanged.connect(self._queue_inline_tab_plus_layout)
        self.tabs.installEventFilter(self)
        self.root = QWidget()
        self.root.installEventFilter(self)
        self.root_layout = QVBoxLayout(self.root)
        self.root_layout.setContentsMargins(0, 0, 0, 0)
        self.root_layout.setSpacing(0)
        self.header = QWidget()
        self.header.setObjectName('topHeader')
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(11, 2, 11, 2)
        header_layout.setSpacing(8)
        self.brand = YomuWordmark(self.header)
        header_layout.addWidget(self.brand, 0, Qt.AlignmentFlag.AlignVCenter)
        # The single notebook-wide summary stays visible across tab changes.
        notebook_header = QWidget(self.header)
        notebook_header.setMinimumWidth(105)
        notebook_header.setMaximumWidth(225)
        notebook_header_layout = QVBoxLayout(notebook_header)
        notebook_header_layout.setContentsMargins(0, 2, 0, 2)
        notebook_header_layout.setSpacing(2)
        self._notebook_progress_label.setParent(notebook_header)
        self._notebook_progress_bar.setParent(notebook_header)
        self._notebook_progress_bar.setFixedHeight(7)
        self._notebook_progress_bar.setMinimumWidth(105)
        self._notebook_progress_bar.setMaximumWidth(220)
        notebook_header_layout.addWidget(self._notebook_progress_label)
        notebook_header_layout.addWidget(self._notebook_progress_bar)
        header_layout.addWidget(notebook_header, 0, Qt.AlignmentFlag.AlignVCenter)
        self.brand.clicked.connect(self.show_about)
        self.quick_actions = WrapBar('Quick actions', self.header)
        header_layout.addWidget(self.quick_actions, 1, Qt.AlignmentFlag.AlignVCenter)
        self.focus_flower = FocusFlower(self.header)
        header_layout.addWidget(self.focus_flower, 0, Qt.AlignmentFlag.AlignVCenter)
        self.focus_timer = FocusTimer(self.settings, self.header)
        self.focus_timer.flower = self.focus_flower
        header_layout.addWidget(self.focus_timer, 0, Qt.AlignmentFlag.AlignVCenter)
        self.root_layout.addWidget(self.header, 0)
        self.root_layout.addWidget(self.tabs, 1)
        self.setCentralWidget(self.root)
        self.save_toast = SaveToast(self.root)
        self.save_confetti = ConfettiOverlay(self.root)
        self.kawaii_notice = KawaiiNotice(self.root)
        self.focus_timer.reminder.connect(self._show_focus_reminder)
        self.button_motion = SoftButtonMotion(self)
        QApplication.instance().installEventFilter(self.button_motion)
        # One tiny MIME-only filter also catches Explorer/Finder notebook drops
        # over QTextEdit, QGraphicsView and tab-strip child viewports. Without
        # it the text editor can consume a .yomunote as a text/URL paste.
        QApplication.instance().installEventFilter(self)
        self.configure_actions()
        self._fallback_history.on_changed(lambda *_: self._update_undo_actions())
        self.brand.set_reduced_motion(str(self.settings.value('reducedMotion', 'false')).lower() == 'true')
        self.button_motion.reduced_motion = self.brand._reduce_motion
        self.save_toast.reduced_motion = self.brand._reduce_motion
        self.apply_theme()
        try:
            QApplication.styleHints().colorSchemeChanged.connect(
                lambda *_: self.apply_theme() if self.theme == 'system' else None)
        except AttributeError:
            pass
        self.backup_timer = QTimer(self)
        self.backup_timer.setInterval(10 * 60 * 1000)  # rotating snapshots every 10 min
        self.backup_timer.timeout.connect(self._periodic_backup)
        paths = self.settings.value('openProjects', [])
        if isinstance(paths, str):
            paths = [paths]
        startup_errors = []
        for path in paths[:1]:  # one notebook with internal tabs
            try:
                self.show_notebook(Notebook.load(Path(path)))
            except Exception as exc:
                # Never quietly open an empty notebook as though nothing
                # happened. Tell the user which file failed to load.
                logger.exception('Could not reopen previous notebook')
                startup_errors.append((str(path), str(exc)))
        if self.notebook is None:
            self.show_notebook(Notebook.create(Path.home() / 'Documents' / 'Yomu Note',
                                               'My First Notes'))
        self.change_tab()
        if startup_errors:
            file_path, problem = startup_errors[0]
            QTimer.singleShot(0, lambda p=file_path, e=problem:
                QMessageBox.warning(
                    self, 'Previous notebook could not open',
                    f'Yomu Note could not reopen:\n{p}\n\n{e}\n\n'
                    'The original notebook has NOT been modified.\n'
                    'Use File → Open to retry or attempt recovery.'))

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() != QEvent.Type.WindowStateChange or not hasattr(self, 'tabs'):
            return
        minimised = bool(self.windowState() & Qt.WindowState.WindowMinimized)
        if minimised:
            # Qt already stops painting obscured windows; halt our visual-only
            # animations too. Preserve the timer that schedules study sounds.
            self.brand._timer.stop()
            self.brand._fade.stop()
            self.focus_flower.anim.stop()
            self.save_confetti.anim.stop()
            self.save_confetti.hide()
            self.save_toast.animation.stop()
            self.save_toast.hide()
            self.kawaii_notice.hide()
            self._notebook_progress_bar._motion.stop()
            self._notebook_progress_bar._flash.stop()
        for i in range(self.tabs.count()):
            pane = self.tabs.widget(i)
            if minimised:
                pane.pages_list._hover_delegate.anim.stop()
                pane.pages_list._wheel_animation.stop()
                for panel in (pane.shelf, pane.canvas_panel, pane.notes_backdrop):
                    panel.anim.stop()
        if not minimised and self.active():
            # A previously deferred visible-row request may resume now.
            self.active().schedule_thumbnails()
        # No extra page loading, image copies, or cache invalidation needed
        # when restoring the window; the current scene pixmap remains intact.

    def action(self, title, callback, shortcut=None):
        act = QAction(title, self)
        if shortcut:
            act.setShortcut(QKeySequence(shortcut))
        act.triggered.connect(callback)
        return act

    def _set_active_navigator_visibility(self, checked):
        self._set_all_navigator_visibility(checked)

    def _set_all_navigator_visibility(self, visible):
        # One workspace preference across notebook tabs. Reuse each pane's
        # shelf and thumbnail cache; no tabs or pages are rebuilt.
        self.settings.setValue('showPageNavigator', bool(visible))
        for index in range(self.tabs.count()):
            pane = self.tabs.widget(index)
            if isinstance(pane, ProjectPane):
                pane.set_navigator_visible(visible, persist=False)
        self._sync_navigator_menu_action()

    def _sync_navigator_menu_action(self):
        pane = self.active()
        action = getattr(self, 'navigator_visibility_action', None)
        if action is not None and pane is not None:
            with QSignalBlocker(action):
                action.setChecked(pane._navigator_visible)

    def configure_actions(self):
        file_menu = self.menuBar().addMenu('&File')
        new = self.action('New Project…', self.new_project, QKeySequence.StandardKey.New)
        open_action = self.action('Open Project…', self.open_project, QKeySequence.StandardKey.Open)
        save = self.action('Save Project', self.save_project, QKeySequence.StandardKey.Save)
        save_as = self.action('Save Copy As…', self.save_copy_as)
        importing = self.action('Import Files…', self.import_files, 'Ctrl+Shift+I')
        self.recent_menu = file_menu.addMenu('Open Recent')
        self.recent_menu.aboutToShow.connect(self.populate_recents)
        for a in (new, open_action):
            file_menu.insertAction(self.recent_menu.menuAction(), a)
        for a in (save, save_as, importing):
            file_menu.addAction(a)
        file_menu.addAction(self.action('Import Tabs from Notebook…',
                                        self.import_notebook_tabs))
        file_menu.addAction(self.action('Export Selected Tabs as Notebook…',
                                        self.export_selected_tabs))
        file_menu.addAction(self.action(
            'Smart Import…', lambda: self.active() and
            self.active().choose_files(smart_default=True)))
        file_menu.addAction(self.action('Add Blank Page', lambda: self.active() and self.active().add_blank()))
        file_menu.addAction(self.action('Export Notes as HTML…',
            lambda: self.active() and self.active().export_html()))
        file_menu.addAction(self.action(
            'Export Clean Notebook for Sharing…', self.export_clean_notebook))
        file_menu.addSeparator()
        file_menu.addAction(self.action('Import Older Project Folder…', self.import_legacy_project))
        file_menu.addAction(self.action('Close Project', self.close_current, QKeySequence.StandardKey.Close))
        file_menu.addAction(self.action('Restore Backup As…', self.restore_backup))
        file_menu.addSeparator()
        file_menu.addAction(self.action('Quit Yomu Note', self.close,
                                        QKeySequence.StandardKey.Quit))

        edit = self.menuBar().addMenu('&Edit')
        self.undo_notes_action = self.action('Undo', self.undo_shared, QKeySequence.StandardKey.Undo)
        self.redo_notes_action = self.action('Redo', self.redo_shared)
        # Windows/Linux users commonly expect Ctrl+Y as an alternative.
        # QKeySequence supports several shortcuts on ONE action, so
        # the menu, toolbar and keyboard share the same handler.
        redo_keys = ['Ctrl+Shift+Z']
        if not IS_MAC:
            redo_keys.append('Ctrl+Y')
        self.redo_notes_action.setShortcuts(
            [QKeySequence(key) for key in redo_keys])
        # A single pair in the Edit menu. The title reflects the next command
        # (text, highlight, page or tab), never which widget has keyboard focus.
        edit.addAction(self.undo_notes_action)
        edit.addAction(self.redo_notes_action)
        edit.aboutToShow.connect(self._update_undo_actions)
        self.tabs.currentChanged.connect(lambda _index: self._update_undo_actions())
        edit.addSeparator()
        edit.addAction(self.action(f'Insert Link to Selected Page  ·  {docs_shortcut("page_link")}', lambda: self.active() and self.active().link_current_page()))
        edit.addAction(self.action('Remove Selected Pages', lambda: self.active() and self.active().remove_page()))
        edit.addAction(self.action('Focus Notes', lambda: self.active() and self.active().notes.focus_notes()))
        edit.addAction(self.action('Repair Notes Line Spacing…', self.repair_notes_line_spacing))
        edit.addSeparator()
        edit.addAction(self.action('Find in Notes…',
                        lambda: self.active() and self.active().notes.open_find(),
                        QKeySequence.StandardKey.Find))
        edit.addAction(self.action('Find Next in Notes',
                        lambda: self.active() and self.active().notes.find_next(), 'Ctrl+G'))
        edit.addAction(self.action('Find Previous in Notes',
                        lambda: self.active() and self.active().notes.find_previous(), 'Ctrl+Shift+G'))

        insert = self.menuBar().addMenu('&Insert')
        insert.addAction(self.action('Horizontal Line',
            lambda: self.active() and self.active().notes.insert_horizontal_line()))

        view = self.menuBar().addMenu('&View')
        self.navigator_visibility_action = view.addAction('Show Page Navigator')
        self.navigator_visibility_action.setCheckable(True)
        self.navigator_visibility_action.setChecked(
            str(self.settings.value('showPageNavigator', 'true')).lower() != 'false')
        self.navigator_visibility_action.triggered.connect(self._set_active_navigator_visibility)
        view.addSeparator()
        themes = view.addMenu('Colour Theme')
        for key, title in THEME_NAMES.items():
            themes.addAction(self.action(title, lambda _checked=False, key=key: self.set_theme(key)))
        view.addAction(self.action('Fit Page to Preview', lambda: self.active() and self.active().canvas.fit_page()))
        view.addAction(self.action('Actual Image Pixels', lambda: self.active() and self.active().canvas_actual()))
        view.addSeparator()
        workspace_menu = view.addMenu('Workspace Layout')
        from itertools import permutations
        display_names = {'pages': 'Pages', 'preview': 'Preview', 'notes': 'Notes'}
        for arrangement in permutations(PANEL_KEYS):
            label = ' → '.join(display_names[key] for key in arrangement)
            workspace_menu.addAction(self.action(label,
                lambda _checked=False, order=arrangement: self.active() and
                    self.active().apply_panel_order(list(order))))
        workspace_menu.addSeparator()
        workspace_menu.addAction(self.action('Reset to Classic',
            lambda: self.active() and self.active().reset_workspace_layout()))
        options = self.menuBar().addMenu('&Settings')
        options.addAction(self.action('Preferences…', self.show_preferences, 'Ctrl+,'))
        options.addAction(self.action('Notes Page Setup…',
            lambda: self.active() and self.active().show_notes_page_setup()))
        help_menu = self.menuBar().addMenu('&Help')
        help_menu.addAction(self.action('About Yomu Note', self.show_about))

        # All header actions wrap instead of disappearing behind toolbar overflow.
        for act, label, tip in [
                (new, '✿ New', f'New project · {PRIMARY}N'),
                (open_action, 'Open', f'Open a project · {PRIMARY}O'),
                (save, 'Save', f'Save your notes · {PRIMARY}S'),
                (importing, '+ Import', f'Import documents · {docs_shortcut("import")}')]:
            quick = self.quick_actions.addAction(label)
            quick.setToolTip(tip)
            quick.triggered.connect(act.trigger)
        preferences = self.quick_actions.addAction('⚙ Settings')
        preferences.setToolTip(f'Preferences · {PRIMARY},')
        preferences.triggered.connect(self.show_preferences)

    def repair_notes_line_spacing(self):
        """Opt-in fix for paragraphs left with FixedHeight by v0.4.4b.

        Normal rich-text line metrics are restored without editing text, HTML,
        page annotations, project containers, or caches. Qt's native undo
        stack retains the entire repair as one undoable edit.
        """
        pane = self.active()
        if pane is None:
            return
        count = pane.notes.count_fixed_height_paragraphs()
        if not count:
            QMessageBox.information(self, 'Notes line spacing',
                                    'No fixed-height paragraphs need repairing in this tab.')
            return
        answer = QMessageBox.question(
            self, 'Repair notes line spacing',
            f'This tab has {count} paragraph(s) with fixed line heights.\n\n'
            'These can cause overlapping or clipped text after the v0.4.4b update. '
            'Restore automatic line spacing for those paragraphs?\n\n'
            'This formatting change can be undone with Undo.',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        repaired = pane.notes.repair_fixed_height_paragraphs()
        self.statusBar().showMessage(f'Repaired line spacing for {repaired} paragraph(s).', 5000)

    @property
    def history(self):
        """The active tab's combined edit history, never another tab's."""
        pane = self.active() if hasattr(self, 'tabs') else None
        return pane.history if pane is not None else self._fallback_history

    def _next_history_sequence(self):
        self._history_clock += 1
        return self._history_clock

    def _history_target(self, *, redo=False):
        """Notebook deletes are visible from any tab, local edits stay local.

        Undo chooses the latest action among the current tab and notebook
        structural actions. Redo uses the earliest undone action, preserving
        the same order when both streams have entries.
        """
        local = self.history
        shared = self._notebook_history
        choices = ([h for h in (local, shared) if h.can_redo] if redo else
                   [h for h in (local, shared) if h.can_undo])
        if not choices:
            return local
        sequence = (lambda h: h.next_redo_sequence) if redo else (lambda h: h.next_undo_sequence)
        return (min if redo else max)(choices, key=sequence)

    def _update_undo_actions(self):
        if not hasattr(self, 'undo_notes_action'):
            return
        undo = self._history_target().next_undo_label
        redo = self._history_target(redo=True).next_redo_label
        self.undo_notes_action.setText('Undo ' + undo if undo else 'Undo')
        self.redo_notes_action.setText('Redo ' + redo if redo else 'Redo')
        self.undo_notes_action.setEnabled(self.history.can_undo or self._notebook_history.can_undo)
        self.redo_notes_action.setEnabled(self.history.can_redo or self._notebook_history.can_redo)
        if pane := self.active():
            pane._update_page_undo_availability()

    def undo_shared(self):
        target = self._history_target()
        if target.can_undo:
            try:
                target.undo()
            except Exception as exc:
                QMessageBox.warning(self, 'Undo failed', str(exc))

    def redo_shared(self):
        target = self._history_target(redo=True)
        if target.can_redo:
            try:
                target.redo()
            except Exception as exc:
                QMessageBox.warning(self, 'Redo failed', str(exc))

    def _record_text_edit(self, pane, note_id=None):
        """Qt's undoCommandAdded identifies one new native text undo level.

        No HTML snapshot or setHtml() call occurs: text selection, formatting,
        zoom, and the native QTextDocument history stay in their original form.
        """
        if not self.notebook or pane._closed or pane.history.replaying:
            return
        if pane._tab_id not in {tab['id'] for tab in self.notebook.tabs}:
            return
        editor = pane.notes.editor
        note_id = note_id or pane.project.active_note_id
        def replay_note_command(*, redo=False):
            # Re-select the document that originally produced the Undo level;
            # applying edit history to the presently visible OTHER notes page
            # would silently corrupt the wrong notes.
            pane.select_note_page(note_id)
            ed = pane.notes.editor
            if redo:
                ed.preserve_view_state(ed.redo)
            else:
                ed.preserve_view_state(ed.undo)
            pane.schedule_save()
        change = getattr(pane, '_pending_page_setup_history', None)
        if change is not None:
            # This particular Qt command belongs to Page Setup.
            # Never add a SECOND entry solely for its saved JSON values.
            if getattr(pane, '_page_setup_history_recorded', False):
                return
            pane._page_setup_history_recorded = True
            before, after = copy.deepcopy(change)

            def replay(metadata, redo=False):
                # Qt restores native per-paragraph formats. Then we
                # restore the corresponding notebook defaults only.
                replay_note_command(redo=redo)
                pane.notes.restore_page_setup_metadata(
                    NotesPageSetup.from_dict(metadata)
                    if metadata is not None else None,
                    update_frame=False)
                pane._set_note_page_setup(note_id, metadata)
                pane.schedule_save()

            pane.history.record_applied(external_undo_action(
                'Notes Page Setup',
                lambda: replay(before),
                lambda: replay(after, redo=True), 256))
            return

        # For ordinary typing and formatting, Qt retains the actual
        # text changes; the shared history only records their place.
        pane.history.record_applied(external_undo_action(
            'Edit Notes',
            lambda: replay_note_command(redo=False),
            lambda: replay_note_command(redo=True),
            192))

    def active(self):
        widget = self.tabs.currentWidget()
        return widget if isinstance(widget, ProjectPane) else None

    def _save_current_tab(self):
        pane = self.active()
        if pane:
            pane.save()

    def _update_notebook_progress(self, *, animate=True):
        """One display ratio across all live notebook tabs, without I/O."""
        if not self.notebook:
            self._notebook_progress_label.setText('Notebook: 0 / 0')
            self._notebook_progress_bar.set_progress(0, animate=False, flash=False)
            return
        projects = [self.tabs.widget(i).project
                    for i in range(self.tabs.count())
                    if isinstance(self.tabs.widget(i), ProjectPane)]
        done, total = notebook_totals(projects)
        self._notebook_progress_label.setText(
            f'Notebook: {done:,}/{total:,} · {percentage(done, total)}%'
            if total else 'Notebook: 0 / 0')
        self._notebook_progress_bar.set_progress(
            100.0 * done / total if total else 0,
            animate=animate, flash=animate)

    def _show_focus_reminder(self, message):
        """Show the timer's exact reminder as a non-modal themed card."""
        self.kawaii_notice.show_message(
            message, header_height=self.header.height(),
            reduced_motion=self.brand._reduce_motion)

    def _reading_action(self, pane, level, name, delta):
        """Optional rewards from one manual checkbox change; no saved state.

        Highest priority: entire notebook > tab > group > milestone.
        Unchecks can animate down, but never show confetti or messages.
        """
        if pane is not self.active() or not self.notebook or delta <= 0:
            return
        projects = [self.tabs.widget(i).project for i in range(self.tabs.count())
                    if isinstance(self.tabs.widget(i), ProjectPane)]
        done, total = notebook_totals(projects)
        if not total:
            return
        celebrations = str(self.settings.value('readingCelebrations', 'true')).lower() == 'true'
        milestones = str(self.settings.value('readingMilestones', 'true')).lower() == 'true'
        level_to_show = ''
        label = ''
        if celebrations:
            if done == total:
                level_to_show, label = 'notebook', self.notebook.name
            elif level == 'tab':
                level_to_show = 'tab'
                label = self.tabs.tabText(self.tabs.indexOf(pane)).strip()
            elif level == 'group':
                level_to_show, label = 'group', name
        if level_to_show:
            self._show_reading_reward(celebration_message(level_to_show, label),
                                      tier=level_to_show)
            return
        if milestones:
            threshold = crossed_milestone(done-delta, done, total)
            if threshold is not None:
                self._show_reading_reward(MILESTONE_MESSAGES[threshold],
                                          tier='milestone')

    def _show_reading_reward(self, message, *, tier='group'):
        """Kawaii card sized to the occasion; no modal dialogs or page I/O."""
        intensity = str(self.settings.value('readingCelebrationMotion', 'playful'))
        if intensity not in ('gentle', 'playful', 'none'):
            intensity = 'gentle'
        reduced = self.brand._reduce_motion or intensity == 'none'
        self.kawaii_notice.show_message(
            message, header_height=self.header.height(),
            duration={'group': 3400, 'tab': 5000, 'notebook': 6700,
                      'milestone': 3200}.get(tier, 4000),
            reduced_motion=reduced, playful=(intensity == 'playful'))
        confetti_on = str(self.settings.value('readingConfetti', 'true')).lower() == 'true'
        if tier != 'milestone' and confetti_on and not reduced:
            self.save_confetti.celebrate(
                self.root.rect(), False, at_top=True, tier=tier,
                playful=(intensity == 'playful'), header_height=self.header.height())
            # The overlay is mouse-transparent; the readable card stays above it.
            self.kawaii_notice.raise_()

    def change_tab(self, *_):
        if self._changing_notebook or not self.notebook:
            return
        active = self.active()
        prior = getattr(self, '_last_active_pane', None)
        importing_index = (self.tabs.indexOf(prior) if prior is not None
                           and getattr(prior, '_importing', False) else -1)
        if importing_index >= 0 and importing_index != self.tabs.currentIndex():
            # Never allow the user to switch away from a live import while its
            # worker still copies source assets into that tab's folder.
            self._changing_notebook = True
            try:
                self.tabs.setCurrentIndex(importing_index)
            finally:
                self._changing_notebook = False
            self.statusBar().showMessage('Finish importing before switching tabs.', 3500)
            return
        # Only the previous and new panes need work on a tab switch. Scanning
        # every heavyweight pane on each addition is needlessly quadratic.
        if prior is not None and prior is not active and prior._active:
            if prior._dirty:
                prior.save()
            prior.deactivate()  # releases cached page pixmap/icons
        if active is not None and not active._active:
            active.activate()
        self._last_active_pane = active
        self._sync_navigator_menu_action()
        if active and self.notebook.active_id != active._tab_id:
            self.notebook.active_id = active._tab_id
            # Persist the last selected internal tab promptly, even when
            # notes haven't changed since the previous autosave.
            self.notebook.save()
        self.setWindowTitle(f'{self.notebook.name} — Yomu Note')
        self._update_undo_actions()
        self._update_notebook_progress()

    def _attach_pane(self, tab):
        pane = ProjectPane(self.notebook.project(tab['id']), self.settings)
        pane.history = UnifiedHistory(max_actions=1000,
                                      max_memory_bytes=200 * 1024 * 1024,
                                      sequence_provider=self._next_history_sequence)
        pane.history.on_changed(lambda *_: self._update_undo_actions())
        pane._tab_id = tab['id']
        pane.notes.editor.history_key_handler = (
            lambda redo: self.redo_shared() if redo else self.undo_shared())
        pane.notes.editor.history_availability = (
            lambda: (self._history_target().can_undo,
                     self._history_target(redo=True).can_redo))
        pane.pages_list.tab_id = tab['id']
        pane.pages_list.notebook_id = self.notebook.identifier
        pane.group_tree.tab_id = tab['id']
        pane.group_tree.notebook_id = self.notebook.identifier
        pane.pages_list.pagesPasted.connect(self._transfer_tab_pages)
        pane.on_container_save = lambda p=pane: (
            self.notebook.save() if self.notebook and p.project.path.is_relative_to(self.notebook.workspace)
            else None)
        pane.statusMessage.connect(self.statusBar().showMessage)
        pane.notebookDropped.connect(self.import_notebook_tabs)
        pane.readingChanged.connect(self._update_notebook_progress)
        pane.readingAction.connect(lambda level, name, delta, p=pane:
                                   self._reading_action(p, level, name, delta))
        # Qt owns the history of each native QTextDocument separately.
        # Attach new documents lazily as the user opens new notes pages.
        def connect_document(note_id, document):
            # Bind the document's stable note ID even after page switching;
            # never infer edit history from whichever note is currently open.
            document.undoCommandAdded.connect(
                lambda p=pane, nid=note_id: self._record_text_edit(p, nid))
        pane.on_note_document = connect_document
        connect_document(pane.project.active_note_id, pane.notes.editor.document())
        return pane

    def _retire_notebook(self, notebook, panes):
        """Release an old notebook *after* all of its pane workers finish.

        QTabWidget.clear() only removes tabs; it does not destroy their page
        widgets.  Detached widgets and their QTextDocuments must be disposed,
        but a worker may still be reading their original PDFs.  Keep both
        the widgets and workspace alive until the task completion is delivered.
        """
        for pane in panes:
            if pane._active:
                pane.deactivate()
            pane._closed = True
            pane._save_timer.stop()
            pane.hide()
            pane.setParent(None)
        self._retired_resources.add(notebook, panes)
        self._retirement_timer.start()

    def _drain_retired_resources(self):
        if not self._retired_resources.advance(lambda pane: pane.deleteLater()):
            self._retirement_timer.stop()

    def show_notebook(self, notebook):
        """One open project; all QTabWidget tabs are internal module sections."""
        if self._exchange_busy:
            if notebook is not self.notebook:
                notebook.close()
            raise RuntimeError('Finish exchanging tabs before switching notebooks.')
        if self.notebook and any(self.tabs.widget(i)._importing for i in range(self.tabs.count())):
            notebook.close()
            raise RuntimeError('Finish importing before switching projects.')
        if self.notebook and self.notebook.path == notebook.path:
            if notebook is not self.notebook:
                notebook.close()
            return
        self._changing_notebook = True
        try:
            if self.notebook:
                for i in range(self.tabs.count()):
                    pane = self.tabs.widget(i)
                    if pane._importing:
                        raise RuntimeError('Finish importing before switching projects.')
                    pane.close_project()
                self.notebook.save()
                old = self.notebook
                old_panes = ([self.tabs.widget(i) for i in range(self.tabs.count())]
                             + list(self._parked_panes.values()))
                self.tabs.clear()
                self._retire_notebook(old, old_panes)
            self.notebook = notebook
            self._last_active_pane = None
            self._fallback_history.clear()
            self._notebook_history.clear()
            self._parked_panes.clear()
            self.tabs.clear()
            for tab in notebook.tabs:
                self.tabs.addTab(self._attach_pane(tab), tab['title'])
            self.tabs.setCurrentIndex(next(i for i,t in enumerate(notebook.tabs)
                                           if t['id'] == notebook.active_id))
            self._refresh_tab_buttons()
        finally:
            self._changing_notebook = False
        self.record_recent(notebook.path)
        self.apply_theme()
        self._update_notebook_progress(animate=False)
        self.change_tab()
        self.save_open_tabs()
        self.backup_timer.start()

    def eventFilter(self, watched, event):
        # Files containing whole study tabs must be routed to Tab Exchange
        # even when dropped onto QTextEdit or an internal graphics viewport.
        # Only intercept a SINGLE local .yomunote file inside this window;
        # ordinary PDF/image drops and internal page drags keep their handlers.
        if (event.type() in (QEvent.Type.DragEnter, QEvent.Type.DragMove,
                             QEvent.Type.Drop)
                and isinstance(watched, QWidget)
                and watched.window() is self):
            share = self._notebook_drag_path(event)
            if share:
                event.acceptProposedAction()
                if event.type() == QEvent.Type.Drop:
                    QTimer.singleShot(0, lambda p=share: self.import_notebook_tabs(p))
                return True
        # The tab widget can resize independently of the QMainWindow while its
        # header wraps. Reposition only after Qt has finished its layout pass.
        if watched is self.tabs and event.type() == QEvent.Type.Resize:
            self._queue_inline_tab_plus_layout()
        if (watched is getattr(self, 'root', None)
                and event.type() == QEvent.Type.Resize
                and hasattr(self, 'kawaii_notice')):
            self.kawaii_notice.recenter(self.header.height())
        return super().eventFilter(watched, event)

    def _queue_inline_tab_plus_layout(self):
        if getattr(self, '_tab_plus_layout_pending', False):
            return
        if not hasattr(self, '_tab_plus_corner'):
            return
        self._tab_plus_layout_pending = True
        QTimer.singleShot(0, self._position_inline_tab_plus)

    def _position_inline_tab_plus(self):
        self._tab_plus_layout_pending = False
        if not hasattr(self, '_tab_plus_corner'):
            return
        bar = self.tabs.tabBar()
        # The QWidget corner must NEVER grow with the number/width of tabs.
        # The last tab's rect may be offset when the strip scrolls, so require
        # BOTH a non-overflowing total width and 38px of visible right space.
        total_width = sum(bar.tabRect(i).width() for i in range(bar.count()))
        last_right = bar.mapTo(
            self.tabs, QPoint(bar.tabRect(bar.count() - 1).right()
                               if bar.count() else 0, 0)).x()
        # QTabBar is allowed to keep only its preferred width when few tabs
        # exist, so put the button on the QTabWidget above the empty space,
        # rather than requiring the bar itself to stretch to window width.
        pos = inline_add_position(self.tabs.width(), last_right, total_width)
        if pos is not None:
            self._overflow_add_tab_button.hide()
            self._add_tab_button.move(
                pos, max(0, bar.y() + (bar.height() - 30) // 2))
            self._add_tab_button.show()
            self._add_tab_button.raise_()
        else:
            self._add_tab_button.hide()
            self._overflow_add_tab_button.show()

    def update_tab_title(self, pane, name):
        if not self.notebook:
            return
        index = self.tabs.indexOf(pane)
        if index >= 0:
            self.tabs.setTabText(index, name)
            self._queue_inline_tab_plus_layout()

    def _ensure_tab_delete_button(self, index):
        bar = self.tabs.tabBar()
        if index < 0 or index >= self.tabs.count():
            return
        if bar.tabButton(index, QTabBar.ButtonPosition.RightSide) is not None:
            return
        pane = self.tabs.widget(index)
        btn = TabTrashButton(bar)
        btn.setFixedSize(18, 18)
        btn.setObjectName('tabDeleteButton')
        btn.hovered.connect(lambda p=pane:
            self._show_tab_trash_on_hover(self.tabs.indexOf(p)))
        btn.setAutoRaise(True)
        btn.setToolTip('Delete this project tab (can be undone)')
        btn.clicked.connect(lambda _=False, p=pane: self.delete_tab_by_id(p._tab_id))
        bar.setTabButton(index, QTabBar.ButtonPosition.RightSide, btn)

    def _refresh_tab_buttons(self):
        for i in range(self.tabs.count()):
            self._ensure_tab_delete_button(i)
        self._hovered_tab_button = -1
        self._show_tab_trash_on_hover(getattr(self.tabs.tabBar(), '_hovered', -1))
        self._queue_inline_tab_plus_layout()

    def _show_tab_trash_on_hover(self, hover_index):
        bar = self.tabs.tabBar()
        last = getattr(self, '_hovered_tab_button', -1)
        if last == hover_index:
            return
        for index in (last, hover_index):
            if index < 0 or index >= self.tabs.count():
                continue
            btn = bar.tabButton(index, QTabBar.ButtonPosition.RightSide)
            if btn is not None:
                btn.setIcon(line_icon('trash-2', '#d84058')
                            if index == hover_index else QIcon())
        self._hovered_tab_button = hover_index

    def _dispose_closed_pane(self, pane):
        # Qt workers have an owned QObject receiver. Wait until the last
        # background callback ends before deleting the pane/its receiver.
        if getattr(pane, '_tasks', None):
            QTimer.singleShot(1000, lambda p=pane: self._dispose_closed_pane(p))
        else:
            pane.deleteLater()

    def _resync_notebook_tabs(self):
        """After add/delete/undo, keep existing panes wherever possible."""
        self._changing_notebook = True
        try:
            existing = {self.tabs.widget(i)._tab_id: self.tabs.widget(i)
                        for i in range(self.tabs.count())}
            active_ids = {tab['id'] for tab in self.notebook.tabs}
            for pane in existing.values():
                if pane._tab_id not in active_ids:
                    if pane._active:
                        pane.deactivate()
                    # Keep the *same* QTextDocument if a deleted tab is
                    # brought back by Undo, preserving its native text steps.
                    self._parked_panes[pane._tab_id] = pane
            self.tabs.clear()
            for tab in self.notebook.tabs:
                pane = (existing.get(tab['id'])
                        or self._parked_panes.pop(tab['id'], None)
                        or self._attach_pane(tab))
                pane._closed = False
                self.tabs.addTab(pane, tab['title'])
            index = next(i for i, tab in enumerate(self.notebook.tabs)
                         if tab['id'] == self.notebook.active_id)
            self.tabs.setCurrentIndex(index)
            self._refresh_tab_buttons()
        finally:
            self._changing_notebook = False
        self.change_tab()
        # Only newly attached panes need a theme refresh. Reapplying the
        # entire QApplication stylesheet after every insert/delete caused a
        # costly repaint/layout traversal of every tab and its child widgets.
        for i in range(self.tabs.count()):
            self._theme_one_pane(self.tabs.widget(i))
        self._update_undo_actions()

    def _transfer_tab_pages(self, source_id, target_id, page_ids, copy_pages):
        """Drop onto another tab or paste pages with Ctrl/Command+V.

        Ctrl/Option-drag copies; plain drag moves. Rebuild visible lists using
        the existing page source files; never clone PDF render caches.
        """
        if not self.notebook or source_id == target_id:
            return
        if any(self.tabs.widget(i)._importing for i in range(self.tabs.count())):
            self.statusBar().showMessage('Finish importing before moving or copying pages.', 3500)
            return
        if source_id not in {t['id'] for t in self.notebook.tabs} or target_id not in {t['id'] for t in self.notebook.tabs}:
            return
        try:
            self._save_current_tab()
            count = self.notebook.transfer_pages(source_id, target_id, page_ids,
                                                 move=not copy_pages)
            if not count:
                return
            for i in range(self.tabs.count()):
                pane = self.tabs.widget(i)
                if pane._tab_id in (source_id, target_id):
                    pane.project = self.notebook.project(pane._tab_id)
                    pane.load_pages()
                    if pane._active:
                        pane.schedule_thumbnails()
            self.notebook.save()
            self._update_notebook_progress()
            self.statusBar().showMessage(f'{count} page(s) {"copied" if copy_pages else "moved"} between tabs.', 4000)
        except Exception as exc:
            QMessageBox.warning(self, 'Page transfer failed', str(exc))

    def add_tab(self):
        if self._exchange_busy:
            return
        if not self.notebook:
            return
        name, ok = QInputDialog.getText(self, 'New project tab', 'Tab name:', text='New Notes')
        if not ok or not name.strip():
            return
        self._save_current_tab()
        source_history = self.history  # Record creation in the originating tab.
        try:
            tabid = self.notebook.add_tab(name)
            index = next(i for i, tab in enumerate(self.notebook.tabs) if tab['id'] == tabid)
            entry = dict(self.notebook.tabs[index])
            # A simple insertion is incremental: QTabWidget.clear() followed
            # by re-adding every heavyweight editor/canvas caused large Qt
            # layout and stylesheet cascades as the tab count increased.
            self._changing_notebook = True
            try:
                pane = self._attach_pane(entry)
                self.tabs.insertTab(index, pane, entry['title'])
                self.tabs.setCurrentIndex(index)
                self._ensure_tab_delete_button(index)
                self._theme_one_pane(pane)
            finally:
                self._changing_notebook = False
            self.change_tab()
            self._queue_inline_tab_plus_layout()
            self.notebook.save()
            source_history.record_applied(CallbackAction('Add Tab',
                lambda tid=tabid: self._history_remove_tab(tid),
                lambda idx=index, tab=entry: self._history_restore_tab(idx, tab),
                384))
        except Exception as exc:
            QMessageBox.warning(self, 'Could not add tab', str(exc))

    def rename_tab(self, index):
        if index < 0 or not self.notebook:
            return
        tab = self.notebook.tabs[index]
        name, ok = QInputDialog.getText(self, 'Rename project tab', 'New name:', text=tab['title'])
        if ok and name.strip():
            new = name.strip()[:100]
            if new != tab['title']:
                self._save_current_tab()
                self.tabs.widget(index).history.perform(rename_action(
                    'tab', tab['id'], tab['title'], new, self._apply_tab_title))

    def delete_tab_by_id(self, tabid):
        if self._exchange_busy:
            return
        if not self.notebook:
            return
        if len(self.notebook.tabs) == 1:
            QMessageBox.information(self, 'Last tab', 'A project must contain at least one tab.')
            return
        if any(self.tabs.widget(i)._importing for i in range(self.tabs.count())):
            QMessageBox.information(self, 'Import active', 'Finish importing before deleting a tab.')
            return
        reply = QMessageBox.question(self, 'Delete project tab',
                'You are about to delete a project tab, are you sure?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            cmd = DeleteNotebookTabCommand(self, tabid)
            self._notebook_history.perform(
                CallbackAction('Delete Tab', cmd.undo, cmd.redo, 512))

    def _history_remove_tab(self, tabid):
        self._save_current_tab()
        self.notebook.delete_tab(tabid)
        self._resync_notebook_tabs()
        self.notebook.save()

    def _history_restore_tab(self, index, entry):
        self.notebook.restore_tab(index, entry)
        self._resync_notebook_tabs()
        self.notebook.save()

    def _apply_tab_title(self, tabid, name):
        self.notebook.rename_tab(tabid, name)
        index = next(i for i, tab in enumerate(self.notebook.tabs) if tab['id'] == tabid)
        self.tabs.widget(index).project.name = name
        self.tabs.setTabText(index, name)
        self._queue_inline_tab_plus_layout()
        self.notebook.save()

    def undo_tab_deletion(self):
        self.undo_shared()

    def redo_tab_deletion(self):
        self.redo_shared()

    def show_tab_context_menu(self, position):
        index = self.tabs.tabBar().tabAt(position)
        if index < 0:
            return
        tabid = self.tabs.widget(index)._tab_id
        menu = QMenu(self)
        menu.addAction('Rename Tab…', lambda: self.rename_tab(index))
        menu.addAction('Export This Tab…', lambda: self.export_selected_tabs(tabid))
        menu.addAction('Delete Tab…', lambda: self.delete_tab_by_id(tabid))
        menu.exec(self.tabs.tabBar().mapToGlobal(position))

    def _apply_tab_order(self, ids):
        lookup = {t['id']: t for t in self.notebook.tabs}
        if set(lookup) != set(ids):
            raise ValueError('Tabs have changed since the reorder.')
        self.notebook.tabs = [lookup[tid] for tid in ids]
        self._resync_notebook_tabs()
        self.notebook.save()

    def _on_tab_moved(self, source, destination):
        if not self._changing_notebook and self.notebook:
            before = [t['id'] for t in self.notebook.tabs]
            self.notebook.move_tab(source, destination)
            after = [t['id'] for t in self.notebook.tabs]
            self.notebook.save()
            if before != after:
                self.history.record_applied(CallbackAction('Reorder Tabs',
                    lambda order=before: self._apply_tab_order(order),
                    lambda order=after: self._apply_tab_order(order),
                    256 + 80 * len(before)))
        self._queue_inline_tab_plus_layout()

    def record_recent(self, path):
        path = str(Path(path).expanduser().resolve())
        recents = self.settings.value('recentProjects', [])
        if isinstance(recents, str):
            recents = [recents]
        paths = [path] + [str(Path(p).expanduser().resolve()) for p in (recents or [])
                          if str(Path(p).expanduser().resolve()) != path]
        self.settings.setValue('recentProjects', paths[:5])
        self.settings.setValue('lastOpenDir', str(Path(path).parent))

    def populate_recents(self):
        self.recent_menu.clear()
        paths = self.settings.value('recentProjects', [])
        if isinstance(paths, str):
            paths = [paths]
        for path in (paths or [])[:5]:
            act = self.recent_menu.addAction(Path(path).stem)
            act.setToolTip(path)
            act.triggered.connect(lambda _=False, p=path: self.open_path(p))
        if not paths:
            no_items = self.recent_menu.addAction('No recent projects')
            no_items.setEnabled(False)

    def open_path(self, path):
        """Open a notebook normally, or offer a safe recovery COPY.

        Recovery is opt-in. Invalid annotations may be skipped,
        but the source notebook is left exactly as it was.
        """
        try:
            notebook = Notebook.load(Path(path))
            self.show_notebook(notebook)
        except Exception as exc:
            logger.exception('Could not open notebook')
            answer = QMessageBox.question(
                self, 'Could not open notebook',
                f'{Path(path)}\n\n{exc}\n\n'
                'Try recovering into a new notebook copy?\n'
                'The original will not be changed.',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            try:
                recovered = Notebook.recover_copy(Path(path))
                warnings = list(recovered.recovery_warnings)
                self.show_notebook(recovered)
                details = '\n'.join(warnings[:15]) if warnings else (
                    'The notebook was copied without altering the original.')
                QMessageBox.information(
                    self, 'Recovery copy opened',
                    f'Recovered copy:\n{recovered.path}\n\n{details}\n\n'
                    'Please check your notes and annotations carefully.',
                )
            except Exception as recovery_error:
                logger.exception('Notebook recovery failed')
                QMessageBox.critical(
                    self, 'Recovery could not finish', str(recovery_error))

    def new_project(self):
        start = self.settings.value('lastSaveDir', str(Path.home() / 'Documents'))
        folder = QFileDialog.getExistingDirectory(self, 'Choose project storage folder', start)
        if not folder:
            return
        name, ok = QInputDialog.getText(self, 'New Yomu Note project', 'Project name:', text='New Study Project')
        if ok and name.strip():
            try:
                notebook = Notebook.create(Path(folder), name)
                self.settings.setValue('lastSaveDir', folder)
                self.show_notebook(notebook)
            except Exception as exc:
                QMessageBox.critical(self, 'New project failed', str(exc))

    def open_project(self):
        start = self.settings.value('lastOpenDir', str(Path.home() / 'Documents'))
        path, _ = QFileDialog.getOpenFileName(self, 'Open Yomu Note notebook', start,
                                               'Yomu Note Notebooks (*.yomunote *.yominote)')
        if path:
            self.open_path(path)

    def import_legacy_project(self):
        start = self.settings.value('lastOpenDir', str(Path.home() / 'Documents'))
        folder = QFileDialog.getExistingDirectory(self, 'Import an older Yomu Note project folder', start)
        if folder and (Path(folder) / 'project.json').exists():
            self.open_path(folder)

    def save_project(self):
        pane = self.active()
        if pane and self.notebook:
            try:
                changed = bool(pane._celebrate_on_next_manual_save)
                pane.save()
                self.notebook.save()
                self.settings.setValue('lastSaveDir', str(self.notebook.path.parent))
                if changed:
                    pane._celebrate_on_next_manual_save = False
                    self.statusBar().showMessage('Notes saved locally!', 3500)
                    self.save_toast.show_for(self.root.rect())
                    self.save_confetti.celebrate(self.root.rect(),
                        str(self.settings.value('reducedMotion', 'false')).lower() == 'true')
                else:
                    self.statusBar().showMessage('Already saved · no new changes ♡', 2500)
            except Exception as exc:
                QMessageBox.critical(self, 'Save failed', str(exc))

    def export_clean_notebook(self):
        """Export a privacy-cleaned copy without modifying the original.

        Every tab is saved before the background database copy.
        A cleaned copy does not contain deleted SQLite records.
        Existing older backups are NOT changed by this action.
        """
        if not self.notebook:
            return
        if getattr(self, '_clean_export_running', False):
            return
        if any(self.tabs.widget(i)._importing for i in range(self.tabs.count())):
            QMessageBox.information(self, 'Import in progress',
                                    'Finish importing before exporting a copy.')
            return
        destination, _ = QFileDialog.getSaveFileName(
            self, 'Export clean notebook for sharing',
            str(self.notebook.path.with_name(
                self.notebook.path.stem + ' Clean Copy.yomunote')),
            'Yomu Note Notebook (*.yomunote)',
        )
        if not destination:
            return
        try:
            # Save all open tabs first so the copy includes recent work.
            for index in range(self.tabs.count()):
                self.tabs.widget(index).save()
            self.notebook.save()
        except Exception as exc:
            QMessageBox.critical(self, 'Could not prepare clean copy', str(exc))
            return
        source = Path(self.notebook.path)
        target = Path(destination)
        self._clean_export_running = True
        self.statusBar().showMessage('Creating clean notebook copy…')

        def worker():
            return Notebook.create_clean_share_copy(source, target)

        def finished(result, error):
            self._clean_export_running = False
            if error:
                QMessageBox.warning(self, 'Clean export failed', str(error))
                return
            QMessageBox.information(
                self, 'Clean notebook copy created',
                f'Cleaned copy saved to:\n{result}\n\n'
                'Deleted file records were excluded and unused SQLite '
                'pages were compacted.\n\n'
                'Old backups are separate and may still contain '
                'previously removed documents.',
            )

        # The potentially lengthy VACUUM runs off the GUI thread.
        start_task(self, worker, finished, priority=1)

    def _begin_exchange(self, message):
        """Keep the window non-interactive while large assets stream off-thread."""
        self._exchange_busy = True
        self._exchange_cancel = threading.Event()
        progress = QProgressDialog(message, 'Cancel', 0, 0, self)
        progress.setWindowTitle('Yomu Note · Tab Exchange')
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.canceled.connect(self._exchange_cancel.set)
        self._exchange_progress = progress
        progress.show()
        self.statusBar().showMessage(message)
        return self._exchange_cancel

    def _end_exchange(self):
        progress = self._exchange_progress
        self._exchange_progress = None
        self._exchange_cancel = None
        self._exchange_busy = False
        if progress is not None:
            progress.close()
            progress.deleteLater()

    def _save_tabs_for_exchange(self):
        if any(self.tabs.widget(i)._importing for i in range(self.tabs.count())):
            raise RuntimeError('Finish importing documents before exchanging tabs.')
        # This covers dirty INACTIVE editor panes too, not just the current one.
        for i in range(self.tabs.count()):
            self.tabs.widget(i).save()
        self.notebook.save()

    def import_notebook_tabs(self, source_path=None):
        """Inspect a share, let the user select tabs, then import atomically."""
        if not self.notebook or self._exchange_busy:
            return
        if isinstance(source_path, bool) or not source_path:
            source_path, _ = QFileDialog.getOpenFileName(
                self, 'Import tabs from another Yomu Note notebook',
                str(self.settings.value('lastOpenDir', str(Path.home()))),
                'Yomu Note Notebooks (*.yomunote *.yominote)')
        if not source_path:
            return
        path = Path(source_path).expanduser().resolve()
        try:
            self._save_tabs_for_exchange()
            tabs = inspect_notebook(path)
        except Exception as exc:
            QMessageBox.warning(self, 'Cannot inspect shared notebook', str(exc))
            return
        dialog = TabExchangeDialog(tabs, action='import',
                                   source_name=path.name, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        ids = dialog.selected_ids()
        if not ids:
            return
        if len(self.notebook.tabs) + len(ids) > MAX_TABS:
            QMessageBox.warning(self, 'Too many tabs',
                f'Only {MAX_TABS - len(self.notebook.tabs)} more tabs fit in this notebook.')
            return
        destination_nb = self.notebook
        used_titles = tuple(t['title'] for t in destination_nb.tabs)
        cancel = self._begin_exchange('Importing selected tabs in the background…')

        def worker():
            return stage_import(path, ids, destination_nb.workspace,
                                used_titles, cancel)

        def finished(result, error):
            try:
                if error:
                    if not cancel.is_set():
                        QTimer.singleShot(0, lambda msg=str(error):
                            QMessageBox.warning(self, 'Tab import failed', msg))
                    return
                stage, entries = result
                if cancel.is_set():
                    shutil.rmtree(stage, ignore_errors=True)
                    return
                if destination_nb is not self.notebook:
                    shutil.rmtree(stage, ignore_errors=True)
                    return
                try:
                    index = len(destination_nb.tabs)
                    imported = commit_import(destination_nb, stage, entries)
                    # Create one notebook-level history entry only AFTER the
                    # entire batch is durable. Persist edits before Undo.
                    def hide_batch():
                        ids_to_hide = {t['id'] for t in imported}
                        for i in range(self.tabs.count()):
                            pane = self.tabs.widget(i)
                            if pane._tab_id in ids_to_hide:
                                pane.save()
                        set_batch_present(destination_nb, imported, False)
                        self._resync_notebook_tabs()

                    def show_batch():
                        set_batch_present(destination_nb, imported, True, index)
                        self._resync_notebook_tabs()

                    # Attach widgets successfully BEFORE registering Undo. A
                    # Qt construction error must not leave an un-undoable
                    # partial batch in the receiving notebook.
                    try:
                        self._resync_notebook_tabs()
                        self._notebook_history.record_applied(CallbackAction(
                            f'Import {len(imported)} Tab(s)', hide_batch,
                            show_batch, 512 + 160 * len(imported)))
                    except Exception:
                        set_batch_present(destination_nb, imported, False)
                        self._resync_notebook_tabs()
                        raise
                    self.statusBar().showMessage(
                        f'{len(imported)} shared tab(s) imported · one Undo removes all ♡', 6000)
                except Exception as exc:
                    QTimer.singleShot(0, lambda msg=str(exc):
                        QMessageBox.warning(self, 'Could not finish tab import', msg))
            finally:
                self._end_exchange()

        start_task(self, worker, finished, priority=1)

    def export_selected_tabs(self, default_id=None):
        """Write a clean standalone .yomunote with ONLY selected live tabs."""
        if not self.notebook or self._exchange_busy:
            return
        if isinstance(default_id, bool):
            default_id = None
        try:
            self._save_tabs_for_exchange()
            all_tabs = inspect_notebook(self.notebook.path)
        except Exception as exc:
            QMessageBox.warning(self, 'Cannot prepare tab export', str(exc))
            return
        preselect = ((default_id,) if default_id else
                     (self.notebook.active_id,))
        dialog = TabExchangeDialog(all_tabs, action='export',
                                   source_name=self.notebook.name,
                                   preselect=preselect, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        ids = dialog.selected_ids()
        if not ids:
            return
        suggested = self.notebook.path.with_name(
            self.notebook.path.stem + ' Shared Tabs.yomunote')
        dest, _ = QFileDialog.getSaveFileName(
            self, 'Save selected tabs as a separate notebook',
            str(suggested), 'Yomu Note Notebooks (*.yomunote)')
        if not dest:
            return
        target = Path(dest).expanduser().resolve()
        if target.suffix.lower() != '.yomunote':
            target = target.with_suffix('.yomunote')
        if target.exists():
            QMessageBox.warning(self, 'Choose a new filename',
                                'Tab export never overwrites another notebook.')
            return
        source = Path(self.notebook.path)
        cancel = self._begin_exchange('Exporting selected tabs in the background…')
        def worker():
            return export_tabs(source, target, ids, cancel)
        def finished(result, error):
            try:
                if error:
                    if not cancel.is_set():
                        QTimer.singleShot(0, lambda msg=str(error):
                            QMessageBox.warning(self, 'Tab export failed', msg))
                elif cancel.is_set():
                    # A late cancellation cannot undo a completed atomic export.
                    self.statusBar().showMessage('Tab export completed before cancellation.', 5000)
                else:
                    self.statusBar().showMessage(
                        f'Shared {len(ids)} tab(s) to {Path(result).name} ♡', 6000)
                    notice = (f'New independent notebook created:\n{result}\n\n'
                              'The original notebook is unchanged. Only the selected '
                              'tabs and their live documents/notes were included.')
                    QTimer.singleShot(0, lambda msg=notice:
                        QMessageBox.information(self, 'Tab notebook exported', msg))
            finally:
                self._end_exchange()
        start_task(self, worker, finished, priority=1)

    @staticmethod
    def _notebook_drag_path(event):
        urls = event.mimeData().urls() if event.mimeData().hasUrls() else []
        return (urls[0].toLocalFile() if len(urls) == 1 and urls[0].isLocalFile()
                and Path(urls[0].toLocalFile()).suffix.lower() in
                ('.yomunote', '.yominote') else None)

    def dragEnterEvent(self, event):
        if self._notebook_drag_path(event):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if self._notebook_drag_path(event):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        path = self._notebook_drag_path(event)
        if path:
            event.acceptProposedAction()
            QTimer.singleShot(0, lambda p=path: self.import_notebook_tabs(p))
        else:
            super().dropEvent(event)

    def import_files(self):
        if self.active():
            self.active().choose_files()

    def save_copy_as(self):
        if not self.notebook:
            return
        self._save_current_tab()
        self.notebook.save()
        target, _ = QFileDialog.getSaveFileName(self, 'Save project copy',
            str(self.notebook.path.with_name(self.notebook.path.stem + ' Copy.yomunote')),
            'Yomu Note Notebook (*.yomunote)')
        if target:
            try:
                dest = Path(target)
                if dest.exists():
                    raise FileExistsError('Choose a new file name to protect your existing project.')
                Notebook.restore_copy(self.notebook.path, dest)
                self.open_path(dest)
            except Exception as exc:
                QMessageBox.warning(self, 'Copy failed', str(exc))

    def close_tab(self, index):
        if 0 <= index < self.tabs.count():
            self.delete_tab_by_id(self.tabs.widget(index)._tab_id)

    def close_current(self):
        if self._exchange_busy:
            QMessageBox.information(self, 'Tab exchange active',
                                    'Finish or cancel the tab exchange before closing.')
            return
        if self.notebook:
            if any(self.tabs.widget(i)._importing for i in range(self.tabs.count())):
                QMessageBox.information(self, 'Import active', 'Finish importing before closing the project.')
                return
            self._save_current_tab()
            self.notebook.save()
            self._changing_notebook = True
            try:
                old = self.notebook
                visible = [self.tabs.widget(i) for i in range(self.tabs.count())]
                old_panes = visible + list(self._parked_panes.values())
                for pane in visible:
                    # Inactive panes are ordinarily saved on tab switch, but
                    # close must also cover programmatic edits to hidden tabs.
                    # Deleted/parked tabs are not included in the saved file.
                    if pane._dirty and not pane._closed:
                        pane.save()
                self.tabs.clear()
                self._retire_notebook(old, old_panes)
                self.notebook = None
                self._last_active_pane = None
                self._fallback_history.clear()
                self._notebook_history.clear()
                self._parked_panes.clear()
                self.backup_timer.stop()
                self.save_open_tabs()
            finally:
                self._changing_notebook = False
            self.setWindowTitle('Yomu Note')
            self._update_notebook_progress(animate=False)

    def save_open_tabs(self):
        self.settings.setValue('openProjects', [str(self.notebook.path)] if self.notebook else [])

    def _periodic_backup(self):
        """Every 10 min, snapshot only if changed since the previous backup."""
        if not self.notebook:
            return
        try:
            pane = self.active()
            if pane and pane._dirty:
                pane.save()
            self.notebook.save()
            if self.notebook.backup_dirty:
                directory = Path(str(self.settings.value('backupDirectory', default_backup_folder())))
                limit = int(self.settings.value('backupCount', 30))
                output = self.notebook.backup(directory, limit)
                if output:
                    self.statusBar().showMessage('Quiet recovery backup saved ♡', 2400)
        except Exception as exc:
            self.statusBar().showMessage(f'Backup could not finish: {exc}', 5500)

    def restore_backup(self):
        folder = str(self.settings.value('backupDirectory', default_backup_folder()))
        original, _ = QFileDialog.getOpenFileName(self, 'Select a Yomu recovery backup', folder,
                                                  'Yomu Note Notebooks (*.yomunote *.yominote)')
        if not original:
            return
        suggested = str((self.notebook.path if self.notebook else Path(folder)/'Recovered.yomunote')
                         .with_name('Recovered ' + Path(original).stem + '.yomunote'))
        destination, _ = QFileDialog.getSaveFileName(self, 'Restore backup to a NEW project file',
            suggested, 'Yomu Note Notebook (*.yomunote)')
        if not destination:
            return
        try:
            output = Notebook.restore_copy(Path(original), Path(destination))
            self.open_path(output)
        except Exception as exc:
            QMessageBox.warning(self, 'Restore failed', str(exc))

    def _theme_one_pane(self, pane):
        colours = getattr(self, 'current_palette', THEMES['washi'])
        pane.pages_list._hover_delegate.accent = QColor(colours['accent'])
        pane.pages_list._hover_delegate.ink = QColor(colours['ink'])
        pane.group_tree.set_accent(colours['accent'])
        pane.canvas.setBackgroundBrush(QBrush(QColor(colours['preview'])))
        for panel in (pane.shelf, pane.canvas_panel, pane.notes_backdrop):
            panel.set_theme_colours(colours)
        pane._theme_annotation_quick_edit(colours)
        pane._theme_annotation_toolbar(colours)

    def apply_theme(self):
        palette_name = self.theme
        if palette_name == 'system':
            try:
                palette_name = 'modern-dark' if QApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark else 'modern-light'
            except AttributeError:
                palette_name = 'modern-light'
        colours = THEMES.get(palette_name, THEMES['washi'])
        self.current_palette = colours
        app = QApplication.instance()
        # Set Qt's native widget colours BEFORE the global stylesheet.
        # New dialogs now inherit the same palette automatically.
        app.setPalette(application_palette(colours))
        app.setStyleSheet(stylesheet(colours))
        self.brand.set_palette(colours['accent'], colours['accent2'], colours['muted'])
        # Re-tint tiny SVG toolbar icons for legibility on dark themes.
        for button in QApplication.instance().allWidgets():
            if isinstance(button, QToolButton) and button.property('yomuIcon'):
                button.setIcon(line_icon(button.property('yomuIcon'), colours['ink']))
        self.button_motion.set_accent(colours['accent'])
        for i in range(self.tabs.count()):
            self._theme_one_pane(self.tabs.widget(i))
        self.focus_flower.colour = QColor(colours['accent'])
        self.focus_flower.update()
        self.kawaii_notice.set_palette(colours)
        self._queue_inline_tab_plus_layout()

    def set_theme(self, theme):
        self.theme = theme
        self.settings.setValue('theme', theme)
        self.apply_theme()

    def show_preferences(self):
        """A scrollable preferences window; its Save/Cancel buttons stay visible."""
        dialog = QDialog(self)
        dialog.setWindowTitle('Yomu Note Preferences')
        dialog.resize(460, 560)
        outer = QVBoxLayout(dialog)
        scroll = QScrollArea(dialog)
        scroll.setObjectName('preferencesScroll')
        # QScrollArea paints through a separate viewport widget. Name it so
        # Windows dark-mode palette can't leak into a light Yomu preference.
        scroll.viewport().setObjectName('preferencesViewport')
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        content.setObjectName('preferencesContent')
        content.setAutoFillBackground(True)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(7)
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)
        layout.addWidget(QLabel('Appearance'))
        theme = QComboBox()
        theme.addItems(list(THEME_NAMES.values()))
        theme.setCurrentIndex(list(THEME_NAMES).index(self.theme))
        layout.addWidget(theme)
        layout.addWidget(QLabel('Default notes style (applies to new notes only)'))
        font = QFontComboBox()
        font.setFontFilters(QFontComboBox.FontFilter.ScalableFonts)
        font.setCurrentFont(QFont(self.settings.value('defaultFont', 'Nunito')))
        layout.addWidget(font)
        size = QSpinBox()
        size.setRange(7, 120)
        size.setValue(int(self.settings.value('defaultFontSize', 13)))
        size.setSuffix(' pt')
        layout.addWidget(size)
        bold = QCheckBox('Bold by default')
        bold.setChecked(str(self.settings.value('defaultBold', 'false')).lower() == 'true')
        layout.addWidget(bold)
        italic = QCheckBox('Italic by default')
        italic.setChecked(str(self.settings.value('defaultItalic', 'false')).lower() == 'true')
        layout.addWidget(italic)
        align = QComboBox()
        align.addItems(['Left', 'Centre', 'Right', 'Justify'])
        align.setCurrentText(self.settings.value('defaultAlignment', 'Left'))
        layout.addWidget(QLabel('Default paragraph alignment'))
        layout.addWidget(align)
        web_link = QCheckBox('Show website link button in the notes toolbar')
        web_link.setChecked(str(self.settings.value('showWebLink', 'false')).lower() == 'true')
        layout.addWidget(web_link)
        jump_edit = QCheckBox('Show Jump to Edit Position button in notes toolbar')
        jump_edit.setChecked(str(self.settings.value('showJumpEditPosition', 'false')).lower() == 'true')
        layout.addWidget(jump_edit)
        reduced = QCheckBox('Reduce animations (no moving logo gradient, confetti or scroll drift)')
        reduced.setChecked(str(self.settings.value('reducedMotion', 'false')).lower() == 'true')
        layout.addWidget(reduced)
        layout.addWidget(QLabel('Reading rewards · gentle encouragement'))
        reading_celebrations = QCheckBox('Show Kawaii celebrations for completed groups, tabs and notebooks')
        reading_celebrations.setChecked(str(self.settings.value('readingCelebrations', 'true')).lower() == 'true')
        layout.addWidget(reading_celebrations)
        reading_confetti = QCheckBox('Show petals and confetti on completion')
        reading_confetti.setChecked(str(self.settings.value('readingConfetti', 'true')).lower() == 'true')
        layout.addWidget(reading_confetti)
        reading_milestones = QCheckBox('Show notebook milestones at 25%, 50% and 75%')
        reading_milestones.setChecked(str(self.settings.value('readingMilestones', 'true')).lower() == 'true')
        layout.addWidget(reading_milestones)
        layout.addWidget(QLabel('Celebration motion'))
        reading_motion = QComboBox()
        for title, value in [('Gentle', 'gentle'),
                             ('Playful (default)', 'playful'),
                             ('None — static messages only', 'none')]:
            reading_motion.addItem(title, value)
        reading_motion.setCurrentIndex(max(0, reading_motion.findData(
            self.settings.value('readingCelebrationMotion', 'playful'))))
        layout.addWidget(reading_motion)
        layout.addWidget(QLabel('Small PDF text clarity (zoomed-out preview only)'))
        clarity = QComboBox()
        clarity.addItem('Off — unmodified Lanczos result', 'off')
        clarity.addItem('Gentle — subtle contrast-aware text edges', 'gentle')
        clarity.addItem('Crisp — stronger clarity (default)', 'crisp')
        clarity_mode = str(self.settings.value('previewClarity', 'crisp')).lower()
        clarity.setCurrentIndex(max(0, clarity.findData(clarity_mode)))
        clarity.setToolTip('Only the current page below 100%; at most 1.5 MP, in memory. '
                           'No new cache files or document changes.')
        layout.addWidget(clarity)
        layout.addWidget(QLabel('Reading view memory'))
        shared_zoom = QCheckBox('Share zoom across pages in the same root group')
        shared_zoom.setChecked(str(self.settings.value('readingViewSharedZoom', 'true')).lower() == 'true')
        layout.addWidget(shared_zoom)
        remember_scroll = QCheckBox('Remember each page’s reading position')
        remember_scroll.setChecked(str(self.settings.value('readingViewRememberScroll', 'true')).lower() == 'true')
        layout.addWidget(remember_scroll)
        persist_view = QCheckBox('Restore reading positions and zoom when reopening notebooks')
        persist_view.setChecked(str(self.settings.value('readingViewPersist', 'true')).lower() == 'true')
        layout.addWidget(persist_view)
        start_top = QCheckBox('Start previously unvisited pages at the top')
        start_top.setChecked(str(self.settings.value('readingViewStartAtTop', 'true')).lower() == 'true')
        layout.addWidget(start_top)
        layout.addWidget(QLabel('Yomu Focus · gentle chiptune sounds in E♭ major'))
        focus_sounds = QCheckBox('Play original 3-second jingles when sessions end')
        focus_sounds.setChecked(str(self.settings.value('focusSounds', 'true')).lower() == 'true')
        layout.addWidget(focus_sounds)
        focus_repeat = QCheckBox('Repeat the reminder once a minute (stop after 10 minutes)')
        focus_repeat.setChecked(str(self.settings.value('focusRepeat', 'true')).lower() == 'true')
        layout.addWidget(focus_repeat)
        volume_line = QHBoxLayout()
        volume_line.addWidget(QLabel('Jingle volume'))
        focus_volume = QSpinBox()
        focus_volume.setRange(0, 100)
        focus_volume.setSuffix(' %')
        focus_volume.setValue(int(self.settings.value('focusVolume', 45)))
        focus_volume.setToolTip('Jingle playback volume; 0% is silent.')
        volume_line.addWidget(focus_volume)
        layout.addLayout(volume_line)
        layout.addWidget(QLabel('Yomu Focus · session durations (minutes)'))
        durations = QHBoxLayout()
        session_spins = []
        for title, key, default in [('Focus', 'pomodoroFocus', 25),
                                    ('Short', 'pomodoroShort', 5),
                                    ('Long', 'pomodoroLong', 15)]:
            block = QVBoxLayout()
            block.addWidget(QLabel(title))
            spin = QSpinBox(); spin.setRange(1, 180)
            spin.setValue(int(self.settings.value(key, default)))
            block.addWidget(spin)
            durations.addLayout(block)
            session_spins.append((key, spin))
        layout.addLayout(durations)
        layout.addWidget(QLabel('Project recovery · rotating 10-minute backups'))
        backup_dir = QLineEdit(str(self.settings.value('backupDirectory', default_backup_folder())))
        backup_dir.setToolTip('User-writable folder for dated portable project backups (no caches).')
        folder_row = QHBoxLayout()
        folder_row.addWidget(backup_dir, 1)
        choose_backup = QPushButton('Browse…')
        def choose_backup_folder():
            path = QFileDialog.getExistingDirectory(dialog, 'Choose recovery backup folder', backup_dir.text())
            if path:
                backup_dir.setText(path)
        choose_backup.clicked.connect(choose_backup_folder)
        folder_row.addWidget(choose_backup)
        layout.addLayout(folder_row)
        backup_count = QSpinBox()
        backup_count.setRange(1, 100)
        backup_count.setValue(int(self.settings.value('backupCount', 30)))
        backup_count.setToolTip('Keep at most this many dated recovery snapshots per project.')
        layout.addWidget(QLabel('Number of backups kept per project'))
        layout.addWidget(backup_count)
        layout.addWidget(QLabel('PDF pages are loaded on demand; caches remain disposable.'))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        outer.addWidget(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.set_theme(list(THEME_NAMES)[theme.currentIndex()])
            self.settings.setValue('defaultFont', font.currentFont().family())
            self.settings.setValue('defaultFontSize', size.value())
            self.settings.setValue('defaultBold', bold.isChecked())
            self.settings.setValue('defaultItalic', italic.isChecked())
            self.settings.setValue('defaultAlignment', align.currentText())
            self.settings.setValue('showWebLink', web_link.isChecked())
            self.settings.setValue('showJumpEditPosition', jump_edit.isChecked())
            self.settings.setValue('reducedMotion', reduced.isChecked())
            self.settings.setValue('readingCelebrations', reading_celebrations.isChecked())
            self.settings.setValue('readingConfetti', reading_confetti.isChecked())
            self.settings.setValue('readingMilestones', reading_milestones.isChecked())
            self.settings.setValue('readingCelebrationMotion', reading_motion.currentData())
            self.settings.setValue('previewClarity', clarity.currentData())
            self.settings.setValue('readingViewSharedZoom', shared_zoom.isChecked())
            self.settings.setValue('readingViewRememberScroll', remember_scroll.isChecked())
            self.settings.setValue('readingViewPersist', persist_view.isChecked())
            self.settings.setValue('readingViewStartAtTop', start_top.isChecked())
            self.settings.setValue('backupDirectory', backup_dir.text().strip() or str(default_backup_folder()))
            self.settings.setValue('backupCount', backup_count.value())
            self.settings.setValue('focusSounds', focus_sounds.isChecked())
            self.settings.setValue('focusRepeat', focus_repeat.isChecked())
            self.settings.setValue('focusVolume', focus_volume.value())
            self.focus_timer.set_sound_preferences(focus_sounds.isChecked(),
                focus_repeat.isChecked(), focus_volume.value())
            self.focus_timer.reduced_motion = reduced.isChecked()
            for key, spin in session_spins:
                self.settings.setValue(key, spin.value())
            self.focus_timer.update_durations(*(spin.value() for _, spin in session_spins))
            self.brand.set_reduced_motion(reduced.isChecked())
            self.button_motion.reduced_motion = reduced.isChecked()
            self.save_toast.reduced_motion = reduced.isChecked()
            self._notebook_progress_bar.set_reduced_motion(reduced.isChecked())
            for i in range(self.tabs.count()):
                pane = self.tabs.widget(i)
                pane.reading_progress.set_reduced_motion(reduced.isChecked())
                pane.group_tree.set_reading_reduced_motion(reduced.isChecked())
                pane.pages_list._hover_delegate.anim.setDuration(0 if reduced.isChecked() else 180)
                for panel in (pane.shelf, pane.canvas_panel, pane.notes_backdrop):
                    panel.set_reduce_motion(reduced.isChecked())
                pane.notes.set_web_link_visible(web_link.isChecked())
                pane.notes.set_jump_edit_visible(jump_edit.isChecked())
                pane.update_preview_clarity()

    def show_about(self):
        """Open a lightweight popup that dismisses on outside click or Escape."""
        if getattr(self, '_about_popup', None) and self._about_popup.isVisible():
            self._about_popup.close()
            return
        popup = QFrame(self, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        popup.setObjectName('aboutPopup')
        c = self.current_palette
        popup.setStyleSheet(f"QFrame#aboutPopup {{ background: {c['panel']}; color: {c['ink']}; "
                            f"border: 1px solid {c['accent']}; border-radius: 16px; }}")
        popup.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        # QWidget popups normally close when users click away; Escape also
        # dismisses the window without affecting the current project.
        escape = QShortcut(QKeySequence('Escape'), popup)
        escape.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        escape.activated.connect(popup.close)
        popup._escape_shortcut = escape
        layout = QVBoxLayout(popup)
        layout.setContentsMargins(24,20,24,20)
        layout.setSpacing(9)
        for text, style in [('Yomu ❤︎', 'font-size: 25px; font-weight: bold;'),
                            ('べんきょうして！', 'font-size: 13px;'),
                            (f'Yomu Note  ·  v{__version__}', 'font-size: 14px; font-weight: bold;'),
                            ('A cosy offline space for reading and learning ✿', 'font-size: 12px;'),
                            ('Designed by Nova O’Reilly!', 'font-size: 13px; font-weight: bold;')]:
            label = QLabel(text)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet(style)
            layout.addWidget(label)
        popup.adjustSize()
        top = self.brand.mapToGlobal(QPoint(0, self.brand.height()+3))
        popup.move(top)
        self._about_popup = popup
        popup.destroyed.connect(lambda *_: setattr(self, '_about_popup', None))
        popup.show()

    def closeEvent(self, event):
        if self._exchange_busy:
            QMessageBox.information(self, 'Tab exchange active',
                                    'Finish or cancel the tab exchange before quitting.')
            event.ignore()
            return
        if any(self.tabs.widget(i)._importing for i in range(self.tabs.count())):
            QMessageBox.information(self, 'Import active', 'Finish importing before closing Yomu Note.')
            event.ignore()
            return
        try:
            for i in range(self.tabs.count()):
                self.tabs.widget(i).save()
            if self.notebook:
                self.notebook.save()
            self.save_open_tabs()
            event.accept()
        except Exception as exc:
            QMessageBox.critical(self, 'Could not save before exit', str(exc))
            event.ignore()
