"""Optional Qt checks; run on Windows/Mac with PySide6 installed.

On CI/Linux with a Qt plugin: QT_QPA_PLATFORM=offscreen python -m pytest -q
"""
from pathlib import Path
from tempfile import TemporaryDirectory
import pytest

QtCore = pytest.importorskip('PySide6.QtCore')
QtGui = pytest.importorskip('PySide6.QtGui')
QtWidgets = pytest.importorskip('PySide6.QtWidgets')
from yomunote.window import ProjectPane
from yomunote.project import Project
from yomunote.importers import blank_page


def new_pane(folder):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    project = Project.create(folder, 'v04 test')
    project.pages.append(blank_page(project))
    project.save()
    prefs = QtCore.QSettings(str(folder / 'settings.ini'), QtCore.QSettings.Format.IniFormat)
    pane = ProjectPane(project, prefs)
    pane.resize(900, 700)
    pane.show()
    app.processEvents()
    return app, pane


def test_fit_button_toggles_without_zoom_jump():
    with TemporaryDirectory() as tmp:
        app, pane = new_pane(Path(tmp))
        try:
            image = QtGui.QPixmap(600, 800)
            image.fill(QtGui.QColor('white'))
            pane.canvas.image_item.setPixmap(image)
            pane.canvas._reference_size = image.size()
            pane.canvas.canvas_scene.setSceneRect(0, 0, 600, 800)
            pane.canvas.fit_page()
            assert pane.fit_action.isChecked()
            before = pane.canvas.transform()
            pane.fit_action.trigger()  # second click releases fit
            assert not pane.fit_action.isChecked()
            assert not pane.canvas._fit
            assert pane.canvas.transform() == before
            pane.fit_action.trigger()  # third click fits again
            assert pane.fit_action.isChecked()
            assert pane.canvas._fit
            pane.canvas.zoom(1.25)
            assert not pane.fit_action.isChecked()  # manual zoom releases fit
        finally:
            pane.close_project()
            pane.close()


def test_navigator_keeps_original_pixmap_aspect_without_padding():
    with TemporaryDirectory() as tmp:
        app, pane = new_pane(Path(tmp))
        try:
            pane.pages_list.setIconSize(QtCore.QSize(220, 280))
            image = QtGui.QPixmap(200, 70)
            image.fill(QtGui.QColor('#e03f70'))
            unmodified = pane._thumbnail_decoration(image)
            assert unmodified.size() == image.size()  # no portrait stretching
            item = pane.pages_list.item(0)
            item.setData(QtCore.Qt.ItemDataRole.DecorationRole, unmodified)
            actual = item.data(QtCore.Qt.ItemDataRole.DecorationRole)
            assert isinstance(actual, QtGui.QPixmap)
            assert actual.width() / actual.height() == 200 / 70
        finally:
            pane.close_project()
            pane.close()
