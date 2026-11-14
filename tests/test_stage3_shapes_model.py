"""Stage 3 v0.5.1 shape/marker persistence and resizing (Qt-independent)."""
import json
import pytest

from yomunote.project import Project
from yomunote.vector_marks import (
    make_shape, valid_shape, make_stroke, valid_stroke, vector_bounds,
    resized_vector, translated_vector, add_mark, replace_stroke, restore_stroke,
    remove_stroke,
)

@pytest.mark.parametrize('kind', ['line', 'arrow', 'rectangle', 'ellipse'])
def test_shapes_have_stable_ids_and_normalized_geometry(kind):
    fill = '#abcdef' if kind in ('rectangle', 'ellipse') else None
    mark = make_shape(kind, (.2, .3), (.8, .7), '#456789', .004, fill)
    assert valid_shape(mark)
    assert vector_bounds(mark) == (.2, .3, .8, .7)
    moved = translated_vector(mark, .4, .4)
    assert moved['id'] == mark['id']
    assert moved['x2'] == pytest.approx(1.)
    assert moved['y2'] == pytest.approx(1.)
    assert mark['x2'] == .8  # no destructive mutation


def test_shapes_reject_invalid_metadata_and_nonfinite_values():
    mark = make_shape('arrow', (.1, .2), (.8, .6), '#112233', .003)
    for update in ({'shape': 'script'}, {'color': 'red'}, {'width': 0},
                   {'x1': -1}, {'y2': float('inf')}, {'fill': '#112233'},
                   {'id': ''}):
        assert not valid_shape({**mark, **update})


def test_endpoint_dragging_preserves_arrow_direction_and_undo_identity():
    arrow = make_shape('arrow', (.9, .9), (.1, .2), '#123456', .003)
    resize = resized_vector(arrow, 'end', .3, .4)
    assert resize['id'] == arrow['id']
    assert (resize['x1'], resize['y1']) == (.9, .9)
    assert (resize['x2'], resize['y2']) == (.3, .4)
    assert arrow['x2'] == .1


def test_rectangle_resizing_from_each_corner():
    rect = make_shape('rectangle', (.1, .1), (.5, .5), '#abc123', .005, '#abc123')
    resized = resized_vector(rect, 'br', .8, .9)
    assert vector_bounds(resized) == pytest.approx((.1, .1, .8, .9))
    resized = resized_vector(rect, 'tl', 0., 0.)
    assert vector_bounds(resized) == pytest.approx((0., 0., .5, .5))


def test_pen_strokes_are_resizable_even_when_line_is_flat():
    pen = make_stroke([(.1, .2), (.4, .2), (.6, .2)], '#557799', .003)
    reshaped = resized_vector(pen, 'br', .9, .7)
    assert reshaped['id'] == pen['id']
    assert all(0 <= x <= 1 and 0 <= y <= 1 for x, y in reshaped['points'])
    assert len(reshaped['points']) == len(pen['points'])
    assert pen['points'][0] == [.1, .2]


def test_marker_multiplies_but_old_pen_strokes_keep_existing_default():
    old = make_stroke([(.1,.1),(.3,.3)], '#99cc22', .003)
    marker = make_stroke([(.1,.1),(.3,.3)], '#99cc22', .009, blend='multiply')
    assert 'blend' not in old
    assert valid_stroke(old) and valid_stroke(marker)
    assert marker['blend'] == 'multiply'
    assert not valid_stroke({**marker, 'blend': 'screen'})


def test_add_remove_replace_restore_vectors_without_touching_highlight():
    highlight={'kind': 'highlight', 'x': .1, 'y': .1, 'w': .2, 'h': .1, 'color': '#eeddaa'}
    shape = make_shape('ellipse', (.2,.2),(.5,.5), '#998877', .003)
    marks=add_mark([highlight],shape)
    assert marks[0] is highlight
    changed=resized_vector(shape,'br',.8,.8)
    marks=replace_stroke(marks,changed)
    assert marks[1]==changed
    marks=remove_stroke(marks,shape['id'])
    assert marks==[highlight]
    marks=restore_stroke(marks,1,shape)
    assert marks==[highlight,shape]


def test_shapes_and_marker_survive_project_save_load(tmp_path):
    p=Project.create(tmp_path,'Stage 3 Shapes')
    p.pages=[{'id':'p1','kind':'blank','title':'Page 1'}]
    marks=[
        {'kind':'highlight','x':.1,'y':.1,'w':.3,'h':.15,'color':'#ffcc33'},
        make_stroke([(.1,.3),(.3,.4)], '#33cc99', .01, blend='multiply'),
        make_shape('rectangle',(.2,.2),(.6,.6),'#445566',.003,'#445566'),
        make_shape('arrow',(.8,.7),(.1,.2),'#445566',.003),
    ]
    p.annotations={'p1': marks}
    p.save()
    q=Project.load(p.path)
    assert q.annotations['p1']==marks
    path=p.path/'project.json'
    data=json.loads(path.read_text())
    data['annotations']['p1'][2]['shape']='invalid_shape'
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError,match='Invalid vector shape'):
        Project.load(p.path)
