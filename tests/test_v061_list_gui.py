"""Native QTextList behaviour; run on Windows/macOS with PySide6 installed."""
import pytest
pytest.importorskip('PySide6.QtWidgets')
from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor, QPalette
from PySide6.QtWidgets import QApplication, QPlainTextEdit
from PySide6.QtTest import QTest
from yomunote.editor import NotesEditor
from yomunote.window import stylesheet, THEMES


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def notes(app):
    widget = NotesEditor()
    widget.resize(720, 640)
    widget.show()
    app.processEvents()
    yield widget
    widget.close()


def block(notes, number):
    return notes.editor.document().findBlockByNumber(number)


def caret(notes, number, offset=1):
    here = QTextCursor(notes.editor.document())
    target = block(notes, number)
    here.setPosition(target.position() + min(offset, max(0, target.length()-1)))
    notes.editor.setTextCursor(here)


def select_blocks(notes, first, last):
    cursor = QTextCursor(notes.editor.document())
    cursor.setPosition(block(notes, first).position())
    last_block = block(notes, last)
    cursor.setPosition(last_block.position() + last_block.length()-1, QTextCursor.MoveMode.KeepAnchor)
    notes.editor.setTextCursor(cursor)


def test_list_item_sink_does_not_move_other_markers_and_undoes(notes):
    notes.editor.setPlainText('First\nSecond\nThird')
    select_blocks(notes, 0, 2)
    notes.make_list(True)
    first, second, third = [block(notes, i) for i in range(3)]
    original_list = first.textList()
    assert original_list is not None and original_list.objectIndex() == second.textList().objectIndex() == third.textList().objectIndex()
    assert original_list.format().indent() == 1
    assert original_list.itemNumber(second) == 1
    assert original_list.itemText(second).strip().startswith('2')
    caret(notes, 1)
    notes.indent(+1)
    assert second.textList() is not None and second.textList().objectIndex() != first.textList().objectIndex()
    assert second.textList().format().indent() == 2
    assert first.textList().objectIndex() == third.textList().objectIndex()
    assert first.textList().format().indent() == 1
    assert first.textList().itemNumber(third) == 1
    notes.indent(-1)
    assert (second.textList().objectIndex() == first.textList().objectIndex()
            == third.textList().objectIndex())
    assert first.textList().itemNumber(second) == 1
    assert notes.editor.toPlainText() == 'First\nSecond\nThird'


def test_earliest_list_item_has_no_parent_to_sink_under(notes):
    notes.editor.setPlainText('A\nB')
    select_blocks(notes, 0, 1)
    notes.make_list(False)
    caret(notes, 0)
    notes.indent(+1)
    assert block(notes, 0).textList().format().indent() == 1
    assert block(notes, 1).textList().format().indent() == 1


def test_ordered_blank_between_items_stays_ordinary_and_numbering_continues(notes):
    notes.editor.setPlainText('One\n\nTwo')
    select_blocks(notes, 0, 2)
    notes.make_list(True)
    a, empty, b = [block(notes, i) for i in range(3)]
    assert empty.textList() is None
    assert a.textList().objectIndex() == b.textList().objectIndex()
    assert a.textList().itemNumber(b) == 1
    caret(notes, 2)
    notes.indent(+1)
    assert empty.textList() is None
    assert a.textList().format().indent() == 1
    assert b.textList().format().indent() == 2
    assert notes.editor.toPlainText() == 'One\n\nTwo'


def test_blank_splits_bullet_lists_and_cannot_sink_last_or_first(notes):
    notes.editor.setPlainText('One\n\nTwo')
    select_blocks(notes, 0, 2)
    notes.make_list(False)
    a, empty, b = [block(notes, i) for i in range(3)]
    assert empty.textList() is None
    assert a.textList() is not None and b.textList() is not None
    assert a.textList().objectIndex() != b.textList().objectIndex()
    caret(notes, 2)
    notes.indent(+1)
    assert b.textList().format().indent() == 1


def test_plain_paragraph_bracket_shortcut_changes_only_caret_block(notes, app):
    notes.editor.setPlainText('Before\nMiddle\nAfter')
    caret(notes, 1)
    notes.editor.setFocus()
    app.processEvents()
    QTest.keyClick(notes.editor, Qt.Key.Key_BracketRight, Qt.KeyboardModifier.ControlModifier)
    app.processEvents()
    assert [block(notes, i).blockFormat().indent() for i in range(3)] == [0, 1, 0]
    QTest.keyClick(notes.editor, Qt.Key.Key_BracketLeft, Qt.KeyboardModifier.ControlModifier)
    app.processEvents()
    assert [block(notes, i).blockFormat().indent() for i in range(3)] == [0, 0, 0]


def test_selection_excludes_next_block_at_start_and_ignores_blank(notes):
    notes.editor.setPlainText('First\nSecond\n\nLast')
    cursor = QTextCursor(notes.editor.document())
    cursor.setPosition(block(notes, 0).position())
    cursor.setPosition(block(notes, 2).position(), QTextCursor.MoveMode.KeepAnchor)
    notes.editor.setTextCursor(cursor)
    notes.indent(+1)
    assert [block(notes, i).blockFormat().indent() for i in range(4)] == [1, 1, 0, 0]


@pytest.mark.parametrize('theme', ['washi', 'lilac', 'modern-light', 'indigo', 'modern-dark'])
def test_ocr_review_surface_and_text_follow_theme(app, theme):
    palette = THEMES[theme]
    sample = QPlainTextEdit()
    sample.setObjectName('ocrReviewText')
    old_style = app.styleSheet()
    app.setStyleSheet(stylesheet(palette))
    sample.setPlainText('OCR: readable quotation')
    sample.show()
    app.processEvents()
    assert sample.palette().color(QPalette.ColorRole.Base).name().lower() == palette['paper'].lower()
    assert sample.palette().color(QPalette.ColorRole.Text).name().lower() == palette['ink'].lower()
    sample.close()
    app.setStyleSheet(old_style)
