"""Desktop regression tests; run with PySide6 on Windows/macOS."""
import pytest
pytest.importorskip('PySide6.QtWidgets')
from PySide6.QtCore import QSize
from PySide6.QtWidgets import QApplication
from yomunote.window import ImageCanvas, MainWindow
from yomunote.notebook import Notebook
from yomunote.vector_marks import make_shape


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


def test_pointed_arrow_and_nonrounded_rectangle(app):
    canvas = ImageCanvas()
    try:
        canvas._reference_size = QSize(900, 1200)
        arrow = make_shape('arrow',(.1,.3),(.7,.3),'#ff5588', .04,
                           head_width=.09,head_length=.1)
        path = canvas._shape_path(arrow)
        assert path.elementCount() >= 7
        item = canvas._draw_shape(arrow, 0)
        assert item.brush().color().alpha() > 0
        assert item.pen().style().name == 'NoPen'
        rect = make_shape('rectangle',(.2,.2),(.6,.6),'#ff5588',.04)
        item = canvas._draw_shape(rect, 1)
        assert item.pen().joinStyle().name == 'MiterJoin'
    finally:
        canvas.close()


def test_quick_edit_shape_selection_and_undo(app, tmp_path):
    notebook = Notebook.create(tmp_path, 'Quick edit')
    window = MainWindow()
    try:
        window.show_notebook(notebook)
        pane = window.active()
        pane.add_blank(0)
        pane.canvas._reference_size = QSize(900, 1200)
        mark = make_shape('arrow',(.2,.4),(.7,.4),'#aabbcc',.003)
        pane.set_annotation_mode('arrow')
        pane.add_shape(mark)
        assert pane.canvas.annotation_tool == 'select'
        assert pane.canvas._selected_stroke is not None
        assert pane._appearance_selection_mark['id'] == mark['id']
        assert pane.arrow_size_row.isVisible() or not pane.annotation_quick_edit.isVisible()
        pane.quick_thickness.setValue(120)
        pane.quick_thickness.editFinished.emit()
        after = pane.project.annotations[pane.current_page()['id']][0]
        assert after['width'] == pytest.approx(.012)
        window.undo_shared()
        assert pane.project.annotations[pane.current_page()['id']][0]['width'] == .003
        pane._dismiss_annotation_quick_edit()
        pane._position_annotation_quick_edit()
        assert pane.annotation_quick_edit.isHidden()
    finally:
        window.close()


def test_toolbar_structure_navigation_preserves_actions(app, tmp_path):
    notebook = Notebook.create(tmp_path, 'Toolbar')
    window = MainWindow()
    try:
        window.show_notebook(notebook)
        pane = window.active()
        assert pane.navigator_previous.toolTip().startswith('Previous page · ')
        assert pane.preview_next.toolTip().startswith('Next page · ')
        pane.set_annotation_mode('highlight_line')
        assert pane.highlight_button.isChecked()
        pane.set_annotation_mode('pen')
        assert pane._annotation_group_buttons['drawing'].isChecked()
        assert pane._annotation_last_tool['drawing'] == 'pen'
        assert pane.stroke_width_control.maximum() == 100
    finally:
        window.close()
