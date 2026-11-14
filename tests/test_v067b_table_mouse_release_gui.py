"""Desktop regression tests for v0.6.7b table input and deletion.

IMPORTANT: These test the actual QWidget mouse release path.
Earlier tests called TableTools.handle_pointer('release') directly,
which missed a second mouseReleaseEvent replacing the first one.

To run this file on Windows, install development requirements
and run: python -m pytest -q tests/test_v067b_table_mouse_release_gui.py
"""
import pytest
pytest.importorskip('PySide6.QtTest')
from PySide6.QtCore import Qt, QPoint, QPointF
from PySide6.QtGui import QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from yomunote.editor import NotesEditor
from yomunote.notes_tables import table_guide_geometry


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def notes(app):
    widget = NotesEditor()
    widget.resize(860, 640)
    widget.show()
    app.processEvents()
    yield widget
    widget.close()
    app.processEvents()


def make_table(notes, rows=3, columns=2):
    notes.editor.setPlainText('Before the table\n')
    cursor = notes.editor.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    table = cursor.insertTable(rows, columns, notes.tables.new_format(columns))
    notes.editor.setTextCursor(table.cellAt(0, 0).firstCursorPosition())
    QApplication.processEvents()
    return table


def test_actual_widget_mouse_release_commits_column_widths(notes):
    table = make_table(notes)
    geometry = table_guide_geometry(notes.editor, table)
    assert geometry is not None
    _, xs, ys = geometry
    start = notes.editor.viewport()
    p = QPoint(round(xs[1]), round((ys[0] + ys[-1]) / 2))
    destination = QPoint(p.x() + 35, p.y())
    QTest.mousePress(start, Qt.MouseButton.LeftButton, pos=p)
    QApplication.processEvents()
    assert notes.editor._table_drag is not None
    # Simulate movement without editing the document before release.
    notes.tables.handle_pointer('move', QPointF(destination))
    QTest.mouseRelease(start, Qt.MouseButton.LeftButton, pos=destination)
    QApplication.processEvents()
    assert notes.editor._table_drag is None
    assert not notes.editor._table_drag_watchdog.isActive()
    after = notes.editor.textCursor().currentTable()
    assert after is not None
    widths = notes.tables._percentage_widths(after)
    assert widths is not None and widths[0] > 50.0
    assert 'Before the table' in notes.editor.toPlainText()


def test_hide_editor_cancels_drag_without_grabbing_mouse(notes):
    table = make_table(notes)
    geometry = table_guide_geometry(notes.editor, table)
    assert geometry is not None
    _, xs, ys = geometry
    assert notes.tables.handle_pointer(
        'press', QPointF(xs[1], (ys[0] + ys[-1]) / 2))
    assert notes.editor._table_drag is not None
    notes.editor.hide()
    assert notes.editor._table_drag is None
    assert not notes.editor._table_drag_watchdog.isActive()
    notes.editor.show()
    QApplication.processEvents()


def test_delete_table_undo_and_save_excludes_deleted_text(notes):
    table = make_table(notes)
    secret = 'YOMU_SECRET_CELL_807349'
    writer = table.cellAt(0, 0).firstCursorPosition()
    writer.insertText(secret)
    notes.editor.setTextCursor(table.cellAt(0, 0).firstCursorPosition())
    assert notes.tables.delete_table()
    assert secret not in notes.html()
    assert 'Before the table' in notes.html()
    notes.editor.undo()
    assert secret in notes.html()
    notes.editor.redo()
    assert secret not in notes.html()


def test_backspace_deletes_completely_empty_table_only(notes):
    table = make_table(notes)
    notes.editor.setTextCursor(table.cellAt(0, 0).firstCursorPosition())
    notes.editor.setFocus()
    QTest.keyClick(notes.editor, Qt.Key.Key_Backspace)
    assert '<table' not in notes.html().lower()
    assert 'Before the table' in notes.editor.toPlainText()
