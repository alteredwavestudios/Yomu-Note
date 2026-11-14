"""Table sizing geometry and UI wiring checks without Qt installed.

All functions in table_grid.py are plain Python maths. A failed
assertion here is a real width-calculation regression, not a Qt
widget or operating-system problem.
"""
import ast
from pathlib import Path

from yomunote.table_grid import (
    resize_adjacent_percentages, closest_table_edge,
    proportional_column_edges,
)

ROOT = Path(__file__).resolve().parents[1]
TABLES = (ROOT / 'yomunote/notes_tables.py').read_text('utf8')
EDITOR = (ROOT / 'yomunote/editor.py').read_text('utf8')
WINDOW = (ROOT / 'yomunote/window.py').read_text('utf8')
SHORTCUTS = (ROOT / 'yomunote/platform_shortcuts.py').read_text('utf8')


def test_resizing_changes_only_adjacent_columns():
    original = [20, 30, 50]
    changed = resize_adjacent_percentages(original, 1, 10)
    assert changed == [30, 20, 50]
    assert original == [20, 30, 50]  # never edit inputs in place
    assert resize_adjacent_percentages([20, 30, 50], 2, -15) == [20, 15, 65]
    assert sum(changed) == 100


def test_extreme_drag_clamps_without_overwriting_other_columns():
    assert resize_adjacent_percentages([25, 25, 50], 1, 900) == [45, 5, 50]
    assert resize_adjacent_percentages([25, 25, 50], 1, -900) == [5, 45, 50]
    assert resize_adjacent_percentages([50], 1, 5) is None
    assert resize_adjacent_percentages([20, 0, 80], 1, 5) is None
    assert proportional_column_edges(0, 400, [25, 25, 50]) == [0, 100, 200, 400]


def test_handle_hit_testing_excludes_outer_column_borders():
    edges = [20, 100, 240]
    assert closest_table_edge(98, edges) == 1
    assert closest_table_edge(19, edges) is None
    assert closest_table_edge(241, edges) is None
    assert closest_table_edge(240, edges, include_final=True) == 2


def test_drag_is_preview_only_until_mouse_release():
    method = TABLES.split('def handle_pointer(', 1)[1].split(
        '@staticmethod\n    def _owners(', 1)[0]
    move = method.split("if phase == 'move' and drag is not None:", 1)[1].split(
        "if phase == 'release' and drag is not None:", 1)[0]
    release = method.split("if phase == 'release' and drag is not None:", 1)[1]
    assert "drag['preview'] =" in move
    assert 'self.set_column_widths' not in move
    assert 'self.set_row_extra_space' not in move
    assert 'self.set_column_widths' in release
    assert 'self.set_row_extra_space' in release
    assert 'self._perform(' in TABLES
    assert 'table.setFormat(fmt)' in TABLES


def test_table_has_selection_handle_and_native_row_extra_space():
    assert 'def select_table(' in TABLES
    assert 'cursor.setPosition(last.position(), QTextCursor.MoveMode.KeepAnchor)' in TABLES
    assert 'def table_corner_rect(' in TABLES
    assert 'def set_row_extra_space(' in TABLES
    assert 'fmt.setBottomPadding(points)' in TABLES
    assert 'def table_properties(' in TABLES
    assert 'self._perform(apply, keep_cursor=False)' in TABLES
    assert 'setHtml(' not in TABLES


def test_shortcuts_and_tooltips_are_consistent():
    for key in ('insert_table', 'table_row_before', 'table_row_after',
                'table_column_before', 'table_column_after'):
        assert f"'{key}':" in SHORTCUTS
        assert f'docs_shortcut("{key}")' in TABLES + EDITOR
    assert "'Ctrl+Shift+T': self.tables.insert_table" in EDITOR
    assert "'Ctrl+Alt+Shift+Up': self.tables.add_row_above" in EDITOR
    assert 'self.editor.table_pointer_handler = self.tables.handle_pointer' in EDITOR
    assert "self.navigator_previous.setToolTip(" in WINDOW
    assert "self.navigator_next.setToolTip(" in WINDOW
    assert "self.preview_previous.setToolTip(" in WINDOW
    assert "self.preview_next.setToolTip(" in WINDOW
    ast.parse(TABLES)
    ast.parse(EDITOR)
