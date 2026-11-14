"""Desktop-only Qt regression tests for v0.6.7c.

On Windows, from the extracted source folder run:
    python -m pytest -q tests/test_v067c_table_polish_gui.py

These require PySide6. The headless build machine skips them.
"""
import pytest

pytest.importorskip('PySide6.QtTest')

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from yomunote.editor import NotesEditor


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def notes(app):
    widget = NotesEditor()
    widget.resize(850, 650)
    widget.show()
    app.processEvents()
    yield widget
    widget.close()
    app.processEvents()


def make_table(notes, rows=3, cols=2):
    notes.editor.setPlainText('Paragraph before\n')
    writer = notes.editor.textCursor()
    writer.movePosition(QTextCursor.MoveOperation.End)
    table = writer.insertTable(rows, cols, notes.tables.new_format(cols))
    notes.editor.setTextCursor(table.cellAt(0, 0).firstCursorPosition())
    QApplication.processEvents()
    return table


def current_table(notes):
    document = notes.editor.document()
    block = document.firstBlock()
    while block.isValid():
        table = QTextCursor(block).currentTable()
        if table is not None:
            return table
        block = block.next()
    return None


def test_indent_is_one_undo_and_preserves_cell_text(notes):
    table = make_table(notes)
    table.cellAt(0, 0).firstCursorPosition().insertText('KEEP_ME')
    notes.editor.setTextCursor(table.cellAt(0, 0).firstCursorPosition())
    original = table.format().leftMargin()
    widths = notes.tables._percentage_widths(table)
    assert notes.tables.indent_table_right()
    QApplication.processEvents()
    table = current_table(notes)
    assert abs(table.format().leftMargin() - original - 18.0) < 0.1
    assert notes.tables._percentage_widths(table) == widths
    assert 'KEEP_ME' in notes.editor.toPlainText()
    notes.editor.undo()
    QApplication.processEvents()
    table = current_table(notes)
    assert abs(table.format().leftMargin() - original) < 0.1
    notes.editor.redo()
    QApplication.processEvents()
    table = current_table(notes)
    assert abs(table.format().leftMargin() - original - 18.0) < 0.1


def test_corner_selected_table_delete_and_undo(notes):
    table = make_table(notes)
    table.cellAt(0, 0).firstCursorPosition().insertText('SENSITIVE_TEST_VALUE')
    notes.editor.setTextCursor(table.cellAt(0, 0).firstCursorPosition())
    notes.tables.select_table(table)
    assert notes.editor._table_selected_range is not None
    QTest.keyClick(notes.editor, Qt.Key.Key_Delete)
    QApplication.processEvents()
    assert 'SENSITIVE_TEST_VALUE' not in notes.html()
    assert 'Paragraph before' in notes.html()
    notes.editor.undo()
    assert 'SENSITIVE_TEST_VALUE' in notes.html()
    notes.editor.redo()
    assert 'SENSITIVE_TEST_VALUE' not in notes.html()


def test_delete_shortcuts_leave_other_table_cells(notes):
    table = make_table(notes)
    table.cellAt(0, 0).firstCursorPosition().insertText('ROW0')
    table.cellAt(1, 0).firstCursorPosition().insertText('ROW1')
    notes.editor.setTextCursor(table.cellAt(1, 0).firstCursorPosition())
    notes.editor.setFocus()
    QTest.keyClick(notes.editor, Qt.Key.Key_R,
                   Qt.KeyboardModifier.ControlModifier |
                   Qt.KeyboardModifier.AltModifier |
                   Qt.KeyboardModifier.ShiftModifier)
    QApplication.processEvents()
    assert 'ROW0' in notes.editor.toPlainText()
    assert 'ROW1' not in notes.editor.toPlainText()
    assert current_table(notes).rows() == 2
    notes.editor.undo()
    assert 'ROW1' in notes.editor.toPlainText()


def test_right_click_menu_title_is_visible(notes):
    table = make_table(notes)
    notes.editor.setTextCursor(table.cellAt(0, 0).firstCursorPosition())
    menu = notes.tables.build_menu(notes, include_insert=False)
    assert menu.title() == 'Edit Table'
    labels = [a.text() for a in menu.actions()]
    assert any('Delete current row' in label for label in labels)
    assert any('Delete current column' in label for label in labels)
    menu.deleteLater()


def test_table_indent_survives_html_round_trip(notes):
    table = make_table(notes)
    notes.editor.setTextCursor(table.cellAt(0, 0).firstCursorPosition())
    assert notes.tables.indent_table_right()
    saved = notes.html()
    notes.set_html(saved)
    QApplication.processEvents()
    loaded = current_table(notes)
    assert loaded is not None
    assert abs(loaded.format().leftMargin() - 18.0) < 0.1


def test_corner_delete_empty_single_cell_table(notes):
    table = make_table(notes, rows=1, cols=1)
    notes.tables.select_table(table)
    QTest.keyClick(notes.editor, Qt.Key.Key_Delete)
    QApplication.processEvents()
    assert '<table' not in notes.html().lower()
    notes.editor.undo()
    assert '<table' in notes.html().lower()


def test_delete_inside_cell_does_not_remove_table(notes):
    table = make_table(notes)
    writer = table.cellAt(0, 0).firstCursorPosition()
    writer.insertText('MUST_STAY')
    cursor = table.cellAt(0, 0).firstCursorPosition()
    cursor.movePosition(QTextCursor.MoveOperation.Right,
                        QTextCursor.MoveMode.KeepAnchor)
    notes.editor.setTextCursor(cursor)
    QTest.keyClick(notes.editor, Qt.Key.Key_Delete)
    QApplication.processEvents()
    assert current_table(notes) is not None
