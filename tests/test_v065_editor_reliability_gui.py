"""Desktop integration tests for actual Qt document behaviour.

Run with PySide6 installed. Offscreen Qt may be used in CI via:
QT_QPA_PLATFORM=offscreen python -m pytest -q tests/test_v065_editor_reliability_gui.py
"""
import pytest
pytest.importorskip('PySide6.QtWidgets')
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QTextCursor, QTextFormat
from yomunote.editor import NotesEditor
from yomunote.notes_layout import NotesPageSetup


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def notes(app):
    widget = NotesEditor(defaults={'font': 'Arial', 'font_size': 13})
    widget.resize(700, 520)
    widget.show()
    app.processEvents()
    yield widget
    widget.close()


def test_three_selected_headings_apply_to_all_blocks(notes):
    notes.editor.setPlainText('First\nSecond\nThird\nFourth')
    c = notes.editor.textCursor()
    c.setPosition(0)
    end = notes.editor.document().findBlockByNumber(2)
    c.setPosition(end.position() + len(end.text()), QTextCursor.MoveMode.KeepAnchor)
    notes.editor.setTextCursor(c)
    notes.change_heading(2)
    document = notes.editor.document()
    assert [document.findBlockByNumber(i).blockFormat().headingLevel()
            for i in range(4)] == [2, 2, 2, 0]


def test_explicit_zero_gap_survives_defaults_change_and_html(notes):
    notes.editor.setPlainText('First\nSecond')
    notes.set_page_setup(NotesPageSetup(), from_load=True)
    notes.set_selected_paragraph_spacing(after_pt=0)
    assert notes.editor.textCursor().blockFormat().bottomMargin() == 0
    notes.set_page_setup(NotesPageSetup(paragraph_after_pt=20))
    assert notes.editor.textCursor().blockFormat().bottomMargin() == 0
    saved = notes.html()
    notes.set_html(saved)
    notes.set_page_setup(NotesPageSetup(paragraph_after_pt=24), from_load=True)
    assert notes.editor.document().firstBlock().blockFormat().bottomMargin() == 0


def test_clear_formatting_removes_explicit_ink(notes):
    notes.editor.setHtml('<p><span style="color:#26374b">Dark ink</span></p>')
    c = notes.editor.textCursor()
    c.select(QTextCursor.SelectionType.Document)
    notes.editor.setTextCursor(c)
    notes.clear_formatting()
    block = notes.editor.document().firstBlock()
    fragment = next(iter(block)).fragment()
    assert not fragment.charFormat().hasProperty(QTextFormat.Property.ForegroundBrush)


def test_native_undo_restores_page_setup_paragraph_format(notes):
    # Saved defaults are restored separately from Qt's native blocks.
    initial = NotesPageSetup(paragraph_after_pt=8)
    changed = NotesPageSetup(paragraph_after_pt=20)
    notes.editor.setPlainText('First\nSecond')
    notes.set_page_setup(initial, from_load=True)
    before = notes.editor.document().firstBlock().blockFormat().bottomMargin()
    notes.set_page_setup(changed)
    during = notes.editor.document().firstBlock().blockFormat().bottomMargin()
    assert during > before
    notes.editor.undo()
    notes.restore_page_setup_metadata(initial, update_frame=False)
    after = notes.editor.document().firstBlock().blockFormat().bottomMargin()
    assert abs(after - before) < 0.2
