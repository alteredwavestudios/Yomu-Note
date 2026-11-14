"""Checks that run without PySide6, for the v0.6.7c table hotfix.

These are structure checks, not substitutes for a Windows mouse test.
They prevent the specific regressions found in earlier releases.
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TABLES = (ROOT / 'yomunote/notes_tables.py').read_text(encoding='utf8')
EDITOR = (ROOT / 'yomunote/editor.py').read_text(encoding='utf8')
SHORTCUTS = (ROOT / 'yomunote/platform_shortcuts.py').read_text(encoding='utf8')


def method(source, cls, name):
    tree = ast.parse(source)
    klass = next(x for x in tree.body if isinstance(x, ast.ClassDef)
                 and x.name == cls)
    function = next(x for x in klass.body if isinstance(x, ast.FunctionDef)
                    and x.name == name)
    return ast.get_source_segment(source, function)


def test_table_indent_changes_frame_only_and_stays_undoable():
    code = method(TABLES, 'TableTools', 'change_table_indent')
    assert 'fmt.setLeftMargin(target)' in code
    assert 'self._perform(apply)' in code
    assert 'table.setFormat(fmt)' in code
    assert 'cellAt(' not in code
    assert 'setColumnWidthConstraints' not in code
    assert '_TABLE_INDENT_STEP = 18.0' in TABLES


def test_table_menu_is_labelled_and_contains_indent_actions():
    code = method(TABLES, 'TableTools', 'build_menu')
    assert "QMenu('Edit Table', parent or self.notes)" in code
    assert 'Indent whole table right' in code
    assert 'Outdent whole table left' in code
    assert 'Delete entire table' in code


def test_row_and_column_delete_shortcuts_share_canonical_labels():
    assert "'table_delete_row': 'Ctrl+Alt+Shift+R'" in SHORTCUTS
    assert "'table_delete_column': 'Ctrl+Alt+Shift+C'" in SHORTCUTS
    shortcuts = method(EDITOR, 'NotesEditor', 'setup_shortcuts')
    assert "'Ctrl+Alt+Shift+R': self.tables.remove_row" in shortcuts
    assert "'Ctrl+Alt+Shift+C': self.tables.remove_column" in shortcuts
    menu = method(TABLES, 'TableTools', 'build_menu')
    assert 'docs_shortcut("table_delete_row")' in menu
    assert 'docs_shortcut("table_delete_column")' in menu
    assert 'Delete row:' in EDITOR and 'Delete column:' in EDITOR


def test_explicit_corner_selection_is_required_to_delete_whole_table():
    selected = method(TABLES, 'TableTools', 'select_table')
    deletion = method(TABLES, 'TableTools', 'delete_empty_table_at_caret')
    assert '_table_selected_range' in selected
    assert 'selected_by_corner' in deletion
    assert 'actual_range == selected_range[1:]' in deletion
    assert 'cursor.hasComplexSelection()' in deletion
    assert '0, table.rows(), 0, table.columns()' in deletion
    assert 'return False' in deletion


def test_cell_selection_uses_qt_documented_tuple_order():
    code = method(TABLES, 'TableTools', '_selected_cells')
    assert 'row, rows, col, cols = result' in code
    assert 'return (row, col, rows, cols)' in code


def test_no_double_mouse_release_handler_regression():
    tree = ast.parse(EDITOR)
    klass = next(x for x in tree.body if isinstance(x, ast.ClassDef)
                 and x.name == 'LinkTextEdit')
    count = sum(isinstance(x, ast.FunctionDef)
                and x.name == 'mouseReleaseEvent' for x in klass.body)
    assert count == 1
