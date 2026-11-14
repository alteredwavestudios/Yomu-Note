"""Optional native Qt tests; run on Windows or macOS with PySide6 installed.

    python -m pytest tests/test_v073_smart_import_gui.py -q
"""
import os
import pytest
pytest.importorskip('PySide6')

from PySide6.QtWidgets import QApplication
from yomunote.import_options_dialog import ImportOptionsDialog
from yomunote.import_review_dialog import SmartImportReviewDialog


@pytest.fixture(scope='module')
def app():
    app = QApplication.instance() or QApplication([])
    return app


def test_options_make_destination_and_grouping_unambiguous(app):
    options = ImportOptionsDialog(smart=True, file_count=2,
        destination_groups=[('id-1', 'Module / Lecture'), ('id-2','Seminar')],
        target_group=None, files=('lecture.pdf', 'reading.pdf'))
    assert options.options()['group_id'] is None
    assert options.options()['smart_group_mode'] == 'per_file'
    options.destination.setCurrentIndex(1)
    assert options.options()['group_id'] == 'id-1'
    options.group_mode.setCurrentIndex(2)
    assert options.options()['smart_import'] is False
    assert options.structure.isEnabled() is False
    options.close()


def test_review_can_rename_rebound_and_undo_without_mutating_project(app):
    class ProjectLike:
        pages = [{'id':'already'}]
    original = [{'title':'Chapter One','start':1,'level':1,'origin':'PDF bookmark'},
                {'title':'Chapter Two','start':4,'level':1,'origin':'PDF bookmark'}]
    batches = [('Test source', [{'id':f'page-{i}'} for i in range(1,7)])]
    analyses = [{'sections':original,'warnings':[], 'source':'PDF bookmarks'}]
    dlg = SmartImportReviewDialog(None, ProjectLike(), batches, analyses,
        destination_label='Root of this tab', arrangement='per_file')
    dlg.tree.setCurrentItem(dlg._item_for_index(1))
    dlg.title_edit.setText('Corrected Chapter')
    dlg.start_spin.setValue(5)
    assert dlg._apply_fields()
    assert dlg.sections_by_file()[0][1]['start'] == 5
    assert dlg.sections_by_file()[0][1]['title'] == 'Corrected Chapter'
    assert ProjectLike.pages == [{'id':'already'}]
    dlg._undo()
    assert dlg.sections_by_file()[0][1]['start'] == 4
    dlg._redo()
    assert dlg.sections_by_file()[0][1]['start'] == 5
    dlg.reject()


def test_zero_bookmark_documents_allow_manual_chapters(app):
    class ProjectLike: pass
    pages = [{'id':f'p{i}'} for i in range(1,5)]
    dlg = SmartImportReviewDialog(None, ProjectLike(), [('No TOC',pages)],
         [{'sections':[], 'source':'No usable embedded bookmarks', 'warnings':[]}],
         destination_label='Root', arrangement='per_file')
    assert dlg.sections_by_file() == [[]]
    dlg._insert_heading(1)
    assert len(dlg.sections_by_file()[0]) == 1
    dlg._remove_heading()
    assert dlg.sections_by_file() == [[]]
    dlg.reject()
