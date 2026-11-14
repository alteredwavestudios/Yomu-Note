"""v0.5.2 appearance / highlights with no Qt dependency.

These prove the existing format v4 accepts old and new annotations; geometry,
transparency, IDs, and independent stroke/fill values survive a full save.
"""
import copy
import json
import pytest
from yomunote.project import Project, FORMAT_VERSION
from yomunote.vector_marks import (
    make_highlight, make_highlight_line, make_shape, make_stroke,
    valid_highlight, valid_shape, valid_stroke, valid_vector,
    translated_vector, resized_vector, vector_bounds,
    add_mark, remove_stroke, restore_stroke,
)


def test_new_fills_and_strokes_have_independent_opacity_and_optional_outline():
    mark = make_shape('ellipse', (.2, .3), (.7, .8), '#556677', .009,
                      fill='#eeddff', opacity=5, fill_opacity=100,
                      stroke_enabled=False)
    assert valid_shape(mark)
    assert mark['color'] != mark['fill']
    assert mark['opacity'] == 5
    assert mark['fill_opacity'] == 100
    assert mark['stroke_enabled'] is False
    assert valid_shape({**mark, 'opacity': 0, 'fill_opacity': 0})
    assert valid_shape({**mark, 'opacity': 100, 'fill_opacity': 100})
    assert valid_shape({**mark, 'stroke_enabled': True, 'fill': None})


@pytest.mark.parametrize('wrong', [-1, 101, float('nan'), float('inf'), True, '35'])
def test_opacity_bounds_reject_invalid_input(wrong):
    s = make_stroke([(.2, .3), (.5, .6)], '#445566', .003, opacity=37)
    e = make_shape('rectangle', (.1, .1), (.8, .8), '#445566', .002, '#ffddcc')
    h = make_highlight((.1, .2, .3, .4), '#ffaa33')
    l = make_highlight_line((.1, .4), (.9, .4), '#ffaa33', .014)
    for mark in (s, e, h, l):
        assert not valid_vector({**mark, 'opacity': wrong})
    assert not valid_shape({**e, 'fill_opacity': wrong})


def test_line_highlighter_is_editable_multiply_vector_with_flat_geometry():
    line = make_highlight_line((.2, .4), (.8, .4), '#ffe16b', .014, 29)
    assert line['kind'] == 'highlight_line'
    assert line['opacity'] == 29
    assert valid_highlight(line)
    assert vector_bounds(line) == (.2, .4, .8, .4)
    moved = translated_vector(line, .1, .25)
    assert (moved['x1'], moved['y1']) == pytest.approx((.3, .65))
    assert moved['id'] == line['id']
    resized = resized_vector(line, 'end', .95, .55)
    assert resized['id'] == line['id']
    assert (resized['x2'], resized['y2']) == (.95, .55)
    assert line['x2'] == .8


def test_legacy_highlights_have_optional_id_and_alpha_and_support_resize():
    old = {'kind': 'highlight', 'x': .1, 'y': .2, 'w': .3, 'h': .08,
           'color': '#f0c26b'}
    assert valid_highlight(old)
    assert vector_bounds(old) == pytest.approx((.1, .2, .4, .28))
    moved = translated_vector(old, .2, .1)
    assert moved['x'] == pytest.approx(.3)
    assert moved['y'] == pytest.approx(.3)
    resized = resized_vector(old, 'br', .6, .4)
    assert resized['w'] == pytest.approx(.5)
    assert resized['h'] == pytest.approx(.2)
    assert resized.get('id') is None
    assert old['w'] == .3


def test_new_rectangle_highlighter_carries_id_and_alpha():
    h = make_highlight((.1, .2, .5, .2), '#ffdd55', 35)
    assert valid_highlight(h)
    assert len(h['id']) > 10
    assert resized_vector(h, 'br', .8, .5)['id'] == h['id']
    assert not valid_highlight({**h, 'x': .8, 'w': .4})


def test_old_anonymous_highlights_can_restore_without_touching_others():
    a = {'kind':'highlight','x':.1,'y':.1,'w':.2,'h':.1,'color':'#ffaa00'}
    b = {'kind':'highlight','x':.1,'y':.3,'w':.2,'h':.1,'color':'#ffbb00'}
    existing = [b]
    assert restore_stroke(existing, 0, a) == [a, b]
    new = make_highlight((.4, .4, .1, .1), '#ffff00')
    assert add_mark([a, b], new) == [a, b, new]
    assert remove_stroke([a, b, new], new['id']) == [a, b]


def test_all_mark_types_survive_save_load_without_bumping_format(tmp_path):
    p = Project.create(tmp_path, 'Opacity & Highlights')
    p.pages = [{'id': 'p1', 'kind': 'blank', 'title': 'Page 1'}]
    marks = [
        {'kind':'highlight','x':.1,'y':.1,'w':.25,'h':.05,'color':'#ffbb33'},
        make_highlight((.25, .25, .3, .1), '#ffaa00', 0),
        make_highlight_line((.05, .5), (.9, .5), '#ff9900', .012, 55),
        make_shape('rectangle', (.2, .2), (.7, .7), '#112233', .006,
                   fill='#f0e0d0', opacity=23, fill_opacity=99),
        make_stroke([(.2,.8),(.4,.9)], '#336699', .003, opacity=70),
        make_stroke([(.5,.8),(.8,.9)], '#336699', .012,
                    blend='multiply', opacity=35),
    ]
    p.annotations['p1'] = copy.deepcopy(marks)
    p.save()
    loaded = Project.load(p.path)
    assert loaded.annotations['p1'] == marks
    saved = json.loads((p.path/'project.json').read_text())
    assert saved['version'] == FORMAT_VERSION == 4
    assert saved['annotations']['p1'] == marks


@pytest.mark.parametrize('invalid', [
    {'kind':'highlight_line', 'id':'abc', 'x1':.2,'y1':.2,
     'x2':.9,'y2':.9, 'width':.101, 'color':'#ffeebb', 'opacity':35},
    {'kind':'highlight', 'x':.8,'y':.3, 'w':.4,'h':.2, 'color':'#ffeebb'},
])
def test_corrupt_new_highlight_geometry_rejected_when_loading(tmp_path, invalid):
    p = Project.create(tmp_path, 'Corrupt Highlights')
    p.pages = [{'id':'p1','kind':'blank','title':'Page 1'}]
    p.save()
    path = p.path/'project.json'
    data = json.loads(path.read_text())
    data['annotations'] = {'p1': [invalid]}
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='Invalid highlight'):
        Project.load(p.path)
