"""Actual canvas and tab integration checks, run on Windows with PySide6."""
import pytest
pytest.importorskip('PySide6.QtWidgets')
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QListWidgetItem
from yomunote.notebook import Notebook
from yomunote.window import DropPageList, MainWindow, DeleteNotebookTabCommand
from yomunote.history import CallbackAction
from yomunote.vector_marks import make_stroke

@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


def test_gap_insertion_menu_freezes_page_index(app):
    pages = DropPageList()
    try:
        for i in range(4):
            pages.addItem(QListWidgetItem(f'Page {i + 1}'))
        emitted=[]
        pages.blankAt.connect(emitted.append)
        pages._insert_index=2
        pages._freeze_insert_gap()
        pages._insert_index=4  # mouse moves while popup is open
        pages.plus_menu.actions()[1].trigger()
        assert emitted == [2]
    finally:
        pages.close()


def test_stage3_vector_strokes_are_undoable_without_affecting_text(app, tmp_path):
    notebook=Notebook.create(tmp_path, 'Stage 3')
    window=MainWindow()
    try:
        window.show_notebook(notebook)
        pane=window.active()
        pane.add_blank(0)
        pane.add_blank(1)
        pane.add_blank(1)
        assert [p['kind'] for p in pane.project.pages] == ['blank']*3
        middle=pane.project.pages[1]['id']
        assert pane.project.selected_page == middle
        mark=make_stroke([(.1,.1),(.2,.2)], '#c74879', .003)
        pane.add_stroke(mark)
        assert pane.project.annotations[middle][0]['kind']=='stroke'
        pane.move_stroke(0, {'dx':.1,'dy':.1})
        assert pane.project.annotations[middle][0]['points'][0] == pytest.approx([.2,.2])
        window.undo_shared()
        assert pane.project.annotations[middle][0]['points'][0] == [.1,.1]
        window.redo_shared()
        pane.erase_stroke(0)
        assert pane.project.annotations.get(middle) is None
        window.undo_shared()
        assert pane.project.annotations[middle][0]['id']==mark['id']
    finally:
        window.close()


def test_deleted_tab_restores_from_any_remaining_tab(app, tmp_path):
    notebook=Notebook.create(tmp_path,'Tab restoration')
    window=MainWindow()
    try:
        window.show_notebook(notebook)
        first=window.active()._tab_id
        second=window.notebook.add_tab('Other')
        window._resync_notebook_tabs()
        # The active and remaining tab is different from the deleted one.
        window.tabs.setCurrentIndex(next(i for i in range(window.tabs.count())
                                        if window.tabs.widget(i)._tab_id==second))
        cmd=DeleteNotebookTabCommand(window,first)
        window._notebook_history.perform(CallbackAction('Delete Tab',cmd.undo,cmd.redo))
        assert first not in [t['id'] for t in notebook.tabs]
        window.undo_shared()
        assert first in [t['id'] for t in notebook.tabs]
        window.redo_shared()
        assert first not in [t['id'] for t in notebook.tabs]
    finally:
        window.close()
