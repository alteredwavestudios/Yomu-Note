"""Mouse-hover and sibling-backdrop checks. Requires PySide6 GUI runtime.

Run on Windows in the actual app environment. These are not headless proofs
of every graphics driver, but reproduce the previously troublesome actions.
"""
import pytest
pytest.importorskip('PySide6.QtWidgets')
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QToolButton
from yomunote.window import MainWindow
from yomunote.notebook import Notebook
from yomunote.vector_marks import make_shape


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


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
def test_hover_does_not_hide_controls_or_destroy_backdrop(app, tmp_path, theme):
    notebook = Notebook.create(tmp_path, 'Quick Edit repaint ' + theme)
    window = MainWindow()
    try:
        window.show_notebook(notebook)
        window.resize(1360, 900)
        window.show()
        app.processEvents()
        pane = window.active()
        pane.add_blank(0)
        _wait_for_preview(app, pane)
        pane.set_annotation_mode('rectangle')
        mark = make_shape('rectangle', (.2, .2), (.65, .55), '#ee9834', .006,
                          fill='#ef86c2', fill_opacity=50)
        pane.add_shape(mark)
        window.set_theme(theme)
        pane.show_annotation_appearance()
        app.processEvents()
        panel, background = pane.annotation_quick_edit, pane._quick_edit_backdrop
        assert panel.graphicsEffect() is None
        assert background.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        assert background.isVisible(), (
            f'Quick Edit backdrop hidden: theme={theme}, '
            f'viewport={pane.canvas.viewport().size()}, panel={panel.geometry()}, '
            f'panel_visible={panel.isVisible()}, selected={pane.canvas._selected_stroke is not None}, '
            f'dismissed={pane._quick_edit_dismissed}, gesture={pane._quick_gesture_active}')
        swatches = pane.quick_palette.findChildren(QToolButton)
        controls = [pane.pen_colour, pane.fill_colour, pane.stroke_width_control,
                    pane.quick_thickness, pane.stroke_opacity_control,
                    pane.fill_opacity_control, *swatches]
        for control in controls:
            if not control.isVisibleTo(panel):
                continue  # recent-colour placeholders deliberately start hidden
            QTest.mouseMove(control, control.rect().center())
            app.processEvents()
            assert panel.isVisible(), (
                f'Quick Edit disappeared on hover: theme={theme}, '
                f'control={type(control).__name__}, '
                f'viewport={pane.canvas.viewport().size()}, panel={panel.geometry()}')
            assert background.isVisible()
            assert control.isVisibleTo(panel)
            assert control.rect().width() > 0 and control.rect().height() > 0
        delta = QPoint(9, 8)
        panel.move(panel.pos() + delta)
        app.processEvents()
        margin = background.MARGIN
        assert background.geometry() == panel.geometry().adjusted(
            -margin, -margin, margin, margin)
        panel.hide()
        app.processEvents()
        assert not background.isVisible()
    finally:
        window.close()


def test_new_highlighter_defaults_are_100_percent(app):
    from yomunote.window import ImageCanvas
    canvas = ImageCanvas()
    try:
        for tool in ('marker', 'highlight', 'highlight_line'):
            assert canvas.tool_styles[tool]['opacity'] == 100
    finally:
        canvas.close()
