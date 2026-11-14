"""Desktop checks for v0.7.1's Qt tree checkboxes and group display.

Run with PySide6 installed; the headless source environment skips this
file. These tests use actual QTreeWidget items rather than source text.
"""
from __future__ import annotations

import pytest

qt = pytest.importorskip('PySide6')
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from yomunote.page_groups import group_node, page_node
from yomunote.page_groups_ui import PageGroupsTree, ROLE_ACTIVE


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


def sample():
    folder = group_node('Lecture', [page_node('a'), page_node('b')])
    pages = [{'id': 'a', 'title': 'Slide one'},
             {'id': 'b', 'title': 'Slide two'}]
    return folder, pages


def test_active_marker_does_not_mark_pages_as_read(app):
    folder, pages = sample()
    tree = PageGroupsTree()
    observed = []
    tree.readToggled.connect(lambda kind, pid, read: observed.append((kind,pid,read)))
    tree.load_tree([folder], pages, 'a', ['b'])
    target = tree.find_item('page', 'a')
    assert target.checkState(0) == Qt.CheckState.Unchecked
    tree.mark_active('b')
    tree.mark_active('a')
    assert observed == []
    target.setData(0, ROLE_ACTIVE, True)
    assert observed == []
    tree.close()


def test_individual_checkbox_emits_one_read_event(app):
    folder, pages = sample()
    tree = PageGroupsTree()
    observed = []
    tree.readToggled.connect(lambda kind, pid, read: observed.append((kind,pid,read)))
    tree.load_tree([folder], pages, 'a', [])
    tree.find_item('page', 'a').setCheckState(0, Qt.CheckState.Checked)
    assert observed == [('page', 'a', True)]
    tree.close()


def test_nested_group_progress_uses_descendants(app):
    subgroup = group_node('Subgroup', [page_node('b')])
    folder = group_node('Main', [page_node('a'), subgroup])
    tree = PageGroupsTree()
    tree.load_tree([folder], [{'id':'a','title':'One'},{'id':'b','title':'Two'}],
                   'a', ['a'])
    item = tree.find_item('group', folder['id'])
    assert item.checkState(0) == Qt.CheckState.PartiallyChecked
    assert item.data(0, Qt.ItemDataRole.UserRole + 4) == (1, 2)
    assert tree.find_item('group', subgroup['id']).checkState(0) == Qt.CheckState.Unchecked
    tree.close()
