"""Visual geometry regression: run on Windows/macOS with PySide6 installed."""
import pytest
pytest.importorskip('PySide6.QtWidgets')
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication
from yomunote.window import MainWindow
from yomunote.notebook import Notebook
from yomunote.vector_marks import make_shape


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


def _rect_in_panel(widget, panel):
    return widget.geometry().translated(widget.parentWidget().mapTo(panel, QPoint(0, 0)))


def _wait_for_preview(app, pane, timeout_seconds=25):
    """Wait for the async blank-page render before testing popup interactions.

    Adding a page starts a worker.  If a shape is selected before its preview
    arrives, the pending image-load callback rebuilds the graphics scene and
    clears that selection.  Popup geometry/hover tests should exercise the
    fully rendered page, not race the image worker.
    """
    from time import monotonic
    from PySide6.QtTest import QTest

    deadline = monotonic() + timeout_seconds
    while monotonic() < deadline:
        app.processEvents()
        if (pane._normal_preview_path is not None
                and not pane.canvas.image_item.pixmap().isNull()):
            return
        QTest.qWait(40)
    pytest.fail('Blank-page preview did not become ready before Quick Edit test')


@pytest.mark.parametrize('theme', ['washi', 'indigo'])
def test_quick_edit_rows_do_not_overlap_in_either_theme(app, tmp_path, theme):
    notebook = Notebook.create(tmp_path, 'Layout hotfix ' + theme)
    window = MainWindow()
    try:
        window.show_notebook(notebook)
        window.resize(1360, 920)
        window.show()
        app.processEvents()
        pane = window.active()
        pane.add_blank(0)
        _wait_for_preview(app, pane)
        pane.set_annotation_mode('rectangle')
        pane.add_shape(make_shape('rectangle', (.2, .2), (.6, .6), '#edaa40', .005,
                                  fill='#ee55aa', fill_opacity=40))
        window.set_theme(theme)
        pane.show_annotation_appearance()
        app.processEvents()
        panel = pane.annotation_quick_edit
        assert panel.isVisible(), (
            'Quick Edit hidden with selected annotation: '
            f'theme={theme}, viewport={pane.canvas.viewport().size()}, '
            f'panel={panel.size()}, selected={pane.canvas._selected_stroke is not None}, '
            f'dismissed={pane._quick_edit_dismissed}, '
            f'gesture={pane._quick_gesture_active}')
        for control in (pane.pen_colour, pane.fill_colour, pane.stroke_width_control,
                        pane.quick_thickness, pane.stroke_opacity_control,
                        pane.fill_opacity_control, pane.quick_palette):
            assert control.isVisibleTo(panel), f'{control.objectName() or type(control).__name__} is hidden'
            r = _rect_in_panel(control, panel)
            assert r.width() > 0 and r.height() > 0
            assert r.left() >= 0 and r.right() <= panel.width()
        # v0.5.4c intentionally uses two columns on wide previews. Verify
        # no overlapping rows WITHIN each column, in either theme.
        for widgets in ((pane.stroke_paint_row, pane.fill_paint_row),
                        (pane.quick_thickness_row, pane._opacity_rows['stroke'],
                         pane._opacity_rows['fill'])):
            rects = [_rect_in_panel(w, panel) for w in widgets]
            for above, below in zip(rects, rects[1:]):
                assert above.bottom() < below.top(), f'Overlapping Quick Edit rows: {above} / {below}'
            assert rects[-1].bottom() < panel.height()
        assert _rect_in_panel(pane.quick_palette, panel).bottom() < panel.height()
    finally:
        window.close()


def test_selected_colour_can_be_edited_and_undone(app, tmp_path):
    notebook = Notebook.create(tmp_path, 'Hotfix history')
    window = MainWindow()
    try:
        window.show_notebook(notebook)
        window.resize(1350, 900)
        window.show()
        app.processEvents()
        pane = window.active()
        pane.add_blank(0)
        _wait_for_preview(app, pane)
        pane.set_annotation_mode('rectangle')
        mark = make_shape('rectangle', (.2, .2), (.6, .6), '#eeb035', .003,
                          fill='#ff66aa', fill_opacity=50)
        pane.add_shape(mark)
        assert pane._appearance_selection_mark['id'] == mark['id']
        page_id = pane.current_page()['id']
        pane.show_annotation_appearance()
        pane._select_palette_channel('fill')
        pane._apply_palette_colour('#29b6a6', 'fill')
        assert pane.project.annotations[page_id][0]['fill'] == '#29b6a6'
        pane.history.undo()
        assert pane.project.annotations[page_id][0]['fill'] == '#ff66aa'
    finally:
        window.close()
