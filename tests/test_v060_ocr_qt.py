"""Interactive canvas checks for Windows/macOS with PySide6 installed.

Run with QT_QPA_PLATFORM=offscreen for CI; repeat manually on Windows with
high-DPI scaling and a very narrow centre preview column.
"""
import pytest
pytest.importorskip('PySide6.QtWidgets')
from PIL import Image
from PySide6.QtCore import QPointF, Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from yomunote.window import ImageCanvas, MainWindow
from yomunote.notebook import Notebook


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


def test_ocr_selection_survives_zoom_scroll_and_does_not_create_annotations(app, tmp_path):
    path = tmp_path / 'very-long.png'
    Image.new('RGB', (900, 3600), 'white').save(path)
    canvas = ImageCanvas()
    try:
        canvas.resize(480, 600)
        canvas.show(); app.processEvents()
        assert canvas.show_image(path)
        canvas.set_annotation_tool('ocr')
        bounds = canvas._page_bounds()
        first = canvas.mapFromScene(QPointF(bounds.width() * .12, bounds.height() * .10))
        second = canvas.mapFromScene(QPointF(bounds.width() * .52, bounds.height() * .19))
        QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=first)
        QTest.mouseMove(canvas.viewport(), pos=second)
        QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=second)
        app.processEvents()
        saved = canvas.ocr_regions()
        assert len(saved) == 1 and saved[0][2] > .2
        assert not canvas._marks  # no permanent annotation added
        canvas.zoom(2.0)
        canvas.verticalScrollBar().setValue(130)
        app.processEvents()
        assert canvas.ocr_regions() == saved
        canvas.select_whole_ocr_page()
        assert canvas.ocr_regions() == [(0., 0., 1., 1.)]
        canvas.undo_ocr_region()
        assert canvas.ocr_regions() == []
        canvas.set_annotation_tool('pan')
        assert not canvas._ocr_mask.isVisible()
    finally:
        canvas.close()


def test_contextual_pen_slider_is_only_visible_for_pen(app, tmp_path):
    window = MainWindow()
    try:
        window.show_notebook(Notebook.create(tmp_path, 'v060 pen size'))
        window.resize(1320, 900)
        window.show(); app.processEvents()
        pane = window.active()
        pane.add_blank(0)
        pane.set_annotation_mode('pen')
        app.processEvents()
        assert pane.pen_size_widget.isVisible()
        pane.pen_size_slider.setValue(19)
        assert pane.canvas.tool_styles['pen']['width'] == pytest.approx(.0095)
        pane.set_annotation_mode('select')
        app.processEvents()
        assert not pane.pen_size_widget.isVisible()
    finally:
        window.close()
