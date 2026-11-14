"""Smoke tests when PySide6 can be installed on the target OS.

These are intentionally skipped in pure-Python CI. Test the drag animation
and native trackpad behaviour manually on Windows/macOS as well.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
import pytest

QtCore = pytest.importorskip('PySide6.QtCore')
QtWidgets = pytest.importorskip('PySide6.QtWidgets')
from yomunote.window import ProjectPane
from yomunote.project import Project


def test_reorder_existing_widgets_preserves_editor_and_save_state():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    with TemporaryDirectory() as td:
        project = Project.create(Path(td), 'GUI layout')
        settings = QtCore.QSettings(str(Path(td) / 'settings.ini'), QtCore.QSettings.Format.IniFormat)
        pane = ProjectPane(project, settings)
        pane.resize(1200, 750)
        pane.show()
        app.processEvents()
        editor = pane.notes.editor
        editor.insertPlainText('This must never disappear on reordering.')
        original_widgets = dict(pane._panel_widgets)
        for order in [('notes','preview','pages'), ('preview','pages','notes'),
                      ('pages','notes','preview'), ('pages','preview','notes')]:
            pane.apply_panel_order(order)
            assert [pane.splitter.widget(i) for i in range(3)] == [original_widgets[k] for k in order]
            assert pane.notes.editor is editor
            assert 'never disappear' in editor.toPlainText()
        pane.move_workspace_panel('notes', 'pages', False)
        assert pane._panel_order == ['notes', 'pages', 'preview']
        pane.save()
        assert Project.load(project.path).panel_order == pane._panel_order
        pane.close()
