"""v0.7 desktop checks; run on Windows/macOS with PySide6 installed.

The headless source package can skip these, but a desktop release
must test real Qt selection and tree interactions before being stable.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import pytest
pytest.importorskip('PySide6.QtWidgets')
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from yomunote.page_groups import flat_tree, group_pages, add_group, validate, flatten
from yomunote.page_groups_ui import PageGroupsTree


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def tree(app):
    widget = PageGroupsTree()
    nodes, folder = group_pages(flat_tree(['a', 'b', 'c']), ['a', 'b'], 'Week 1')
    nodes, sub = add_group(nodes, 'Chapter', parent_id=folder)
    pages = [{'id': i, 'title': label} for i, label in
             [('a', 'Introduction'), ('b', 'Conclusion'), ('c', 'Slide 1')]]
    widget.load_tree(nodes, pages, 'b')
    yield widget, nodes, folder, sub
    widget.close()


def test_grouped_view_has_same_flat_reading_order(tree):
    widget, nodes, folder, sub = tree
    assert widget.topLevelItemCount() == 2
    assert widget.flatten_items() == ['a', 'b', 'c']
    assert widget.extract_tree() == nodes
    validate(widget.extract_tree(), ['a', 'b', 'c'])


def test_collapse_does_not_change_page_order(tree):
    widget, nodes, folder, sub = tree
    folder_item = widget.find_item('group', folder)
    folder_item.setExpanded(False)
    assert widget.flatten_items() == ['a', 'b', 'c']
    assert widget.extract_tree()[0]['collapsed']


def test_reorder_group_inside_tree_preserves_all_pages(tree):
    widget, nodes, folder, sub = tree
    folder_item = widget.find_item('group', folder)
    moved = folder_item.takeChild(0)
    folder_item.insertChild(1, moved)
    actual = widget.extract_tree()
    assert widget.flatten_items() == ['b', 'a', 'c']
    validate(actual, ['b', 'a', 'c'])


def test_selection_reports_explicit_page_ids(tree):
    widget, nodes, folder, sub = tree
    widget.find_item('page', 'a').setSelected(True)
    widget.find_item('page', 'b').setSelected(True)
    assert widget.selected_page_ids() == ['a', 'b']
