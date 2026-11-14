"""Real Qt tests for the v0.6.5a list, heading and dialog fixes.

Run on Windows/macOS with PySide6 installed. These are not source greps:
they open actual editor widgets and send keyboard input to Qt.
"""
import pytest
pytest.importorskip('PySide6.QtWidgets')

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor, QTextListFormat, QPalette
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest

from yomunote.editor import NotesEditor
from yomunote.notes_layout import NotesPageSetup
from yomunote.notes_layout_dialog import NotesPageSetupDialog
from yomunote.window import application_palette, stylesheet, THEMES


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def notes(app):
    widget = NotesEditor()
    widget.resize(650, 510)
    widget.show()
    app.processEvents()
    yield widget
    widget.close()


def block(notes, index):
    return notes.editor.document().findBlockByNumber(index)


def caret(notes, index):
    cursor = QTextCursor(notes.editor.document())
    cursor.setPosition(block(notes, index).position())
    notes.editor.setTextCursor(cursor)


def select_blocks(notes, first, last):
    cursor = QTextCursor(notes.editor.document())
    cursor.setPosition(block(notes, first).position())
    last_block = block(notes, last)
    cursor.setPosition(last_block.position() + last_block.length()-1,
                       QTextCursor.MoveMode.KeepAnchor)
    notes.editor.setTextCursor(cursor)


def test_list_level_marker_progression_and_repeat_indent(notes):
    notes.editor.setPlainText('One\nTwo\nThree\nFour')
    select_blocks(notes, 0, 3)
    notes.make_list(False)
    caret(notes, 2)
    notes.indent(+1)
    assert block(notes, 2).textList().format().indent() == 2
    assert block(notes, 2).textList().format().style() == QTextListFormat.Style.ListCircle
    notes.indent(+1)
    assert block(notes, 2).textList().format().indent() == 3
    assert block(notes, 2).textList().format().style() == QTextListFormat.Style.ListSquare
    notes.indent(-1)
    assert block(notes, 2).textList().format().indent() == 2
    assert block(notes, 2).textList().format().style() == QTextListFormat.Style.ListCircle
    notes.indent(-1)
    assert block(notes, 2).textList().format().indent() == 1
    assert block(notes, 2).textList().format().style() == QTextListFormat.Style.ListDisc
    assert block(notes, 0).textList().format().indent() == 1
    assert block(notes, 3).textList().format().indent() == 1


def test_existing_text_applied_as_list_uses_inline_native_markers(notes):
    notes.editor.setPlainText('Before\nThis is already written\nThen this line')
    select_blocks(notes, 1, 2)
    notes.make_list(True)
    assert block(notes, 0).textList() is None
    assert block(notes, 1).textList() is not None
    assert block(notes, 2).textList() is not None
    assert notes.editor.toPlainText() == 'Before\nThis is already written\nThen this line'
    assert block(notes, 1).blockFormat().textIndent() == 0


def test_return_creates_new_item_without_scrolling_to_top(notes, app):
    notes.editor.setPlainText('\n'.join('Paragraph '+str(i) for i in range(75)))
    caret(notes, 64)
    notes.make_list(False)
    notes.editor.setFocus()
    notes.editor.ensureCursorVisible()
    app.processEvents()
    original_block = notes.editor.textCursor().blockNumber()
    QTest.keyClick(notes.editor, Qt.Key.Key_Return)
    app.processEvents()
    assert notes.editor.textCursor().blockNumber() == original_block + 1
    assert notes.editor.textCursor().currentList() is not None
    assert notes.editor.verticalScrollBar().value() > 0
    assert notes.editor.document().findBlockByNumber(65).textList() is not None


def test_heading_dropdown_follows_caret_and_mixed_selection(notes, app):
    notes.editor.setPlainText('One\nTwo\nThree')
    caret(notes, 0)
    notes.change_heading(1)
    caret(notes, 1)
    notes.change_heading(2)
    app.processEvents()
    assert block(notes, 0).blockFormat().headingLevel() == 1
    assert block(notes, 1).blockFormat().headingLevel() == 2
    caret(notes, 0)
    assert notes.heading_choice.currentIndex() == 1
    caret(notes, 1)
    assert notes.heading_choice.currentIndex() == 2
    select_blocks(notes, 0, 1)
    assert notes.heading_choice.currentIndex() == 7
    notes.change_heading(3)
    assert block(notes, 0).blockFormat().headingLevel() == 3
    assert block(notes, 1).blockFormat().headingLevel() == 3
    assert block(notes, 2).blockFormat().headingLevel() == 0
    assert notes.heading_choice.currentIndex() == 3


@pytest.mark.parametrize('theme', ['washi', 'modern-light', 'indigo', 'modern-dark'])
def test_page_setup_spinboxes_inherit_theme(app, theme):
    old_style, old_palette = app.styleSheet(), app.palette()
    colours = THEMES[theme]
    app.setPalette(application_palette(colours))
    app.setStyleSheet(stylesheet(colours))
    dialog = NotesPageSetupDialog(NotesPageSetup())
    dialog.show()
    app.processEvents()
    try:
        for control in (dialog.top, dialog.bottom, dialog.left, dialog.right,
                        dialog.after, dialog.line):
            assert control.palette().color(QPalette.ColorRole.Base).name().lower() == colours['paper'].lower()
            assert control.palette().color(QPalette.ColorRole.Text).name().lower() == colours['ink'].lower()
    finally:
        dialog.close()
        app.setStyleSheet(old_style)
        app.setPalette(old_palette)
