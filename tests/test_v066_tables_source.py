"""Source checks for native tables when GUI libraries are unavailable.

These checks are not a substitute for the Qt tests below.
They protect the intended architecture and release scope.
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TABLES = (ROOT / 'yomunote/notes_tables.py').read_text('utf-8')
EDITOR = (ROOT / 'yomunote/editor.py').read_text('utf-8')
UI = (ROOT / 'yomunote/ui.py').read_text('utf-8')


def test_new_table_is_native_and_borderless():
    assert 'QTextTableFormat()' in TABLES
    assert 'fmt.setBorder(1.0 if borders else 0.0)' in TABLES
    assert 'fmt.setCellPadding(_DEFAULT_PADDING)' in TABLES
    assert 'fmt.setCellSpacing(0.0)' in TABLES
    assert 'cursor.insertTable(rows, columns, fmt)' in TABLES
    assert 'QTextLength.Type.PercentageLength' in TABLES


def test_table_navigation_and_editing_are_contextual():
    assert 'table.appendRows(1)' in TABLES
    assert 'table.insertRows(target, 1)' in TABLES
    assert 'table.insertColumns(target, 1)' in TABLES
    assert 'table.cellAt' in TABLES
    assert 'table.mergeCells(*selected)' in TABLES
    assert 'table.splitCell(' in TABLES
    assert 'self.editor.table_tab_handler = self.tables.handle_tab' in EDITOR
    assert 'key in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab)' in EDITOR
    assert 'self.tables.build_menu(self)' in EDITOR
    assert "'table':" in UI


def test_temporary_guides_are_paint_only():
    guide = TABLES.split('def paint_table_guides(', 1)[1]
    assert 'painter.drawRect(frame.adjusted(' in guide
    assert 'painter.drawLine' in guide
    assert 'table.setFormat(' not in guide
    assert 'setHtml(' not in guide
    assert 'self.editor.table_context_provider' in EDITOR
    assert 'paint_table_guides(self, painter)' in EDITOR


def test_table_cells_do_not_inherit_regular_paragraph_gaps():
    assert 'in_cell = QTextCursor(block).currentTable() is not None' in EDITOR
    assert 'expected = (0.0 if in_cell else' in EDITOR
    assert 'after if not in_cell and (' in EDITOR
    assert 'self._clear_cell_spacing(table)' in TABLES


def test_editor_preserves_view_without_restoring_old_caret():
    assert 'def preserve_view_state(self, callback, *, restore_cursor=True)' in EDITOR
    assert 'editor.preserve_view_state(perform, restore_cursor=keep_cursor)' in TABLES
    assert 'self._perform(apply, keep_cursor=False)' in TABLES
    ast.parse(TABLES)
    ast.parse(EDITOR)
