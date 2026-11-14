"""Protect against the duplicate event-handler bug in v0.6.7a.

This source-level test is useful when PySide6 is unavailable.
It prevents a second mouseReleaseEvent definition from silently
replacing the table-resize completion handler again.
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EDITOR = (ROOT / 'yomunote/editor.py').read_text(encoding='utf8')
TABLES = (ROOT / 'yomunote/notes_tables.py').read_text(encoding='utf8')


def method(cls_name, name):
    tree = ast.parse(EDITOR)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls_name)
    methods = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == name]
    assert len(methods) == 1, (cls_name, name, [m.lineno for m in methods])
    return ast.get_source_segment(EDITOR, methods[0])


def test_only_one_mouse_release_event_and_it_finishes_resizing():
    handler = method('LinkTextEdit', 'mouseReleaseEvent')
    assert "handler('release', event.position())" in handler
    assert 'self.linkActivated.emit(link)' in handler
    assert 'self.clear_table_interaction()' in handler


def test_no_explicit_mouse_capture_and_bounded_watchdog():
    assert 'grabMouse()' not in EDITOR
    assert 'releaseMouse()' not in EDITOR
    assert 'editor.viewport().grabMouse()' not in TABLES
    assert 'editor.viewport().releaseMouse()' not in TABLES
    clear = method('LinkTextEdit', 'clear_table_interaction')
    assert 'self._table_drag_watchdog.stop()' in clear
    assert 'self._table_drag = None' in clear
    watch = method('LinkTextEdit', '_finish_table_drag_if_mouse_released')
    assert 'QApplication.mouseButtons()' in watch
    assert "handler('release', QPointF(cursor_position))" in watch
    assert 'self.clear_table_interaction()' in watch
    hide = method('LinkTextEdit', 'hideEvent')
    assert 'self.clear_table_interaction()' in hide


def test_table_deletion_uses_qt_native_rows_in_one_edit_block():
    tree = ast.parse(TABLES)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'TableTools')
    delete = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'delete_table')
    code = ast.get_source_segment(TABLES, delete)
    assert 'table.removeRows(0, rows)' in code
    assert 'self._perform(apply, keep_cursor=False)' in code
    assert 'self.editor.clear_table_interaction()' in code
    assert 'table.rows()' in code
    assert "'Delete entire table'" in TABLES
    assert 'delete_empty_table_at_caret' in TABLES


def test_legacy_tables_can_explicitly_enable_column_resizing():
    assert 'def initialise_percentage_widths(' in TABLES
    assert 'self.equalise_columns(table=table)' in TABLES
