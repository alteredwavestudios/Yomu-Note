"""Platform-aware shortcut labels and OS checks, independent of Qt.

Qt translates the logical Ctrl modifier to Command on macOS. For display,
we choose macOS glyphs or the literal Windows/Linux key names instead of
hardcoding Command signs into labels everywhere.
"""
from __future__ import annotations
import sys

IS_MAC = sys.platform == 'darwin'
IS_WINDOWS = sys.platform.startswith('win')
IS_LINUX = sys.platform.startswith('linux')
PRIMARY = '⌘' if IS_MAC else 'Ctrl'
ALT = '⌥' if IS_MAC else 'Alt'
SHIFT = '⇧' if IS_MAC else 'Shift'

def shortcut_label(sequence: str) -> str:
    """Convert a Qt portable shortcut into a readable platform-native hint.

    This is a presentation helper; QKeySequence continues to own the actual
    shortcut mapping. E.g. Ctrl+Shift+. becomes ⌘⇧. or Ctrl+Shift+.
    """
    if not IS_MAC:
        return sequence
    parts = sequence.split('+')
    if sequence.endswith('++'):
        # A literal PLUS key makes split('+') produce empty fields.
        # Keep that final key instead of showing only Command.
        parts = [part for part in parts if part] + ['+']
    modifiers = {'Ctrl': '⌘', 'Alt': '⌥', 'Shift': '⇧', 'Meta': '⌃'}
    return ''.join(modifiers.get(part, part) for part in parts)

def docs_shortcut(action: str) -> str:
    """Canonical Google Docs-compatible shortcuts for tooltips and menus."""
    bindings = {
        'larger_font': 'Ctrl+Shift+.', 'smaller_font': 'Ctrl+Shift+,',
        'bold': 'Ctrl+B', 'italic': 'Ctrl+I', 'underline': 'Ctrl+U',
        'strike': 'Ctrl+Shift+X' if IS_MAC else 'Alt+Shift+5',
        'left': 'Ctrl+Shift+L', 'centre': 'Ctrl+Shift+E',
        'right': 'Ctrl+Shift+R', 'justify': 'Ctrl+Shift+J',
        'numbered': 'Ctrl+Shift+7', 'bulleted': 'Ctrl+Shift+8',
        'indent': 'Ctrl+]', 'outdent': 'Ctrl+[',
        'page_link': 'Ctrl+K', 'web_link': 'Ctrl+Alt+K',
        'find': 'Ctrl+F', 'find_next': 'Ctrl+G',
        'find_previous': 'Ctrl+Shift+G',
        'notes_zoom_in': 'Ctrl++', 'notes_zoom_out': 'Ctrl+-',
        'notes_zoom_reset': 'Ctrl+0',
        'import': 'Ctrl+Shift+I',
        'insert_table': 'Ctrl+Shift+T',
        'table_row_before': 'Ctrl+Alt+Shift+Up',
        'table_row_after': 'Ctrl+Alt+Shift+Down',
        'table_column_before': 'Ctrl+Alt+Shift+Left',
        'table_column_after': 'Ctrl+Alt+Shift+Right',
        'table_delete_row': 'Ctrl+Alt+Shift+R',
        'table_delete_column': 'Ctrl+Alt+Shift+C',
    }
    return shortcut_label(bindings[action])
