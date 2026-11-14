"""Offscreen Qt tests for the v0.5.2 appearance UI; run on Windows/macOS.

These tests intentionally skip rather than fake Qt when PySide6 isn't present.
"""
import pytest
pytest.importorskip('PySide6.QtWidgets')
from PySide6.QtCore import QSize, Qt, QSignalBlocker
from PySide6.QtWidgets import QApplication
from yomunote.window import ImageCanvas, MultiplyStrokeItem, MainWindow
from yomunote.notebook import Notebook
from yomunote.vector_marks import make_shape, make_highlight_line

@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


def test_highlighter_modes_always_multiply_and_line_has_flat_cap(app):
    canvas = ImageCanvas()
    canvas._reference_size = QSize(800, 1100)
    try:
        old = {'kind':'highlight','x':.1,'y':.1,'w':.3,'h':.05,'color':'#ffaa11'}
        line = make_highlight_line((.1,.3),(.9,.3),'#ffdd44',.015,45)
        canvas.set_annotations([old,line])
        rect_item, line_item = canvas._marks
        assert isinstance(rect_item, MultiplyStrokeItem)
        assert isinstance(line_item, MultiplyStrokeItem)
        assert line_item.pen().capStyle() == Qt.PenCapStyle.FlatCap
        assert line_item.pen().color().alphaF() == pytest.approx(.45, abs=.01)
        assert rect_item.brush().color().alpha() == 92  # legacy colour exactly
    finally:
        canvas.close()


def test_selected_fill_and_stroke_edit_undo_without_changing_tool_defaults(app,tmp_path):
    notebook = Notebook.create(tmp_path, 'Appearance')
    window = MainWindow()
    try:
        window.show_notebook(notebook)
        pane = window.active()
        pane.add_blank(0)
        page = pane.current_page()['id']
        mark = make_shape('rectangle', (.1,.1),(.6,.6),'#112233',.003)
        pane.add_shape(mark)
        pane.set_annotation_mode('select')
        pane._annotation_selection_changed(0, mark)
        original_default = dict(pane.canvas.tool_styles['rectangle'])
        pane.pen_colour.set_colour('#ff0000')
        pane.fill_colour.set_colour('#ffdd88')
        with QSignalBlocker(pane.shape_fill_checkbox):
            pane.shape_fill_checkbox.setChecked(True)
        pane.fill_opacity_control.setValue(100)
        pane.stroke_width_control.setValue(12)
        pane._appearance_changed()
        edited = pane.project.annotations[page][0]
        assert edited['color'] == '#ff0000'
        assert edited['fill'] == '#ffdd88'
        assert edited['fill_opacity'] == 100
        assert edited['width'] == pytest.approx(.012)
        assert pane.canvas.tool_styles['rectangle'] == original_default
        window.undo_shared()
        assert pane.project.annotations[page][0] == mark
        window.redo_shared()
        assert pane.project.annotations[page][0] == edited
    finally:
        window.close()


def test_erase_one_legacy_highlight_without_erasing_siblings(app,tmp_path):
    notebook=Notebook.create(tmp_path,'Old highlights')
    window=MainWindow()
    try:
        window.show_notebook(notebook)
        pane=window.active()
        pane.add_blank(0)
        page=pane.current_page()['id']
        one={'kind':'highlight','x':.1,'y':.1,'w':.3,'h':.05,'color':'#ffaa33'}
        two={'kind':'highlight','x':.1,'y':.3,'w':.3,'h':.05,'color':'#ffcc33'}
        pane._apply_annotation_snapshot(page,[one,two])
        pane.erase_stroke(0)
        assert pane.project.annotations[page]==[two]
        window.undo_shared()
        assert pane.project.annotations[page]==[one,two]
    finally:
        window.close()
