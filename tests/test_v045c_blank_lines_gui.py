"""Offscreen Qt coverage for blank paragraphs with invisible formatting runs.

Run on a Windows or Mac installation with PySide6 (or QT_QPA_PLATFORM=offscreen).
"""
import pytest
pytest.importorskip('PySide6.QtWidgets')
from PySide6.QtGui import QTextCursor, QTextBlockFormat
from PySide6.QtWidgets import QApplication
from yomunote.editor import NotesEditor


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize('blank', ['', '   ', '\t', '\u00a0', '\u200b', '\u200e', ' \u200b\u00a0 '])
def test_blank_line_font_height_grows_and_shrinks(app, blank):
    notes = NotesEditor()
    try:
        content = f'Before\n{blank}\nAfter'
        notes.editor.setPlainText(content)
        notes.resize(620, 540)
        notes.show()
        app.processEvents()
        line = notes.editor.document().findBlockByNumber(1)
        cursor = notes.editor.textCursor()
        cursor.setPosition(line.position() + (1 if blank else 0))
        notes.editor.setTextCursor(cursor)
        notes.set_font_size_immediately(12)
        app.processEvents()
        small = line.layout().boundingRect().height()
        notes.set_font_size_immediately(42)
        app.processEvents()
        large = line.layout().boundingRect().height()
        assert large > small + 8, (repr(blank), small, large)
        assert round(notes._selected_first_size()) == 42
        assert line.blockFormat().lineHeightType() == int(QTextBlockFormat.LineHeightTypes.MinimumHeight.value)
        notes.set_font_size_immediately(16)
        app.processEvents()
        smaller = line.layout().boundingRect().height()
        assert smaller < large, (repr(blank), smaller, large)
        # Qt deliberately maps U+00A0 to an ordinary space in toPlainText().
        # toRawText preserves the actual Unicode, so this also detects any
        # accidental filler characters inserted while changing font sizes.
        raw = notes.editor.document().toRawText().replace('\u2029', '\n').replace('\u2028', '\n')
        assert raw == content
        assert notes.editor.document().isUndoAvailable()
    finally:
        notes.close()


def test_consecutive_blank_paragraphs_change_independently(app):
    notes = NotesEditor()
    try:
        notes.editor.setPlainText('First\n \n\u200b\n\nLast')
        notes.resize(640, 560)
        notes.show()
        app.processEvents()
        doc = notes.editor.document()
        blocks = [doc.findBlockByNumber(i) for i in (1, 2, 3)]
        old_format = [block.blockFormat().lineHeightType() for block in blocks]
        caret = notes.editor.textCursor()
        caret.setPosition(blocks[1].position() + 1)
        notes.editor.setTextCursor(caret)
        notes.set_font_size_immediately(45)
        app.processEvents()
        assert blocks[1].blockFormat().lineHeightType() == int(QTextBlockFormat.LineHeightTypes.MinimumHeight.value)
        assert blocks[0].blockFormat().lineHeightType() == old_format[0]
        assert blocks[2].blockFormat().lineHeightType() == old_format[2]
        assert notes.editor.toPlainText() == 'First\n \n\u200b\n\nLast'
    finally:
        notes.close()
