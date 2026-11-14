"""Offscreen Qt scenarios for the selection crash and simplified colour UI.

These run with PySide6 on Windows/macOS. No fake Qt widgets are used.
"""
import pytest
pytest.importorskip('PySide6.QtWidgets')
from PySide6.QtCore import QSize, QSignalBlocker
from PySide6.QtWidgets import QApplication
from yomunote.window import ImageCanvas, MainWindow
from yomunote.notebook import Notebook
from yomunote.vector_marks import make_shape, make_stroke, make_highlight_line


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize('kind', ['rectangle', 'arrow', 'stroke', 'highlight_line'])
def test_selection_handles_accept_qrectf_directly(app, kind):
    canvas = ImageCanvas()
    canvas._reference_size = QSize(850, 1100)
    try:
        if kind == 'stroke':
            mark = make_stroke([[.2,.2],[.3,.25],[.4,.3]], '#ff0033', .004)
        elif kind == 'highlight_line':
            mark = make_highlight_line((.2,.2),(.8,.3),'#ffcc11', .012, 40)
        else:
            mark = make_shape(kind, (.2,.2),(.7,.7),'#ff0033', .004)
        canvas.set_annotation_tool('select')
        canvas.set_annotations([mark])
        canvas._selected_stroke = canvas._marks[0]
        canvas._show_resize_handles()
        assert canvas._selection_outline is not None
        assert set(canvas._selection_handles) == (
            {'start', 'end'} if kind in ('arrow', 'highlight_line')
            else {'tl', 'tr', 'bl', 'br'})
        canvas._show_resize_handles()  # pointer movement must not throw either
    finally:
        canvas.close()


def test_palette_recolour_selected_annotation_undo_and_keep_opacity(app, tmp_path):
    notebook = Notebook.create(tmp_path, 'Layout hotfix')
    window = MainWindow()
    try:
        window.show_notebook(notebook)
        pane = window.active()
        pane.add_blank(0)
        page_id = pane.current_page()['id']
        mark = make_shape('rectangle', (.1,.1),(.6,.6),'#112233', .003,
                          fill='#8899aa', opacity=65, fill_opacity=22)
        pane.add_shape(mark)
        pane.set_annotation_mode('select')
        pane._annotation_selection_changed(0, mark)
        assert pane.stroke_opacity_control.value() == 65
        assert pane.fill_opacity_control.value() == 22
        pane._apply_palette_colour('#ff5555', 'fill')
        after = pane.project.annotations[page_id][0]
        assert after['fill'] == '#ff5555'
        assert after['fill_opacity'] == 22
        assert after['opacity'] == 65
        window.undo_shared()
        assert pane.project.annotations[page_id][0] == mark
        window.redo_shared()
        assert pane.project.annotations[page_id][0] == after
    finally:
        window.close()


def test_colour_swap_never_changes_alpha(app, tmp_path):
    notebook = Notebook.create(tmp_path, 'Swap test')
    window = MainWindow()
    try:
        window.show_notebook(notebook)
        pane = window.active()
        pane.add_blank(0)
        mark = make_shape('ellipse', (.2,.2),(.7,.7),'#115599', .006,
                          fill='#ff8844', opacity=45, fill_opacity=80)
        pane.add_shape(mark)
        pane.set_annotation_mode('select')
        pane._annotation_selection_changed(0, mark)
        pane._swap_annotation_colours()
        changed = pane.project.annotations[pane.current_page()['id']][0]
        assert changed['color'] == '#ff8844'
        assert changed['fill'] == '#115599'
        assert changed['opacity'] == 45
        assert changed['fill_opacity'] == 80
    finally:
        window.close()
