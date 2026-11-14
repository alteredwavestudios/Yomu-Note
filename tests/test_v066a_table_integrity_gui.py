"""Real Qt tests for deleting rows/columns without losing other data.

Run on Windows/macOS with PySide6, or in CI with the
QT_QPA_PLATFORM=offscreen environment setting.
"""
import sqlite3
from pathlib import Path

import pytest
pytest.importorskip('PySide6.QtWidgets')

from PySide6.QtGui import QTextCursor, QTextLength
from PySide6.QtWidgets import QApplication

from yomunote.editor import NotesEditor
from yomunote.notebook import Notebook


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def notes(app):
    result = NotesEditor()
    result.resize(640, 500)
    result.show()
    app.processEvents()
    yield result
    result.close()


def make_table(notes):
    cursor = notes.editor.textCursor()
    table = cursor.insertTable(3, 2, notes.tables.new_format(2))
    for row in range(3):
        for col in range(2):
            cell = table.cellAt(row, col)
            pointer = QTextCursor(cell.firstCursorPosition())
            pointer.insertText(f'CELL_{row}_{col}_VALUE')
    return table


def current_cell(notes, table, row, col):
    notes.editor.setTextCursor(table.cellAt(row, col).firstCursorPosition())


def test_row_delete_one_undo_and_saved_html(notes):
    table = make_table(notes)
    current_cell(notes, table, 1, 0)
    notes.tables.remove_row()
    assert table.rows() == 2
    assert 'CELL_1_0_VALUE' not in notes.html()
    assert 'CELL_1_1_VALUE' not in notes.html()
    assert 'CELL_0_0_VALUE' in notes.html()
    assert 'CELL_2_1_VALUE' in notes.html()
    assert notes.editor.textCursor().currentTable() is not None
    notes.editor.undo()
    assert table.rows() == 3
    assert 'CELL_1_0_VALUE' in notes.html()
    assert 'CELL_1_1_VALUE' in notes.html()
    notes.editor.redo()
    assert table.rows() == 2
    assert 'CELL_1_0_VALUE' not in notes.html()


def test_column_delete_preserves_surviving_values_and_widths(notes):
    table = make_table(notes)
    current_cell(notes, table, 0, 0)
    notes.tables.add_column_right()
    assert table.columns() == 3
    # First column gets split rather than reset to equal widths.
    widths = table.format().columnWidthConstraints()
    assert [round(v.rawValue()) for v in widths] == [25, 25, 50]
    # Delete the original second data column (now in column 2).
    current_cell(notes, table, 1, 2)
    notes.tables.remove_column()
    assert table.columns() == 2
    assert 'CELL_2_1_VALUE' not in notes.html()
    assert 'CELL_2_0_VALUE' in notes.html()
    widths = table.format().columnWidthConstraints()
    assert [round(v.rawValue()) for v in widths] == [50, 50]
    notes.editor.undo()
    assert table.columns() == 3
    assert 'CELL_2_1_VALUE' in notes.html()


def test_delete_merged_cell_requires_split(notes, monkeypatch):
    table = make_table(notes)
    table.mergeCells(0, 0, 2, 1)
    messages = []
    monkeypatch.setattr(
        'yomunote.notes_tables.QMessageBox.information',
        lambda *args: messages.append(args))
    current_cell(notes, table, 0, 0)
    html = notes.html()
    notes.tables.remove_row()
    assert table.rows() == 3
    assert notes.html() == html
    assert messages


def test_deleted_secret_not_present_in_clean_notebook(notes, tmp_path):
    table = make_table(notes)
    current_cell(notes, table, 1, 0)
    notes.tables.remove_row()
    assert 'CELL_1_0_VALUE' not in notes.html()
    nb = Notebook.create(tmp_path, 'Private Tables')
    try:
        project = nb.project(nb.active_id)
        project.notes_html = notes.html()
        project.save()
        nb.save()
        target = tmp_path / 'Clean Table Export.yomunote'
        Notebook.create_clean_share_copy(nb.path, target)
        with sqlite3.connect(nb.path) as conn:
            original_current = conn.execute(
                'SELECT data FROM files WHERE path LIKE ?',
                ('%/project.json',)).fetchone()[0]
        # The CURRENT saved record does not include deleted cells.
        assert b'CELL_1_0_VALUE' not in original_current
        with sqlite3.connect(target) as conn:
            data = conn.execute('SELECT data FROM files WHERE path LIKE ?',
                                ('%/project.json',)).fetchone()[0]
        assert b'CELL_1_0_VALUE' not in data
        assert b'CELL_1_1_VALUE' not in data
        assert b'CELL_2_0_VALUE' in data
        # This test sentinel is ASCII; inspect full database bytes too.
        assert b'CELL_1_0_VALUE' not in target.read_bytes()
        # Undo in the live tab must STILL restore the deleted row,
        # without modifying the already exported clean copy.
        notes.editor.undo()
        assert 'CELL_1_0_VALUE' in notes.html()
        assert b'CELL_1_0_VALUE' not in target.read_bytes()
    finally:
        nb.close()


def test_table_alignment_reflow_does_not_change_saved_border(notes, app):
    """Centred and right-aligned cell text must not move borders."""
    from PySide6.QtCore import Qt

    table = make_table(notes)
    current_cell(notes, table, 0, 1)
    for alignment in (Qt.AlignmentFlag.AlignHCenter,
                      Qt.AlignmentFlag.AlignRight,
                      Qt.AlignmentFlag.AlignLeft):
        notes.editor.setAlignment(alignment)
        app.processEvents()
        # Force Qt to repaint the temporary, unsaved guide overlay.
        image = notes.editor.viewport().grab().toImage()
        assert not image.isNull()
        assert table.format().border() == 0.0
    assert notes.html().lower().count('<table') >= 1


def test_two_independent_editors_never_share_table_undo(notes, app):
    """The active editor owns its table and its native Undo stack."""
    other = NotesEditor()
    try:
        other.show()
        table_a = make_table(notes)
        table_b = make_table(other)
        current_cell(notes, table_a, 1, 0)
        notes.tables.remove_row()
        assert table_a.rows() == 2
        assert table_b.rows() == 3
        assert 'CELL_1_0_VALUE' in other.html()
        notes.editor.undo()
        assert table_a.rows() == 3
        assert table_b.rows() == 3
    finally:
        other.close()
