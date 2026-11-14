"""Offscreen Qt smoke tests (run with QT_QPA_PLATFORM=offscreen)."""
import pytest
pytest.importorskip('PySide6.QtWidgets')
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QApplication
from yomunote.editor import NotesEditor
from yomunote.notebook import Notebook
from yomunote.window import ProjectPane, MainWindow

@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


def _selected_size(editor, position=None):
    # QTextEdit.undo() is allowed to move/collapse the current selection.
    # Always inspect the SAME document character before and after Undo.
    c = editor.textCursor()
    probe = QTextCursor(editor.document())
    probe.setPosition(c.selectionStart() + 1 if position is None else position)
    return probe.charFormat().fontPointSize()


def test_repeated_font_shrink_in_middle_of_paragraph(app):
    editor=NotesEditor(defaults={'font':'Arial','font_size':13})
    try:
        editor.editor.setPlainText('Some normal text in a single paragraph')
        c=editor.editor.textCursor()
        c.setPosition(12)
        c.setPosition(16,QTextCursor.MoveMode.KeepAnchor)
        editor.editor.setTextCursor(c)
        sampled_character = c.selectionStart() + 1
        editor.change_font_size(-1)
        first=_selected_size(editor.editor)
        editor.change_font_size(-1)
        second=_selected_size(editor.editor)
        assert (first, second)==(12, 11)
        assert editor.editor.textCursor().selectedText()=='text'
        editor.editor.undo()
        assert _selected_size(editor.editor, sampled_character) == 12
        editor.editor.undo()
        assert _selected_size(editor.editor, sampled_character) == 13
    finally:
        editor.close()


def test_unified_history_notes_and_pages(app,tmp_path):
    nb=Notebook.create(tmp_path,'History Test')
    window=MainWindow()
    try:
        window.show_notebook(nb)
        pane=window.active()
        assert pane is not None
        pane.notes.editor.insertPlainText('Hello')
        assert window.history.can_undo
        pane.add_blank(0)
        page_id=pane.project.pages[0]['id']
        assert window.history.next_undo_label=='Add Blank Page'
        pane.rename_page_to('My New Page')
        assert pane.project.pages[0]['title']=='My New Page'
        window.undo_shared()
        assert pane.project.pages[0]['title']=='Blank page'
        window.undo_shared()
        assert not pane.project.pages
        window.undo_shared()
        assert pane.notes.editor.toPlainText()==''
        window.redo_shared(); window.redo_shared(); window.redo_shared()
        assert pane.notes.editor.toPlainText()=='Hello'
        assert pane.project.pages[0]['id']==page_id
        assert pane.project.pages[0]['title']=='My New Page'
    finally:
        window.close()
