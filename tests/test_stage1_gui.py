"""Visual code-path smoke tests; executed with PySide6 on target machines.

Use QT_QPA_PLATFORM=offscreen for automated checks. Live zoom/trackpad
quality should ALSO be checked interactively on Windows and macOS.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
import pytest

QtCore = pytest.importorskip('PySide6.QtCore')
QtWidgets = pytest.importorskip('PySide6.QtWidgets')
QtGui = pytest.importorskip('PySide6.QtGui')
from yomunote.window import ProjectPane
from yomunote.project import Project


def make_pane(root):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    project = Project.create(root, 'Stage1')
    # Imported locally: blank_page belongs to the importers module.
    from yomunote.importers import blank_page
    project.pages.append(blank_page(project))
    project.save()
    settings = QtCore.QSettings(str(root / 'prefs.ini'), QtCore.QSettings.Format.IniFormat)
    pane = ProjectPane(project, settings)
    pane.resize(1000, 780)
    pane.show()
    app.processEvents()
    return app, pane


def test_navigator_icon_centre_and_number_independent_of_title():
    with TemporaryDirectory() as tmp:
        app, pane = make_pane(Path(tmp))
        option = QtWidgets.QStyleOptionViewItem()
        delegate = pane.pages_list.itemDelegate()
        delegate.initStyleOption(option, pane.pages_list.model().index(0, 0))
        assert option.decorationAlignment & QtCore.Qt.AlignmentFlag.AlignVCenter
        assert option.text == ''
        pane.close_project()
        pane.close()


def test_undo_annotations_and_autosave_do_not_erase_notes_history():
    with TemporaryDirectory() as tmp:
        app, pane = make_pane(Path(tmp))
        notes = pane.notes.editor
        notes.insertPlainText('Typing stays undoable')
        assert notes.document().isUndoAvailable()
        assert pane._save_timer.interval() == 60_000
        assert pane._save_timer.isSingleShot()
        assert pane._save_timer.isActive()  # typing starts dirty-only autosave
        mark = {'kind':'highlight','x':0.1,'y':0.2,'w':0.3,'h':0.1,'color':'#ffcf69'}
        page_id = pane.project.pages[0]['id']
        pane.add_highlight(mark)
        saved_mark = pane.project.annotations[page_id][0]
        # A legacy ID-less mark is accepted, but a *new* addition gets an ID.
        # This ID must survive Undo/Redo and disk persistence unchanged.
        assert {key: value for key, value in saved_mark.items() if key != 'id'} == mark
        assert isinstance(saved_mark['id'], str) and len(saved_mark['id']) == 32
        assert 'id' not in mark  # the caller's dict is never modified
        pane.undo_annotation()
        assert not pane.project.annotations.get(page_id)
        pane.redo_annotation()
        assert pane.project.annotations[page_id] == [saved_mark]
        pane.save()
        assert notes.document().isUndoAvailable()  # save isn't a reload
        assert Project.load(pane.project.path).annotations[page_id] == [saved_mark]
        pane.close_project()
        pane.close()


def test_horizontal_line_remains_html_and_undoable():
    with TemporaryDirectory() as tmp:
        app, pane = make_pane(Path(tmp))
        notes = pane.notes.editor
        notes.insertPlainText('Before')
        pane.notes.insert_horizontal_line()
        assert '<hr' in notes.toHtml().lower()
        assert notes.document().isUndoAvailable()
        pane.close_project()
        pane.close()
