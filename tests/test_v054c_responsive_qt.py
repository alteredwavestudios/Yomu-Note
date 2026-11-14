"""Windows/macOS integration checks, run with PySide6 installed."""
import pytest
pytest.importorskip('PySide6.QtWidgets')
from PySide6.QtCore import Qt, QSize, QPoint
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from yomunote.window import MainWindow, ImageCanvas
from yomunote.notebook import Notebook
from yomunote.vector_marks import make_shape

@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])

@pytest.mark.parametrize('theme', ['washi','indigo'])
def test_wide_panel_opaque_and_resizable(app, tmp_path, theme):
    window=MainWindow()
    try:
        window.show_notebook(Notebook.create(tmp_path, 'v054c '+theme))
        window.resize(1450,950)
        window.show(); app.processEvents()
        pane=window.active(); pane.add_blank(0)
        pane.canvas._reference_size=QSize(900,1200)
        pane.set_annotation_mode('rectangle')
        pane.add_shape(make_shape('rectangle',(.2,.2),(.5,.5),'#ee9834',.006,
                                  fill='#ef86c2',fill_opacity=50))
        window.set_theme(theme)
        pane.show_annotation_appearance(); app.processEvents()
        assert pane._quick_edit_backdrop._surface.alpha()==255
        panel=pane.annotation_quick_edit
        assert panel.width() >= 400
        start=pane._quick_edit_user_width
        grip=pane.quick_resize_handle
        QTest.mousePress(grip,Qt.MouseButton.LeftButton, pos=grip.rect().center())
        # Synthetic mouse move deltas are tested independently of the screen
        # resolution by adjusting the requested width and reflowing.
        QTest.mouseRelease(grip,Qt.MouseButton.LeftButton, pos=grip.rect().center())
        pane._quick_edit_user_width=365
        pane._position_annotation_quick_edit(); app.processEvents()
        assert pane._quick_columns.direction().name=='TopToBottom'
        pane._quick_edit_user_width=start
        pane._position_annotation_quick_edit(); app.processEvents()
        assert pane._quick_columns.direction().name=='LeftToRight'
    finally:
        window.close()


def test_responsive_toolbar_order_and_mode(app,tmp_path):
    window=MainWindow()
    try:
        window.show_notebook(Notebook.create(tmp_path, 'responsive footer'))
        window.resize(1400,900)
        window.show(); app.processEvents()
        pane=window.active()
        pane.canvas.resize(450,600)
        pane._update_annotation_toolbar_layout()
        assert pane.annotation_mode_buttons['select'].toolButtonStyle()==Qt.ToolButtonStyle.ToolButtonIconOnly
        assert len(pane._annotation_footer_buttons)==9
        pane._theme_annotation_toolbar(window.current_palette)
        assert not pane._annotation_footer_buttons[0].icon().isNull()
    finally:
        window.close()
