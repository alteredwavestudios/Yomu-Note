"""Qt offscreen regression for Add Tab placement, scrolling and tab moves."""
import pytest
pytest.importorskip('PySide6.QtWidgets')
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication
from yomunote.window import MainWindow
from yomunote.notebook import Notebook


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


def test_plus_directly_after_last_tab_without_covering_drag_area(app, tmp_path):
    notebook = Notebook.create(tmp_path, 'Tab Strip Test')
    window = MainWindow()
    try:
        window.show_notebook(notebook)
        window.resize(1050, 690)
        window.show()
        app.processEvents()
        window._position_inline_tab_plus()
        app.processEvents()
        bar = window.tabs.tabBar()
        last_right = bar.mapTo(window.tabs, QPoint(bar.tabRect(0).right(), 0)).x()
        plus_left = window._add_tab_button.pos().x()
        assert bar.usesScrollButtons()
        assert window._tab_plus_corner.width() == 38
        assert window._add_tab_button.isVisible()
        assert not window._overflow_add_tab_button.isVisible()
        assert 0 < plus_left - last_right <= 12, (last_right, plus_left)
        assert window._add_tab_button.parent() is window.tabs

        for index in range(12):
            notebook.add_tab(f'A rather long notebook tab title {index}')
        window._resync_notebook_tabs()
        window.resize(800, 690)
        app.processEvents()
        window._position_inline_tab_plus()
        app.processEvents()
        assert window._tab_plus_corner.width() == 38
        assert window._overflow_add_tab_button.isVisible()
        assert not window._add_tab_button.isVisible()
    finally:
        window.close()
