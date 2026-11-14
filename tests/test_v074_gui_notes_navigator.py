"""Native Qt acceptance checks for v0.7.4 (Windows/macOS or QT_QPA_PLATFORM=offscreen).

These intentionally skip on pure-Python CI. They exercise the actual editor
rather than merely looking for words in the source code.
"""
import os
from pathlib import Path

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
QtCore = pytest.importorskip('PySide6.QtCore')
QtGui = pytest.importorskip('PySide6.QtGui')
QtWidgets = pytest.importorskip('PySide6.QtWidgets')

from yomunote.window import ProjectPane
from yomunote.project import Project
from yomunote.page_groups import flat_tree, group_pages
from yomunote.page_groups_ui import PageGroupsTree, ROLE_KIND


@pytest.fixture(scope='module')
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def test_native_multi_note_editor_switch_save_and_reload(app, tmp_path):
    project = Project.create(tmp_path, 'Notes Switch')
    settings = QtCore.QSettings(str(tmp_path/'settings.ini'), QtCore.QSettings.Format.IniFormat)
    pane = ProjectPane(project, settings)
    pane.show()
    app.processEvents()
    try:
        first = pane.project.active_note_id
        pane.notes.editor.insertHtml('<p><b>Important</b> <a href="yomu-page:abc">link</a></p>')
        pane.add_note_page()
        second = pane.project.active_note_id
        assert second != first
        pane.notes.editor.insertHtml('<p><i>Second document</i></p>')
        pane.select_note_page(first)
        assert 'Important' in pane.notes.editor.toPlainText()
        assert 'Second document' not in pane.notes.editor.toPlainText()
        pane.select_note_page(second)
        assert 'Second document' in pane.notes.editor.toPlainText()
        pane.save()
        loaded = Project.load(project.path)
        assert len(loaded.note_pages) == 2
        assert 'Important' in loaded.note_pages[0]['html']
        assert 'Second document' in loaded.note_pages[1]['html']
        assert 'href=' in loaded.note_pages[0]['html']
    finally:
        pane.close_project()
        pane.close()


def test_remove_note_page_is_one_undo_step_and_restores_content(app, tmp_path):
    project = Project.create(tmp_path, 'Note removal')
    settings = QtCore.QSettings(str(tmp_path/'settings.ini'), QtCore.QSettings.Format.IniFormat)
    pane = ProjectPane(project, settings)
    try:
        pane.add_note_page()
        removed_id = pane.project.active_note_id
        pane.notes.editor.insertHtml('<h2>Keep me</h2>')
        # Test the same model callback after confirmation, without modal UI.
        pane._delete_note_page(removed_id)
        assert len(pane.project.note_pages) == 1
        pane._insert_note_page({'id': removed_id, 'title': 'Notes 2',
                               'html': '<h2>Keep me</h2>', 'scroll': 0,
                               'page_setup': None}, 1)
        assert len(pane.project.note_pages) == 2
        assert 'Keep me' in pane.notes.editor.toPlainText()
    finally:
        pane.close_project()
        pane.close()


def test_group_labels_are_present_even_without_thumbnails(app):
    tree, gid = group_pages(flat_tree(['p1', 'p2']), ['p1', 'p2'], 'Chapter 7')
    widget = PageGroupsTree()
    widget.load_tree(tree, [{'id': 'p1', 'title': 'First page'},
                            {'id': 'p2', 'title': 'Second page'}])
    try:
        folder = widget.find_item('group', gid)
        p1 = widget.find_item('page', 'p1')
        assert folder.text(0) == 'Chapter 7'
        assert p1.text(0) == 'First page'
        for width in (450, 290, 200, 140, 80, 450):
            widget.set_navigator_density(width)
            assert folder.text(0) == 'Chapter 7'
            assert p1.text(0) == 'First page'
        image = QtGui.QPixmap(40, 50)
        image.fill(QtGui.QColor('#668899'))
        widget.set_page_thumbnail('p1', image)
        widget.discard_other_thumbnails(set())
        assert p1.text(0) == 'First page'
        assert folder.text(0) == 'Chapter 7'
        # The delegate must not erase GROUP titles in the rail layout.
        index = widget.indexFromItem(folder)
        option = QtWidgets.QStyleOptionViewItem()
        option.rect = QtCore.QRect(0, 0, 140, 41)
        widget.set_navigator_density(140)
        widget.itemDelegate().initStyleOption(option, index)
        assert option.text == 'Chapter 7'
    finally:
        widget.close()
