"""GUI regression tests for the stale-QTextTable crash.

Run on Windows or with QT_QPA_PLATFORM=offscreen.
Unlike source checks, these create live Qt document objects.
"""
import pytest
pytest.importorskip('PySide6.QtWidgets')

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QApplication

from yomunote.editor import NotesEditor
from yomunote.notes_tables import (
    table_guide_geometry, table_interaction_hit,
    _table_at_position,
)


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def notes(app):
    widget = NotesEditor()
    widget.resize(840, 560)
    widget.show()
    app.processEvents()
    yield widget
    widget.close()


def make_table(notes):
    cursor = notes.editor.textCursor()
    table = cursor.insertTable(3, 2, notes.tables.new_format(2))
    notes.editor.setTextCursor(table.cellAt(0, 0).firstCursorPosition())
    return table


def test_table_geometry_does_not_move_when_cell_text_is_centred(notes, app):
    table = make_table(notes)
    cell = table.cellAt(0, 0)
    writer = cell.firstCursorPosition()
    writer.insertText('Alignment test')
    notes.editor.setTextCursor(cell.firstCursorPosition())
    app.processEvents()
    baseline = table_guide_geometry(notes.editor, table)
    assert baseline is not None
    for alignment in (Qt.AlignmentFlag.AlignHCenter,
                      Qt.AlignmentFlag.AlignRight,
                      Qt.AlignmentFlag.AlignLeft):
        notes.editor.setAlignment(alignment)
        app.processEvents()
        current = notes.editor.textCursor().currentTable()
        shape = table_guide_geometry(notes.editor, current)
        assert shape is not None
        assert abs(shape[0].left() - baseline[0].left()) <= 2.0
        assert len(shape[1]) == len(baseline[1])
        assert all(abs(a-b) <= 2.0 for a,b in zip(
            shape[1], baseline[1]))


def test_hover_table_is_not_retained_after_document_replacement(notes, app):
    table = make_table(notes)
    app.processEvents()
    frame, xs, ys = table_guide_geometry(notes.editor, table)
    mid = QPointF(xs[1], (ys[0] + ys[-1]) / 2)
    notes.tables.handle_pointer('move', mid)
    assert notes.editor._table_hover_position is not None
    notes.editor.setPlainText('Table has been replaced')
    assert notes.editor._table_hover_position is None
    assert notes.editor._table_drag is None
    assert not notes.editor.viewport().grab().isNull()


def test_drag_cancels_after_document_edit_and_clears_guide(notes, app):
    table = make_table(notes)
    app.processEvents()
    frame, xs, ys = table_guide_geometry(notes.editor, table)
    p = QPointF(xs[1], (ys[0] + ys[-1]) / 2)
    assert notes.tables.handle_pointer('press', p)
    assert notes.editor._table_drag is not None
    notes.editor.setAlignment(Qt.AlignmentFlag.AlignRight)
    assert notes.editor._table_drag is None
    assert notes.editor._table_hover_position is None
    assert not notes.editor.viewport().grab().isNull()


def test_release_resizes_and_removes_drag_preview(notes, app):
    table = make_table(notes)
    app.processEvents()
    frame, xs, ys = table_guide_geometry(notes.editor, table)
    p = QPointF(xs[1], (ys[0] + ys[-1]) / 2)
    position = table.cellAt(0, 0).firstCursorPosition().position()
    assert notes.tables.handle_pointer('press', p)
    assert notes.tables.handle_pointer(
        'move', QPointF(p.x()+30, p.y()))
    assert notes.tables.handle_pointer(
        'release', QPointF(p.x()+30, p.y()))
    assert notes.editor._table_drag is None
    assert notes.editor._table_hover_position is None
    current = _table_at_position(notes.editor, position)
    assert current is not None
    assert current.format().columnWidthConstraints()[0].rawValue() > 50
