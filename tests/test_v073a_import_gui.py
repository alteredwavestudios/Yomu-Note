"""Run these optional GUI checks with PySide6, e.g. Windows Python."""
import pytest
pytest.importorskip('PySide6')

from PySide6.QtWidgets import QApplication, QDialogButtonBox
from yomunote.import_options_dialog import ImportOptionsDialog
from yomunote.import_review_dialog import SmartImportReviewDialog


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


def test_collapse_checked_by_default_toggleable_and_no_group_disabled(app):
    dialog = ImportOptionsDialog(smart=True, file_count=1, files=('lecture.pdf',),
                                 preset='custom', custom='Chapter [chapter] — Page [page]')
    assert dialog.collapse_groups.isChecked()
    assert dialog.options()['collapse_new_groups'] is True
    assert dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).isEnabled()
    dialog.collapse_groups.setChecked(False)
    assert dialog.options()['collapse_new_groups'] is False
    dialog.group_mode.setCurrentIndex(2)  # No file groups
    assert not dialog.collapse_groups.isEnabled()
    dialog.close()


def test_review_outline_defaults_to_collapsed_with_expand_switch(app):
    class ProjectLike: pass
    pages = [{'id':f'p{i}'} for i in range(1,6)]
    analyses = [{'sections':[{'title':'Chapter 1','start':1,'level':1},
                              {'title':'Section A','start':2,'level':2}],
                 'warnings':[], 'source':'PDF bookmarks'}]
    dlg = SmartImportReviewDialog(None, ProjectLike(), [('Text',pages)], analyses,
        destination_label='Root', arrangement='per_file')
    root = dlg.tree.topLevelItem(0)
    assert not dlg.expand_review.isChecked()
    assert not root.isExpanded()
    dlg.expand_review.setChecked(True)
    assert root.isExpanded()
    dlg.expand_review.setChecked(False)
    assert not root.isExpanded()
    dlg.reject()
