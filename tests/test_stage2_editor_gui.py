"""GUI regression checks; run on Windows/macOS with PySide6 present."""
import sys
import pytest
pytest.importorskip('PySide6')
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QTextCursor
from PySide6.QtWidgets import QApplication
import yomunote.editor as editor_module
from yomunote.editor import NotesEditor


@pytest.fixture(scope='module')
def app():
    existing = QApplication.instance()
    return existing or QApplication([])


def test_windows_ctrl_delete_is_one_word_not_paragraph(app, monkeypatch):
    monkeypatch.setattr(editor_module, 'IS_MAC', False)
    notes = NotesEditor()
    try:
        notes.set_html('<p>alpha beta gamma</p><p>second paragraph</p>')
        cursor = notes.editor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        notes.editor.setTextCursor(cursor)
        event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Delete,
                          Qt.KeyboardModifier.ControlModifier)
        notes.editor.keyPressEvent(event)
        assert 'beta gamma' in notes.editor.toPlainText()
        assert 'second paragraph' in notes.editor.toPlainText()
        assert 'alpha beta gamma' not in notes.editor.toPlainText()
    finally:
        notes.close()


def test_empty_line_font_size_updates_line_geometry(app):
    notes = NotesEditor()
    try:
        notes.set_html('<p></p>')
        notes.font_size.setValue(48)
        block = notes.editor.textCursor().block()
        assert block.charFormat().fontPointSize() == 48
        assert block.blockFormat().lineHeightType() != 2  # Never force FixedHeight.
        assert notes.editor.document().isUndoAvailable()
        # A font size selection must not break subsequent text edits.
        notes.editor.insertPlainText('hello')
        assert 'hello' in notes.editor.toPlainText()
        notes.editor.undo()
        assert notes.editor.toPlainText() == '' 
    finally:
        notes.close()


def test_windows_ctrl_backspace_deletes_previous_word_only(app, monkeypatch):
    monkeypatch.setattr(editor_module, 'IS_MAC', False)
    notes = NotesEditor()
    try:
        notes.set_html('<p>alpha beta gamma</p><p>second paragraph</p>')
        cursor = notes.editor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        cursor.movePosition(QTextCursor.MoveOperation.NextWord)
        cursor.movePosition(QTextCursor.MoveOperation.NextWord)
        notes.editor.setTextCursor(cursor)  # at the beginning of 'gamma'
        before = notes.editor.toPlainText()
        notes.editor.keyPressEvent(QKeyEvent(QKeyEvent.Type.KeyPress,
                                   Qt.Key.Key_Backspace,
                                   Qt.KeyboardModifier.ControlModifier))
        after = notes.editor.toPlainText()
        assert after != before
        assert 'alpha' in after and 'gamma' in after
        assert 'second paragraph' in after
        assert 'beta' not in after
        assert notes.editor.document().isUndoAvailable()
        notes.editor.undo()
        assert notes.editor.toPlainText() == before
    finally:
        notes.close()


def test_notes_zoom_preserves_active_line_position(app):
    from PySide6.QtCore import QPoint
    from PySide6.QtTest import QTest
    notes = NotesEditor()
    try:
        notes.resize(650, 440)
        notes.show()
        notes.editor.setPlainText(''.join(f'Paragraph {i:03d}: words for a long note.\n'
                                          for i in range(250)))
        # In an offscreen Qt window, text layout and scrollbar ranges may not
        # be ready as soon as setPlainText() returns. Moving a cursor 85 lines
        # from the document start and immediately calling ensureCursorVisible()
        # can leave it thousands of pixels outside the viewport on Windows.
        # That tests an unfinished *initial scroll*, not the zoom anchoring.
        app.processEvents()
        QTest.qWait(50)
        bar = notes.editor.verticalScrollBar()
        assert bar.maximum() > bar.minimum()  # long notes must scroll
        bar.setValue(bar.maximum() // 3)
        app.processEvents()

        # Set the caret on text that is ALREADY visible, as when a person
        # clicks a paragraph they are reading. This tests the actual promise:
        # zoom in/out must keep that same editing line at its screen position.
        viewport = notes.editor.viewport()
        caret = notes.editor.cursorForPosition(QPoint(12, viewport.height() // 2))
        assert caret.blockNumber() > 10  # ensure we did not choose the first page
        notes.editor.setTextCursor(caret)
        app.processEvents()
        before = notes.editor.cursorRect().top()
        assert 0 <= before < viewport.height()
        original_line = notes.editor.textCursor().block().text()

        notes.zoom_notes(+1)
        QTest.qWait(50)  # allow queued text layout / anchor alignment
        after = notes.editor.cursorRect().top()
        assert 0 <= after < viewport.height()
        assert abs(after - before) <= 18, (before, after)
        assert notes.editor.textCursor().block().text() == original_line
        notes.zoom_notes(-1)
        QTest.qWait(50)
        assert abs(notes.editor.cursorRect().top() - before) <= 18
        assert notes.editor.textCursor().block().text() == original_line
    finally:
        notes.close()


def test_notes_zoom_keeps_visible_passage_if_caret_elsewhere(app):
    from PySide6.QtCore import QPoint
    from PySide6.QtTest import QTest
    notes = NotesEditor()
    try:
        notes.resize(650, 440)
        notes.show()
        notes.editor.setPlainText(''.join(f'Paragraph {i:03d}: line of reading.\n'
                                          for i in range(250)))
        app.processEvents()
        # Caret at start while reader has scrolled well past it.
        notes.editor.verticalScrollBar().setValue(900)
        app.processEvents()
        point = QPoint(12, 18)
        original = notes.editor.cursorForPosition(point).block().text()
        notes.zoom_notes(+1)
        QTest.qWait(50)
        current = notes.editor.cursorForPosition(point).block().text()
        assert original == current, (original, current)
    finally:
        notes.close()
