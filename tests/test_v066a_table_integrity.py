"""Test table-boundary maths without a graphical desktop.

The most important rule is that cell text alignment must
never determine a table column's physical boundary.
"""
import ast
from pathlib import Path

from yomunote.table_grid import (
    grid_segments, proportional_column_edges, would_cut_merged_cell,
)

ROOT = Path(__file__).resolve().parents[1]
TABLES = (ROOT / 'yomunote/notes_tables.py').read_text('utf-8')


def test_column_edges_follow_proportions_not_text_cursor():
    assert proportional_column_edges(10, 210, [25, 75]) == [10.0, 60, 210.0]
    assert proportional_column_edges(0, 100, [1, 1, 2]) == [0.0, 25, 50, 100.0]
    assert proportional_column_edges(0, 100, [0, 1]) == []
    assert proportional_column_edges(0, 100, [float('nan'), 1]) == []


def test_grid_edges_are_drawn_once():
    owners = [['a', 'b'], ['c', 'd'], ['e', 'f']]
    segments = grid_segments(owners, [0, 80, 200], [0, 30, 75, 100])
    assert segments.count((80, 0, 80, 100)) == 1
    assert segments.count((0, 30, 200, 30)) == 1
    assert segments.count((0, 75, 200, 75)) == 1
    assert len(segments) == 3


def test_merged_cells_have_no_false_interior_boundaries():
    owners = [['big', 'big'], ['left', 'right']]
    segments = grid_segments(owners, [0, 100, 200], [0, 30, 90])
    assert (100, 0, 100, 90) not in segments
    assert (100, 30, 100, 90) in segments
    assert (0, 30, 200, 30) in segments


def test_merges_must_not_be_partially_deleted():
    vertically_merged = [['a', 'b'], ['a', 'c']]
    assert would_cut_merged_cell(vertically_merged, 'row', 0)
    assert would_cut_merged_cell(vertically_merged, 'row', 1)
    assert not would_cut_merged_cell(vertically_merged, 'column', 1)
    horizontally_merged = [['a', 'a'], ['b', 'c']]
    assert would_cut_merged_cell(horizontally_merged, 'column', 0)
    assert would_cut_merged_cell(horizontally_merged, 'column', 1)
    assert not would_cut_merged_cell(horizontally_merged, 'row', 0)


def test_deletion_is_native_undoable_not_html_replacement():
    assert 'table.removeRows(target_row, 1)' in TABLES
    assert 'table.removeColumns(target_col, 1)' in TABLES
    assert 'writer.beginEditBlock()' in TABLES
    assert 'writer.endEditBlock()' in TABLES
    assert 'keep_cursor=False' in TABLES
    assert '_safe_to_delete(' in TABLES
    assert 'equalise_columns(preserve=False, table=table)' not in TABLES
    assert 'table.setFormat(' in TABLES
    assert 'setHtml(' not in TABLES
    assert 'self.editor.setTextCursor(' in TABLES
    ast.parse(TABLES)


def test_guides_use_constraints_not_cell_text_x():
    geometry = TABLES.split('def table_guide_geometry(', 1)[1].split(
        'def table_corner_rect(', 1)[0]
    guides = TABLES.split('def paint_table_guides(', 1)[1]
    assert 'columnWidthConstraints()' in geometry
    assert 'proportional_column_edges(' in geometry
    assert 'grid_segments(' in guides
    # v0.6.7a: the viewport transform must not use a caret X.
    assert 'dx = -editor.horizontalScrollBar().value()' in geometry
    assert 'cursorRect(pos).left()' not in geometry
    assert 'painter.drawRect(frame.adjusted(' in guides
    assert 'painter.drawLine' in guides
    assert 'table.setFormat(' not in guides
