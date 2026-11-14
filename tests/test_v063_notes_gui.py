"""Desktop checks: run with PySide6 (QT_QPA_PLATFORM=offscreen works in CI)."""
import pytest
pytest.importorskip('PySide6.QtWidgets')
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QTextCursor
from yomunote.editor import NotesEditor
from yomunote.notes_layout import NotesPageSetup

@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])

@pytest.fixture
def notes(app):
    widget = NotesEditor(defaults={'font':'Arial','font_size':13})
    widget.resize(700,500)
    widget.show()
    app.processEvents()
    yield widget
    widget.close()


def test_page_setup_and_selected_paragraph_spacing(notes):
    notes.editor.setPlainText('One\nTwo\nThree')
    notes.set_page_setup(NotesPageSetup(), from_load=True)
    assert notes.editor.document().rootFrame().frameFormat().topMargin() > 0
    cursor = notes.editor.textCursor()
    cursor.setPosition(notes.editor.document().findBlockByNumber(1).position()+1)
    notes.editor.setTextCursor(cursor)
    notes.set_selected_paragraph_spacing(before_pt=5, after_pt=12, line_multiplier=1.5)
    fmt = notes.editor.document().findBlockByNumber(1).blockFormat()
    assert fmt.topMargin()>0 and fmt.bottomMargin()>0
    assert fmt.lineHeightType()==1
    assert abs(fmt.lineHeight()-150)<0.1
    assert notes.editor.document().findBlockByNumber(0).blockFormat().topMargin()==0


def test_list_spacing_and_jump_button(notes, app):
    notes.editor.setPlainText('One\nTwo\nThree')
    notes.set_page_setup(NotesPageSetup(), from_load=True)
    cursor = notes.editor.textCursor()
    cursor.setPosition(0)
    cursor.setPosition(len('One\nTwo'), QTextCursor.MoveMode.KeepAnchor)
    notes.editor.setTextCursor(cursor)
    notes.make_list(False)
    app.processEvents()
    blocks = [notes.editor.document().findBlockByNumber(i) for i in range(3)]
    assert blocks[0].textList() is not None
    assert blocks[1].textList() is not None
    assert blocks[0].blockFormat().bottomMargin() == 0
    assert blocks[1].blockFormat().bottomMargin() > 0
    notes.set_jump_edit_visible(True)
    assert notes.jump_edit_button.isVisible()
