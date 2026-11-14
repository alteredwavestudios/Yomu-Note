"""v0.8.2 reading continuity: root-group zoom, independent scroll, safe metadata.

All pure-model tests run without a Qt display. The optional Canvas test uses
Qt's offscreen platform in the existing cross-platform test matrix.
"""
import math

from yomunote.reading_view import (
    clean_reading_view, effective_zoom, empty_view, fit_zoom,
    normalise_position, normalise_zoom, pages_in_group, remember_zoom,
    root_for_group, root_for_page, set_page_independent, set_root_shared,
)


def tree():
    return [
        {'type': 'group', 'id': 'a' * 32, 'name': 'Book', 'collapsed': False,
         'children': [
             {'type': 'page', 'page_id': 'p1'},
             {'type': 'group', 'id': 'b' * 32, 'name': 'Chapter',
              'collapsed': False, 'children': [
                  {'type': 'page', 'page_id': 'p2'},
                  {'type': 'page', 'page_id': 'p3'},
              ]},
         ]},
        {'type': 'page', 'page_id': 'solo'},
        {'type': 'group', 'id': 'c' * 32, 'name': 'Other book',
         'collapsed': False, 'children': [{'type': 'page', 'page_id': 'p4'}]},
    ]


def test_root_group_inheritance_including_nested_chapter():
    view = empty_view()
    assert root_for_page(tree(), 'p1') == 'a' * 32
    assert root_for_page(tree(), 'p2') == 'a' * 32
    assert root_for_page(tree(), 'solo') is None
    assert root_for_group(tree(), 'b' * 32) == 'a' * 32
    assert pages_in_group(tree(), 'b' * 32) == ['p2', 'p3']
    remember_zoom(view, tree(), 'p1', {'mode': 'manual', 'scale': 1.45})
    assert effective_zoom(view, tree(), 'p2')['scale'] == 1.45
    assert effective_zoom(view, tree(), 'p3')['scale'] == 1.45
    assert effective_zoom(view, tree(), 'p4') == fit_zoom()
    assert effective_zoom(view, tree(), 'solo') == fit_zoom()


def test_independent_page_override_and_rejoining_group():
    view = empty_view()
    remember_zoom(view, tree(), 'p1', {'mode': 'manual', 'scale': 1.45})
    set_page_independent(view, tree(), 'p2', True)
    remember_zoom(view, tree(), 'p2', {'mode': 'manual', 'scale': .85})
    assert effective_zoom(view, tree(), 'p2')['scale'] == .85
    assert effective_zoom(view, tree(), 'p1')['scale'] == 1.45
    set_page_independent(view, tree(), 'p2', False)
    assert effective_zoom(view, tree(), 'p2')['scale'] == 1.45


def test_disabling_group_sharing_snapshots_existing_scale():
    view = empty_view()
    remember_zoom(view, tree(), 'p1', {'mode': 'manual', 'scale': 1.45})
    set_root_shared(view, tree(), 'a' * 32, False)
    remember_zoom(view, tree(), 'p2', {'mode': 'manual', 'scale': 1.2})
    assert effective_zoom(view, tree(), 'p2')['scale'] == 1.2
    assert effective_zoom(view, tree(), 'p1')['scale'] == 1.45
    set_root_shared(view, tree(), 'a' * 32, True)
    assert effective_zoom(view, tree(), 'p2')['scale'] == 1.45
    assert effective_zoom(view, tree(), 'p1')['scale'] == 1.45


def test_multiple_positions_are_distinct_and_survive_sanitisation():
    view = empty_view()
    view['positions']['p1'] = {'x': .18, 'y': .82, 'bottom': True}
    view['positions']['p2'] = {'x': .1, 'y': 0., 'bottom': False}
    clean = clean_reading_view(view, ['p1', 'p2', 'p3'], tree())
    assert clean['positions']['p1']['bottom']
    assert clean['positions']['p2']['y'] == 0.
    assert clean['positions']['p1'] != clean['positions']['p2']


