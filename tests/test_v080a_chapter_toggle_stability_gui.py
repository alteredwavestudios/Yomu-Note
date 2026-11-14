"""Qt regression: never destroy the checkbox item while Qt dispatches its signal.

Run on Windows/macOS with PySide6, or QT_QPA_PLATFORM=offscreen. This is a
native GUI test and is intentionally skipped when PySide6 is unavailable.
"""
import pytest
pytest.importorskip('PySide6')
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from yomunote.import_review_dialog import SmartImportReviewDialog


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


def _dialog():
    class ProjectLike:
        pages = []
    pages = [{'id': f'page-{i}'} for i in range(1, 21)]
    sections = [
        {'title': 'Chapter 1', 'start': 1, 'level': 1},
        {'title': 'Section 1.1', 'start': 3, 'level': 2},
        {'title': 'Section 1.2', 'start': 6, 'level': 2},
        {'title': 'Chapter 2', 'start': 10, 'level': 1},
    ]
    return SmartImportReviewDialog(None, ProjectLike(), [('Course', pages)],
                                   [{'sections': sections, 'source':'PDF bookmarks', 'warnings':[]}],
                                   destination_label='Root', arrangement='per_file')


def test_repeated_checkbox_changes_preserve_qt_items_history_and_preview(app):
    dlg = _dialog()
    try:
        dlg.tree.expandAll()
        parent = dlg._item_for_index(0)
        child = dlg._item_for_index(1)
        dlg.tree.setCurrentItem(child)
        original_items = tuple(dlg._tree_section_items)
        generation = dlg._preview_generation
        for i in range(150):
            state = (Qt.CheckState.Unchecked if i % 2 == 0
                     else Qt.CheckState.Checked)
            parent.setCheckState(0, state)
            assert tuple(dlg._tree_section_items) == original_items
            assert dlg._item_for_index(1) is child
            assert dlg.tree.currentItem() is child
            assert dlg._enabled[0][:3] == [i % 2 == 1] * 3
            app.processEvents()
        # A checkbox change must not generate an expensive PDF preview rerender.
        assert dlg._preview_generation == generation
        assert dlg._enabled[0][3]
        dlg._undo()
        assert dlg._enabled[0][:3] == [False] * 3
        dlg._redo()
        assert dlg._enabled[0][:3] == [True] * 3
    finally:
        dlg.reject()


def test_bulk_toggle_and_mixed_parent_do_not_rebuild_and_accept_filtered_pages(app):
    dlg = _dialog()
    try:
        original_items = tuple(dlg._tree_section_items)
        for _ in range(100):
            dlg._toggle_all_chapters(False)
            dlg._toggle_all_chapters(True)
        assert tuple(dlg._tree_section_items) == original_items
        assert dlg._enabled[0] == [True] * 4
        dlg._item_for_index(1).setCheckState(0, Qt.CheckState.Unchecked)
        assert dlg._item_for_index(0).checkState(0) == Qt.CheckState.PartiallyChecked
        assert dlg._choices_for_file(0) == [1,2,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20]
        dlg._accept_checked()
        assert dlg.selected_pages_by_file()[0] == dlg._choices_for_file(0)
    finally:
        dlg.reject()


def test_edit_title_inside_item_changed_does_not_recreate_qt_item(app):
    dlg = _dialog()
    try:
        item = dlg._item_for_index(0)
        item.setText(0, 'New chapter name')
        assert item is dlg._item_for_index(0)
        assert dlg.sections_by_file()[0][0]['title'] == 'New chapter name'
        assert item.text(2) == 'Edited in review'
        dlg._undo()
        assert dlg.sections_by_file()[0][0]['title'] == 'Chapter 1'
    finally:
        dlg.reject()
