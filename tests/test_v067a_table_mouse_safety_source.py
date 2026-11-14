"""Safety checks for the v0.6.7a table hover/drag hotfix.

These work without PySide6. They inspect the source so a
future refactor cannot quietly restore stale table pointers.
The Qt integration tests exercise real QWidget behaviour.
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TABLES = (ROOT / 'yomunote/notes_tables.py').read_text('utf8')
EDITOR = (ROOT / 'yomunote/editor.py').read_text('utf8')


def test_hover_and_drag_store_positions_not_qt_table_wrappers():
    assert 'from shiboken6 import isValid' in TABLES
    assert 'def _live_table(table)' in TABLES
    assert 'def _table_at_position(editor, position)' in TABLES
    assert 'def _drag_table(editor, drag)' in TABLES
    assert 'editor._table_hover_position = start_position' in TABLES
    assert "'table_position': start_position" in TABLES
    assert "'edit_serial': editor._table_edit_serial" in TABLES
    assert "'table': table" not in TABLES
    assert 'editor._table_hover = table' not in TABLES
    assert 'self._table_hover = None' not in EDITOR


def test_alignment_never_sets_coordinate_system_from_text_caret():
    geometry = TABLES.split('def table_guide_geometry(', 1)[1].split(
        '\ndef table_corner_rect(', 1)[0]
    assert 'layout.frameBoundingRect(table).translated(dx, dy)' in geometry
    assert 'dx = -editor.horizontalScrollBar().value()' in geometry
    assert 'dy = -editor.verticalScrollBar().value()' in geometry
    assert 'screen_rect = editor.cursorRect(first_cursor)' not in geometry


def test_end_of_drag_discards_preview_without_explicit_mouse_grab():
    handler = TABLES.split('def handle_pointer(', 1)[1].split(
        '    @staticmethod\n    def _owners(', 1)[0]
    assert "if phase == 'release' and drag is not None:" in handler
    assert 'editor.clear_table_interaction()' in handler
    assert 'editor.viewport().grabMouse()' not in handler
    assert 'self.set_column_widths(table, drag[' in handler
    assert 'self.set_row_extra_space(' in handler
    assert 'if _drag_table(editor, drag) is None:' in handler
    assert 'def clear_table_interaction(self)' in EDITOR
    assert 'self.viewport().releaseMouse()' not in EDITOR
    assert 'self.document().contentsChange.connect(' in EDITOR
    assert 'self.clear_table_interaction()' in EDITOR
    ast.parse(TABLES)
    ast.parse(EDITOR)
