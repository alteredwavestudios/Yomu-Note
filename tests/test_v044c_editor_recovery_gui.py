"""Run with PySide6 on Windows/macOS or with QT_QPA_PLATFORM=offscreen."""
import pytest
pytest.importorskip('PySide6.QtWidgets')
from PySide6.QtGui import QTextCursor, QTextBlockFormat
from PySide6.QtWidgets import QApplication
from yomunote.editor import NotesEditor

@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])

def test_font_format_does_not_break_undo_stack(app):
    notes=NotesEditor()
    try:
        notes.editor.setPlainText('First line\n\nThird line')
        cursor=notes.editor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        cursor.movePosition(QTextCursor.MoveOperation.Down)
        notes.editor.setTextCursor(cursor)
        notes.set_font_size_immediately(46)
        assert cursor.block().blockFormat().lineHeightType() != QTextBlockFormat.LineHeightTypes.FixedHeight.value
        notes.editor.insertPlainText('New text')
        assert 'New text' in notes.editor.toPlainText()
        notes.editor.undo()
        assert 'New text' not in notes.editor.toPlainText()
        notes.editor.redo()
        assert 'New text' in notes.editor.toPlainText()
    finally:
        notes.close()

def test_repair_of_fixed_height_is_undoable(app):
    notes=NotesEditor()
    try:
        notes.editor.setPlainText('hello\nworld')
        c=notes.editor.textCursor()
        c.movePosition(QTextCursor.MoveOperation.Start)
        b=c.blockFormat()
        b.setLineHeight(12.0,int(QTextBlockFormat.LineHeightTypes.FixedHeight.value))
        c.setBlockFormat(b)
        assert notes.count_fixed_height_paragraphs()==1
        assert notes.repair_fixed_height_paragraphs()==1
        assert notes.count_fixed_height_paragraphs()==0
        notes.editor.undo()
        assert notes.count_fixed_height_paragraphs()==1
    finally:
        notes.close()
