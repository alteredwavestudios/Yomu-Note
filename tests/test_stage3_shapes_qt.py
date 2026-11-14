"""Offscreen GUI regression tests for v0.5.1; run with PySide6 on Windows."""
import pytest
pytest.importorskip('PySide6.QtWidgets')
from PySide6.QtCore import QSize
from PySide6.QtWidgets import QApplication
from yomunote.window import ImageCanvas, MultiplyStrokeItem, MainWindow
from yomunote.notebook import Notebook
from yomunote.vector_marks import make_shape, make_stroke

@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


def test_live_pen_preview_starts_at_real_mouse_down_not_page_origin(app):
    canvas=ImageCanvas()
    canvas._reference_size=QSize(1000, 700)
    path=canvas._stroke_path([[.7,.4],[.75,.45],[.8,.5]])
    assert path.elementAt(0).x==pytest.approx(700.)
    assert path.elementAt(0).y==pytest.approx(280.)
    assert path.elementAt(path.elementCount()-1).x==pytest.approx(800.)
    canvas.close()


def test_marker_renders_as_multiply_item_but_legacy_ink_does_not(app):
    canvas=ImageCanvas()
    canvas._reference_size=QSize(1000, 700)
    marker=make_stroke([(.2,.2),(.3,.3)],'#00cc88',.009,blend='multiply')
    pen=make_stroke([(.2,.2),(.3,.3)],'#00cc88',.003)
    mi=canvas._draw_stroke(marker,0)
    pi=canvas._draw_stroke(pen,1)
    assert isinstance(mi, MultiplyStrokeItem)
    assert not isinstance(pi, MultiplyStrokeItem)
    canvas.close()


def test_shape_creation_resize_erase_and_undo_through_existing_history(app,tmp_path):
    notebook=Notebook.create(tmp_path,'Stage 3 Shapes')
    window=MainWindow()
    try:
        window.show_notebook(notebook)
        pane=window.active()
        pane.add_blank(0)
        page_id=pane.current_page()['id']
        shape=make_shape('rectangle',(.2,.2),(.3,.3),'#336699',.003,'#336699')
        pane.add_shape(shape)
        assert pane.project.annotations[page_id][-1]==shape
        resized={**shape,'x2':.7,'y2':.8}
        pane.resize_stroke(len(pane.project.annotations[page_id])-1,resized)
        assert pane.project.annotations[page_id][-1]==resized
        window.undo_shared()
        assert pane.project.annotations[page_id][-1]==shape
        window.redo_shared()
        assert pane.project.annotations[page_id][-1]==resized
        pane.erase_stroke(len(pane.project.annotations[page_id])-1)
        assert not pane.project.annotations.get(page_id)
        window.undo_shared()
        assert pane.project.annotations[page_id][-1]==resized
    finally:
        window.close()
