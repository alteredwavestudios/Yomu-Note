"""UI regression checks to run on a Windows/macOS machine with PySide6."""
import pytest
pytest.importorskip('PySide6.QtWidgets')
from PySide6.QtCore import QSize
from PySide6.QtWidgets import QApplication
from yomunote.window import MainWindow
from yomunote.notebook import Notebook
from yomunote.vector_marks import make_shape


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


def test_inline_thickness_and_colour_controls_modify_selected_shape_once(app, tmp_path):
    notebook = Notebook.create(tmp_path, 'v054 Quick Edit')
    window = MainWindow()
    try:
        window.show_notebook(notebook)
        window.show()
        app.processEvents()
        pane = window.active()
        pane.add_blank(0)
        pane.canvas._reference_size = QSize(900, 1200)
        mark = make_shape('rectangle', (.2, .2), (.6, .6), '#efaa42', .003,
                          fill='#dd55bb', fill_opacity=40)
        pane.set_annotation_mode('rectangle')
        pane.add_shape(mark)
        assert pane._appearance_selection_mark['id'] == mark['id']
        assert pane.annotation_quick_edit.layout().indexOf(pane.appearance_panel) >= 0
        pane.quick_thickness.setValue(130)
        pane.quick_thickness.editFinished.emit()
        page_id = pane.current_page()['id']
        assert pane.project.annotations[page_id][0]['width'] == pytest.approx(.013)
        pane.history.undo()
        assert pane.project.annotations[page_id][0]['width'] == pytest.approx(.003)
        pane.show_annotation_appearance()
        assert not pane.annotation_quick_edit.isHidden()
        pane._dismiss_annotation_quick_edit()
        assert pane.annotation_quick_edit.isHidden()
    finally:
        window.close()


def test_theme_and_hideable_shelf_controls(app, tmp_path):
    notebook = Notebook.create(tmp_path, 'v054 navigator')
    window = MainWindow()
    try:
        window.show_notebook(notebook)
        window.show()
        app.processEvents()
        pane = window.active()
        window.set_theme('washi')
        light = pane._quick_edit_backdrop._surface
        assert light.name().lower() == '#fff8fa' and light.alpha() == 255
        assert 'background: transparent' in pane.annotation_quick_edit.styleSheet().lower()
        window.set_theme('indigo')
        dark = pane._quick_edit_backdrop._surface
        assert dark.name().lower() == '#25344a' and dark.alpha() == 255
        assert dark.name() != light.name()
        window._set_all_navigator_visibility(False)
        assert pane.shelf.isHidden()
        assert not window.navigator_visibility_action.isChecked()
        window._set_all_navigator_visibility(True)
        assert not pane.shelf.isHidden()
        assert window.navigator_visibility_action.isChecked()
    finally:
        window.close()
