"""Qt smoke test: retired compression UI, unchanged raster swap geometry."""
from pathlib import Path
import pytest
QtCore = pytest.importorskip('PySide6.QtCore')
QtGui = pytest.importorskip('PySide6.QtGui')
QtWidgets = pytest.importorskip('PySide6.QtWidgets')
from yomunote.window import ProjectPane
from yomunote.project import Project
from yomunote.importers import blank_page


def test_compression_button_removed_and_replacement_keeps_zoom(tmp_path):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    project = Project.create(tmp_path, 'AB GUI')
    project.pages.append(blank_page(project))
    project.save()
    settings = QtCore.QSettings(str(Path(tmp_path) / 'prefs.ini'), QtCore.QSettings.Format.IniFormat)
    pane = ProjectPane(project, settings)
    pane.resize(1100, 780)
    pane.show()
    app.processEvents()
    try:
        assert not hasattr(pane, "lossless_action")  # diagnostic control retired in Stage 2
        from PIL import Image
        jpeg = project.path / 'cache' / 'previews' / 'test.jpg'
        jpeg.parent.mkdir(parents=True, exist_ok=True)
        Image.new('RGB', (400, 500), 'white').save(jpeg, quality=87)
        assert pane.canvas.show_image(jpeg)
        pane.canvas.zoom(1.25)
        before = pane.canvas.transform()
        assert pane.canvas.replace_quality_rgb(100, 125, Image.new('RGB', (100, 125), 'white').tobytes())
        assert pane.canvas.transform() == before
        assert pane.canvas._page_bounds().size() == QtCore.QSizeF(400, 500)
        assert pane.canvas.replace_quality_image(jpeg)
        assert pane.canvas.transform() == before
    finally:
        pane.close_project()
        pane.close()
