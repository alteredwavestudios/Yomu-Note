"""Optional native PySide6 validation for the Smart Import 3.0 review dialog.

Run with a native Qt installation (Windows/macOS) or QT_QPA_PLATFORM=offscreen.
"""
import pytest
pytest.importorskip('PySide6')
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog
from yomunote.import_review_dialog import SmartImportReviewDialog

@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


def _dlg():
    class ProjectLike:
        pages=[]
    batch = [('Coursebook', [{'id':f'p{i}'} for i in range(1,13)])]
    headings = [{'title':'Preface','start':1,'level':1},
                {'title':'Chapter One','start':3,'level':1},
                {'title':'Section 1.1','start':5,'level':2},
                {'title':'Chapter Two','start':9,'level':1}]
    return SmartImportReviewDialog(None, ProjectLike(), batch,
        [{'sections':headings, 'source':'PDF bookmarks', 'warnings':[]}],
        destination_label='Root', arrangement='per_file')


def test_ranges_bookmarks_intersection_and_filter_review(app):
    dlg=_dlg()
    try:
        assert dlg._choices_for_file(0)==list(range(1,13))
        dlg.all_pages_check.setChecked(False)
        dlg.page_range_edit.setText('2-6,10-12')
        assert dlg._choices_for_file(0)==[2,3,4,5,6,10,11,12]
        # Unchecking a parent also excludes all its descendants.
        dlg._item_for_index(1).setCheckState(0, Qt.CheckState.Unchecked)
        assert dlg._choices_for_file(0)==[2,10,11,12]
        dlg._accept_checked()
        assert dlg.result()==QDialog.DialogCode.Accepted
        assert dlg.selected_pages_by_file()==[[2,10,11,12]]
    finally:
        dlg.close()


def test_review_undo_restores_chapter_filters_and_reset(app):
    dlg=_dlg()
    try:
        dlg._toggle_all_chapters(False)
        assert dlg._enabled[0]==[False]*4
        dlg._undo()
        assert dlg._enabled[0]==[True]*4
        dlg._redo()
        assert dlg._enabled[0]==[False]*4
        dlg._reset()
        assert dlg._enabled[0]==[True]*4
        assert len(dlg.sections_by_file()[0])==4
    finally:
        dlg.reject()
