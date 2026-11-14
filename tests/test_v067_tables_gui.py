"""Qt-only integration checks for native table sizing and selection.

Run on Windows/macOS with PySide6, or CI under an offscreen Qt
platform. These exercise actual QTextTable and Undo semantics.
"""
import pytest
pytest.importorskip('PySide6.QtWidgets')

from PySide6.QtCore import QPointF
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QApplication

from yomunote.editor import NotesEditor
from yomunote.notes_tables import table_guide_geometry, table_corner_rect


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def notes(app):
    widget = NotesEditor()
    widget.resize(760, 550)
    widget.show()
    app.processEvents()
    yield widget
    widget.close()


def new_table(notes):
    cursor = notes.editor.textCursor()
    table = cursor.insertTable(3, 2, notes.tables.new_format(2))
    notes.editor.setTextCursor(table.cellAt(0, 0).firstCursorPosition())
    return table


def test_table_insert_above_left_preserves_other_cells(notes):
    table = new_table(notes)
    first = table.cellAt(0, 0).firstCursorPosition()
    writing = QTextCursor(first)
    writing.insertText('KEEP_THIS')
    notes.editor.setTextCursor(first)
    notes.tables.add_row_above()
    assert table.rows() == 4
    assert 'KEEP_THIS' in notes.html()
    notes.tables.add_column_left()
    assert table.columns() == 3
    assert 'KEEP_THIS' in notes.html()
    notes.editor.undo()
    assert table.columns() == 2
    notes.editor.undo()
    assert table.rows() == 3
    assert 'KEEP_THIS' in notes.html()


def test_column_resize_is_one_native_undo(notes):
    table = new_table(notes)
    notes.tables.set_column_widths(table, [35, 65])
    assert [round(x.rawValue()) for x in table.format().columnWidthConstraints()] == [35, 65]
    notes.editor.undo()
    assert [round(x.rawValue()) for x in table.format().columnWidthConstraints()] == [50, 50]
    notes.editor.redo()
    assert [round(x.rawValue()) for x in table.format().columnWidthConstraints()] == [35, 65]
    assert 'border="' not in notes.html() or table.format().border() == 0


def test_row_extra_space_changes_native_cell_padding(notes):
    table = new_table(notes)
    notes.tables.set_row_extra_space(table, 1, 24.0)
    assert abs(notes.tables.row_extra_space(table, 1) - 24.0) < 0.1
    notes.editor.undo()
    assert notes.tables.row_extra_space(table, 1) < 0.1
    notes.editor.redo()
    assert abs(notes.tables.row_extra_space(table, 1) - 24.0) < 0.1
    html = notes.html()
    restored = NotesEditor()
    try:
        restored.set_html(html)
        doc = restored.editor.document()
        block = doc.firstBlock()
        while block.isValid():
            probe = QTextCursor(block).currentTable()
            if probe is not None:
                assert abs(restored.tables.row_extra_space(probe, 1) - 24.0) < 0.1
                break
            block = block.next()
        else:
            pytest.fail('HTML roundtrip did not contain a table')
    finally:
        restored.close()


def test_corner_selects_whole_table_without_changing_html(notes, app):
    table = new_table(notes)
    app.processEvents()
    geometry = table_guide_geometry(notes.editor, table)
    assert geometry is not None
    frame, xs, ys = geometry
    assert len(xs) == 3 and len(ys) == 4
    original = notes.html()
    corner = table_corner_rect(frame).center()
    assert notes.tables.handle_pointer('press', corner)
    assert notes.editor.textCursor().hasSelection()
    assert notes.html() == original


def test_drag_preview_does_not_edit_until_release(notes, app):
    table = new_table(notes)
    app.processEvents()
    geo = table_guide_geometry(notes.editor, table)
    assert geo is not None
    _, xs, ys = geo
    middle = QPointF(xs[1], (ys[0] + ys[-1]) / 2)
    original = notes.html()
    assert notes.tables.handle_pointer('press', middle)
    assert notes.tables.handle_pointer('move', QPointF(middle.x() + 30, middle.y()))
    assert notes.html() == original
    assert notes.tables.handle_pointer('release', QPointF(middle.x() + 30, middle.y()))
    widths = table.format().columnWidthConstraints()
    assert widths[0].rawValue() > 50
    notes.editor.undo()
    assert round(table.format().columnWidthConstraints()[0].rawValue()) == 50