def test_malformed_values_and_deleted_objects_cannot_break_loading():
    raw = {
        'positions': {'p1': {'x': float('nan'), 'y': .1},
                      'p2': {'x': .2, 'y': .7, 'bottom': True},
                      'removed': {'x': .3, 'y': .4}},
        'group_zooms': {'a' * 32: {'mode': 'manual', 'scale': float('inf')},
                        'removed-group': {'mode': 'manual', 'scale': 1.5}},
        'page_zooms': {'p1': {'mode': 'manual', 'scale': -100}},
        'independent_pages': ['p1', 'ghost', 'p1'],
        'unshared_roots': ['b' * 32, 'a' * 32],
    }
    clean = clean_reading_view(raw, ['p1', 'p2', 'p3', 'solo', 'p4'], tree())
    assert 'p1' not in clean['positions']
    assert 'removed' not in clean['positions']
    assert clean['positions']['p2']['bottom']
    assert clean['group_zooms']['a' * 32] == fit_zoom()
    assert clean['page_zooms']['p1'] == fit_zoom()
    assert clean['independent_pages'] == ['p1']
    assert clean['unshared_roots'] == ['a' * 32]
    assert normalise_position({'x': -1, 'y': .2}) is None
    assert normalise_zoom({'mode': 'manual', 'scale': math.nan}) == fit_zoom()


def test_ungrouped_page_keeps_its_zoom():
    view = empty_view()
    remember_zoom(view, tree(), 'solo', {'mode': 'manual', 'scale': 2.0})
    assert effective_zoom(view, tree(), 'solo')['scale'] == 2.0
    assert effective_zoom(view, tree(), 'p1') == fit_zoom()


def test_canvas_restores_top_and_bottom_after_page_swap(tmp_path):
    pytest = __import__('pytest')
    pytest.importorskip('PySide6.QtWidgets')
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QImage, QColor
    from PySide6.QtWidgets import QApplication
    from yomunote.window import ImageCanvas

    app = QApplication.instance() or QApplication([])
    canvas = ImageCanvas()
    try:
        canvas.resize(380, 300)
        canvas.show()
        app.processEvents()
        img = QImage(700, 1400, QImage.Format.Format_RGB32)
        img.fill(QColor('white'))
        page = tmp_path / 'page.png'
        assert img.save(str(page))
        assert canvas.show_image(page)
        canvas.apply_reading_zoom({'mode': 'manual', 'scale': 1.0})
        canvas.restore_reading_position(None)
        app.processEvents()
        assert canvas.verticalScrollBar().value() <= 10
        canvas.verticalScrollBar().setValue(canvas.verticalScrollBar().maximum())
        saved = canvas.capture_reading_position()
        assert saved['bottom'] is True
        canvas.show_image(None)
        assert canvas.show_image(page)
        canvas.apply_reading_zoom({'mode': 'manual', 'scale': 1.0})
        canvas.restore_reading_position(saved)
        app.processEvents()
        assert canvas.verticalScrollBar().value() >= canvas.verticalScrollBar().maximum() - 3
    finally:
        canvas.close()


def test_project_json_persists_reading_view_without_format_bump(tmp_path):
    from yomunote.project import Project, FORMAT_VERSION
    from yomunote.page_groups import page_node

    project = Project.create(tmp_path, 'Reading Memory')
    project.pages = [{'id': 'p1', 'title': 'Page One'}]
    project.page_groups = [page_node('p1')]
    project.reading_view = empty_view()
    project.reading_view['positions']['p1'] = {
        'x': 0.23, 'y': 0.78, 'bottom': True}
    project.reading_view['page_zooms']['p1'] = {
        'mode': 'manual', 'scale': 1.5}
    project.save()

    reopened = Project.load(project.path)
    assert reopened.loaded_version == FORMAT_VERSION
    assert reopened.reading_view['positions']['p1']['bottom']
    assert reopened.reading_view['positions']['p1']['y'] == .78
    assert reopened.reading_view['page_zooms']['p1']['scale'] == 1.5
