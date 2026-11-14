"""UI-dependent quality/thumbnail stress tests (skip without Qt)."""
from pathlib import Path
from tempfile import TemporaryDirectory
import pytest

QtCore = pytest.importorskip('PySide6.QtCore')
QtWidgets = pytest.importorskip('PySide6.QtWidgets')
from yomunote.window import ProjectPane
from yomunote.project import Project


def test_moving_shelf_to_right_keeps_its_width_preset_and_adaptive_bucket():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    with TemporaryDirectory() as td:
        proj = Project.create(Path(td), 'Sidebars')
        pane = ProjectPane(proj, QtCore.QSettings(str(Path(td) / 's.ini'), QtCore.QSettings.Format.IniFormat))
        pane.resize(1450, 800)
        pane.show()
        app.processEvents()
        pane.move_workspace_panel('pages', 'notes', True)
        assert pane._panel_order == ['preview', 'notes', 'pages']
        assert pane.splitter.indexOf(pane.shelf) == 2
        pane.cycle_navigator_mode()
        assert pane.splitter.indexOf(pane.shelf) == 2
        assert pane._thumbnail_width_for_view() <= 420
        pane.save()
        loaded = Project.load(proj.path)
        assert loaded.panel_order == pane._panel_order
        pane.close()
