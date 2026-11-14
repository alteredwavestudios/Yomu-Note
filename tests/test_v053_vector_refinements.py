"""v0.5.3: small vector geometry records, no Qt required."""
import math
from yomunote.vector_marks import (MAX_STROKE_WIDTH, make_shape,
                                    make_highlight_line, resized_vector,
                                    valid_shape, valid_vector)


def test_new_thickness_limit_and_out_of_range_rejection():
    assert MAX_STROKE_WIDTH == .10
    assert valid_vector(make_shape('rectangle', (.2,.2),(.7,.6),'#112233', .10))
    assert valid_vector(make_highlight_line((.1,.2),(.7,.2),'#ffcc44', .10))
    assert not valid_shape({**make_shape('rectangle',(.2,.2),(.8,.8),'#112233', .1), 'width': .101})


def test_arrowhead_dimensions_are_persistent_optional_properties():
    arrow = make_shape('arrow',(.1,.25),(.7,.25),'#be2288',.01,
                       head_width=.045, head_length=.08)
    assert valid_vector(arrow)
    assert arrow['head_width'] == .045
    assert arrow['head_length'] == .08
    for field in ('head_width', 'head_length'):
        assert not valid_vector({**arrow, field: float('nan')})
        assert not valid_vector({**arrow, field: .3})
    old = make_shape('arrow',(.1,.2),(.4,.3),'#123456', .004)
    assert valid_vector(old)
    assert 'head_width' not in old


def test_shift_corner_resize_preserves_rectangle_aspect_ratio_and_id():
    rect = make_shape('rectangle',(.2,.2),(.6,.4),'#ff4433', .006)
    resized = resized_vector(rect,'br',.7,.4, keep_aspect=True)
    assert resized['id'] == rect['id']
    width = abs(resized['x2'] - resized['x1'])
    height = abs(resized['y2'] - resized['y1'])
    assert math.isclose(width/height, 2.0, rel_tol=1e-8)
    assert width > .4
    # Inward drag in one axis should also shrink proportionally.
    shrink = resized_vector(rect,'br',.48,.4, keep_aspect=True)
    assert shrink['x2'] < rect['x2']
    assert math.isclose((shrink['x2']-shrink['x1']) /
                        (shrink['y2']-shrink['y1']), 2., rel_tol=1e-8)


def test_alt_resize_is_centred_and_combines_with_shift():
    ellipse = make_shape('ellipse',(.2,.2),(.6,.4),'#1166aa', .003)
    resized = resized_vector(ellipse,'br',.65,.47, from_center=True,
                             keep_aspect=True)
    original_center = (.4,.3)
    new_center = ((resized['x1']+resized['x2'])/2,
                  (resized['y1']+resized['y2'])/2)
    assert all(math.isclose(a,b,abs_tol=1e-8) for a,b in zip(original_center,new_center))
    assert math.isclose((resized['x2']-resized['x1']) /
                        (resized['y2']-resized['y1']), 2., rel_tol=1e-8)


def test_arrow_endpoint_shift_preserves_direction_and_alt_centre():
    arrow = make_shape('arrow',(.2,.2),(.5,.4),'#123456', .012)
    new = resized_vector(arrow, 'end', .8,.3,keep_aspect=True)
    dx, dy = new['x2']-new['x1'], new['y2']-new['y1']
    assert math.isclose(dy/dx, 2/3, rel_tol=1e-8)
    opposite = resized_vector(arrow,'end',.6,.5,from_center=True)
    assert math.isclose((opposite['x1']+opposite['x2'])/2, .35, abs_tol=1e-9)
    assert math.isclose((opposite['y1']+opposite['y2'])/2, .3, abs_tol=1e-9)
