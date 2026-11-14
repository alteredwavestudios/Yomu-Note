"""Desktop checks for the v0.7.0a page-group navigator.

Run with PySide6 on Windows/macOS. Headless environments skip this.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import pytest
pytest.importorskip('PySide6.QtWidgets')
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QApplication
from yomunote.page_groups import flat_tree, group_pages
from yomunote.page_groups_ui import (
    PageGroupsTree, ROLE_ACTIVE, ROLE_ACTIVE_ANCESTOR,
)


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def widget(app):
    tree, gid = group_pages(flat_tree(['a', 'b', 'c']), ['a', 'b'], 'Week 1')
    view = PageGroupsTree()
    view.load_tree(tree, [{'id': p, 'title': f'Page {p}'} for p in 'abc'], 'a')
    view.resize(320, 420)
    view.show()
    app.processEvents()
    yield view, gid
    view.close()


def test_navigation_does_not_clear_multi_selection(widget, app):
    view, gid = widget
    page_a = view.find_item('page', 'a')
    page_b = view.find_item('page', 'b')
    page_a.setSelected(True)
    page_b.setSelected(True)
    view.mark_active('c')
    assert set(view.selected_page_ids()) == {'a', 'b'}
    assert bool(view.find_item('page', 'c').data(0, ROLE_ACTIVE))
    app.processEvents()


def test_collapsed_group_marks_active_descendant(widget):
    view, gid = widget
    folder = view.find_item('group', gid)
    folder.setExpanded(False)
    view.mark_active('b')
    assert bool(folder.data(0, ROLE_ACTIVE_ANCESTOR))
    assert not bool(folder.isExpanded())


def test_only_selected_group_counts_as_import_destination(widget):
    view, gid = widget
    assert view.selected_group_id() is None
    folder = view.find_item('group', gid)
    folder.setSelected(True)
    assert view.selected_group_id() == gid
    view.mark_active('c')
    assert view.selected_group_id() == gid


def test_page_thumbnails_scale_and_evict(widget):
    view, gid = widget
    pixmap = QPixmap(70, 120)
    pixmap.fill(QColor('#bada55'))
    view.set_page_thumbnail('a', pixmap)
    assert not view.find_item('page', 'a').icon(0).isNull()
    view.discard_other_thumbnails(set())
    assert view.find_item('page', 'a').icon(0).isNull()
