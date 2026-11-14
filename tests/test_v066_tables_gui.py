"""Desktop integration tests for native QTextTable editing.

Requires PySide6. Use QT_QPA_PLATFORM=offscreen in CI.
"""
import pytest
pytest.importorskip('PySide6.QtWidgets')

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QApplication, QDialog
from PySide6.QtTest import QTest

from yomunote.editor import NotesEditor
from yomunote.notes_tables import InsertTableDialog
from yomunote.notes_layout import NotesPageSetup


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def notes(app):
    editor = NotesEditor()
    editor.resize(650, 480)
    editor.show()
    app.processEvents()
    yield editor
    editor.close()


def insert_default(notes, monkeypatch):
    # Accept the real dialog with its unmodified 3 x 2 defaults.
    monkeypatch.setattr(InsertTableDialog, 'exec',
                        lambda self: QDialog.DialogCode.Accepted)
    notes.tables.insert_table()
    return notes.editor.textCursor().currentTable()


def test_table_creation_and_round_trip(notes, monkeypatch, app):
    notes.editor.setPlainText('Before\nAfter')
    cursor = notes.editor.textCursor()
    cursor.setPosition(7)
    notes.editor.setTextCursor(cursor)
    table = insert_default(notes, monkeypatch)
    assert table is not None
    assert table.rows() == 3 and table.columns() == 2
    assert table.format().border() == 0.0
    assert table.format().cellPadding() == 4.0
    assert table.format().cellSpacing() == 0.0
    assert table.cellAt(0, 0).firstCursorPosition().block().blockFormat().bottomMargin() == 0.0
    assert notes.editor.textCursor().currentTable() is not None
    html = notes.html()
    assert '<table' in html.lower()
    replacement = NotesEditor()
    replacement.set_html(html)
    try:
        doc = replacement.editor.document()
        cursor = QTextCursor(doc)
        block = doc.firstBlock()
        while block.isValid() and not QTextCursor(block).currentTable():
            block = block.next()
        assert block.isValid()
        restored = QTextCursor(block).currentTable()
        assert restored.rows() == 3 and restored.columns() == 2
        assert restored.format().border() == 0.0
    finally:
        replacement.close()


def test_tab_navigation_adds_row_and_shift_tab_moves_back(notes, monkeypatch, app):
    table = insert_default(notes, monkeypatch)
    notes.editor.setFocus()
    notes.editor.setTextCursor(table.cellAt(0, 0).firstCursorPosition())
    QTest.keyClick(notes.editor, Qt.Key.Key_Tab)
    assert table.cellAt(notes.editor.textCursor()).column() == 1
    QTest.keyClick(notes.editor, Qt.Key.Key_Backtab)
    assert table.cellAt(notes.editor.textCursor()).column() == 0
    notes.editor.setTextCursor(table.cellAt(2, 1).firstCursorPosition())
    QTest.keyClick(notes.editor, Qt.Key.Key_Tab)
    app.processEvents()
    assert table.rows() == 4
    cell = table.cellAt(notes.editor.textCursor())
    assert cell.row() == 3 and cell.column() == 0


def test_add_row_column_borders_and_page_setup(notes, monkeypatch):
    table = insert_default(notes, monkeypatch)
    notes.tables.add_row_below()
    assert table.rows() == 4
    notes.tables.add_column_right()
    assert table.columns() == 3
    notes.tables.toggle_borders()
    assert table.format().border() > 0
    notes.tables.toggle_borders()
    assert table.format().border() == 0
    notes.set_page_setup(NotesPageSetup(), from_load=True)
    for row in range(table.rows()):
        for col in range(table.columns()):
            block = table.cellAt(row, col).firstCursorPosition().block()
            assert block.blockFormat().bottomMargin() == 0


def test_text_formatting_inside_cell(notes, monkeypatch):
    table = insert_default(notes, monkeypatch)
    notes.editor.insertPlainText('A short note')
    cursor = notes.editor.textCursor()
    cursor.setPosition(table.cellAt(0, 0).firstCursorPosition().position())
    cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock,
                        QTextCursor.MoveMode.KeepAnchor)
    notes.editor.setTextCursor(cursor)
    notes.bold_action.trigger()
    char = table.cellAt(0, 0).firstCursorPosition().block().begin().fragment()
    assert char.isValid() and char.charFormat().fontWeight() >= 700
