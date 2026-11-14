"""Small, Qt-independent vector annotation primitives for Stage 3.

All path coordinates are fractions of their source page, not pixmap pixels.
The original document is never painted over. A stroke remains editable after
saving, zooming or regenerating a PDF preview cache.
"""
from __future__ import annotations

import math
import re
from uuid import uuid4

MAX_STROKE_POINTS = 4096
MAX_STROKE_WIDTH = 0.10
MIN_STROKE_WIDTH = 0.0005
_COLOUR = re.compile(r'#[0-9a-fA-F]{6}\Z')
SHAPES = frozenset(('line', 'arrow', 'rectangle', 'ellipse'))
VECTOR_KINDS = frozenset(('stroke', 'shape', 'highlight', 'highlight_line'))


def _unit(value):
    return type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1


def valid_opacity(value) -> bool:
    """Percent alpha rather than a Qt-dependent byte; reject NaN and bool."""
    return type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 100


def _valid_optional_appearance(mark, *, shape=False):
    return (('opacity' not in mark or valid_opacity(mark['opacity']))
            and ('stroke_enabled' not in mark or
                 (shape and type(mark['stroke_enabled']) is bool))
            and ('fill_opacity' not in mark or
                 (shape and valid_opacity(mark['fill_opacity']))))


def valid_stroke(mark: object) -> bool:
    """Validate a stored freehand pen stroke before Qt attempts to draw it."""
    if not isinstance(mark, dict) or mark.get('kind') != 'stroke':
        return False
    points = mark.get('points')
    return (isinstance(mark.get('id'), str) and 1 <= len(mark['id']) <= 96
            and isinstance(mark.get('color'), str) and bool(_COLOUR.fullmatch(mark['color']))
            and type(mark.get('width')) in (float, int)
            and math.isfinite(mark['width'])
            and MIN_STROKE_WIDTH <= mark['width'] <= MAX_STROKE_WIDTH
            and mark.get('blend', 'normal') in ('normal', 'multiply')
            and _valid_optional_appearance(mark)
            and isinstance(points, list) and 2 <= len(points) <= MAX_STROKE_POINTS
            and all(isinstance(p, list) and len(p) == 2
                    and _unit(p[0]) and _unit(p[1]) for p in points))


def make_stroke(points, color: str, width: float, blend: str = 'normal',
                opacity: int | float | None = None) -> dict:
    """Create one mark from a user gesture, saving its stable identity."""
    mark = {'kind': 'stroke', 'id': uuid4().hex, 'color': color,
            'width': float(width), 'points': [[float(x), float(y)] for x, y in points]}
    if blend != 'normal':
        mark['blend'] = blend
    if opacity is not None:
        mark['opacity'] = opacity
    if not valid_stroke(mark):
        raise ValueError('Invalid vector stroke')
    return mark


def translated_stroke(mark: dict, dx: float, dy: float) -> dict:
    """Move without stretching: clamp the complete path inside the page."""
    if not valid_stroke(mark):
        raise ValueError('Invalid vector stroke')
    xs = [p[0] for p in mark['points']]
    ys = [p[1] for p in mark['points']]
    dx = min(1.0 - max(xs), max(-min(xs), float(dx)))
    dy = min(1.0 - max(ys), max(-min(ys), float(dy)))
    return {**mark, 'points': [[min(1., max(0., x + dx)), min(1., max(0., y + dy))]
                                for x, y in mark['points']]}



def valid_shape(mark: object) -> bool:
    """Shapes are small vector records in the same page-relative space as pens."""
    if not isinstance(mark, dict) or mark.get('kind') != 'shape':
        return False
    return (isinstance(mark.get('id'), str) and 1 <= len(mark['id']) <= 96
            and isinstance(mark.get('shape'), str) and mark['shape'] in SHAPES
            and isinstance(mark.get('color'), str)
            and bool(_COLOUR.fullmatch(mark['color']))
            and type(mark.get('width')) in (float, int)
            and math.isfinite(mark['width'])
            and MIN_STROKE_WIDTH <= mark['width'] <= MAX_STROKE_WIDTH
            and _valid_optional_appearance(mark, shape=True)
            and (mark['shape'] != 'arrow' or all(
                key not in mark or (type(mark[key]) in (int, float)
                    and math.isfinite(mark[key]) and .002 <= mark[key] <= .25)
                for key in ('head_width', 'head_length')))
            and all(_unit(mark.get(key)) for key in ('x1', 'y1', 'x2', 'y2'))
            and (mark.get('fill') is None or
                 (isinstance(mark.get('fill'), str) and
                  bool(_COLOUR.fullmatch(mark['fill']))))
            and (mark.get('shape') not in ('line', 'arrow') or mark.get('fill') is None))


def make_shape(shape: str, first, last, color: str, width: float,
               fill: str | None = None, *, opacity=None, fill_opacity=None,
               stroke_enabled=True, head_width=None, head_length=None) -> dict:
    """Make a page-relative line/arrow/rectangle/ellipse (never rasterize)."""
    if shape in ('line', 'arrow'):
        fill = None
    x1, y1 = first
    x2, y2 = last
    result = {'kind': 'shape', 'id': uuid4().hex, 'shape': shape,
              'x1': float(x1), 'y1': float(y1), 'x2': float(x2),
              'y2': float(y2), 'color': color, 'width': float(width),
              'fill': fill}
    if shape == 'arrow':
        if head_width is not None:
            result['head_width'] = float(head_width)
        if head_length is not None:
            result['head_length'] = float(head_length)
    if opacity is not None:
        result['opacity'] = opacity
    if fill_opacity is not None:
        result['fill_opacity'] = fill_opacity
    if not stroke_enabled:
        result['stroke_enabled'] = False
    if not valid_shape(result):
        raise ValueError('Invalid vector shape')
    return result


def valid_highlight(mark: object) -> bool:
    """Old rectangle highlights have no ID or opacity; keep them readable."""
    if not isinstance(mark, dict) or mark.get('kind') not in ('highlight', 'highlight_line'):
        return False
    if (not isinstance(mark.get('color'), str)
            or not _COLOUR.fullmatch(mark['color'])
            or ('id' in mark and (not isinstance(mark['id'], str)
                                  or not 1 <= len(mark['id']) <= 96))
            or not _valid_optional_appearance(mark)):
        return False
    if mark['kind'] == 'highlight':
        return (all(_unit(mark.get(key)) for key in ('x', 'y', 'w', 'h'))
                and mark['x'] + mark['w'] <= 1.000001
                and mark['y'] + mark['h'] <= 1.000001)
    return (isinstance(mark.get('id'), str)
            and all(_unit(mark.get(key)) for key in ('x1', 'y1', 'x2', 'y2'))
            and type(mark.get('width')) in (float, int)
            and math.isfinite(mark['width'])
            and MIN_STROKE_WIDTH <= mark['width'] <= MAX_STROKE_WIDTH)


def make_highlight(rect, color, opacity=35):
    x, y, w, h = rect
    result = {'kind': 'highlight', 'id': uuid4().hex,
              'x': float(x), 'y': float(y), 'w': float(w), 'h': float(h),
              'color': color, 'opacity': opacity}
    if not valid_highlight(result):
        raise ValueError('Invalid rectangle highlight')
    return result


def make_highlight_line(first, last, color, width, opacity=35):
    result = {'kind': 'highlight_line', 'id': uuid4().hex,
              'x1': float(first[0]), 'y1': float(first[1]),
              'x2': float(last[0]), 'y2': float(last[1]),
              'width': float(width), 'color': color, 'opacity': opacity}
    if not valid_highlight(result):
        raise ValueError('Invalid line highlight')
    return result


def valid_vector(mark: object) -> bool:
    """Dispatch to the correct validator for each supported annotation type."""
    return valid_stroke(mark) or valid_shape(mark) or valid_highlight(mark)


def vector_bounds(mark: dict) -> tuple[float, float, float, float]:
    """Return the geometry bounds excluding pen thickness, all in 0..1."""
    if not valid_vector(mark):
        raise ValueError('Invalid vector annotation')
    if mark['kind'] == 'highlight':
        return mark['x'], mark['y'], mark['x'] + mark['w'], mark['y'] + mark['h']
    if mark['kind'] in ('shape', 'highlight_line'):
        return (min(mark['x1'], mark['x2']), min(mark['y1'], mark['y2']),
                max(mark['x1'], mark['x2']), max(mark['y1'], mark['y2']))
    xs = [point[0] for point in mark['points']]
    ys = [point[1] for point in mark['points']]
    return min(xs), min(ys), max(xs), max(ys)


def translated_vector(mark: dict, dx: float, dy: float) -> dict:
    if mark.get('kind') == 'stroke':
        return translated_stroke(mark, dx, dy)
    if not valid_vector(mark):
        raise ValueError('Invalid vector annotation')
    left, top, right, bottom = vector_bounds(mark)
    dx = min(1.0 - right, max(-left, float(dx)))
    dy = min(1.0 - bottom, max(-top, float(dy)))
    if mark['kind'] == 'highlight':
        return {**mark, 'x': min(1., max(0., mark['x'] + dx)),
                'y': min(1., max(0., mark['y'] + dy))}
    moved = {**mark, 'x1': min(1., max(0., mark['x1'] + dx)),
             'y1': min(1., max(0., mark['y1'] + dy)),
             'x2': min(1., max(0., mark['x2'] + dx)),
             'y2': min(1., max(0., mark['y2'] + dy))}
    return moved


def resized_vector(mark: dict, handle: str, x: float, y: float, *,
                   keep_aspect: bool = False, from_center: bool = False) -> dict:
    """Resize a saved vector, retaining the ID and every original pen point.

    Lines/arrows expose their two endpoints. Strokes, rectangles and ellipses
    expose four bounding-box corners. Zero-span dimensions are well-defined
    so horizontal/vertical pen marks don't divide by zero.
    """
    if not valid_vector(mark) or not _unit(x) or not _unit(y):
        raise ValueError('Invalid vector resize')
    if (mark['kind'] == 'highlight_line' or
            (mark['kind'] == 'shape' and mark['shape'] in ('line', 'arrow'))):
        if handle not in ('start', 'end'):
            raise ValueError('Invalid line endpoint')
        keys = ('x1', 'y1') if handle == 'start' else ('x2', 'y2')
        other = ('x2', 'y2') if handle == 'start' else ('x1', 'y1')
        proposed_x, proposed_y = float(x), float(y)
        if keep_aspect and mark.get('shape') == 'arrow':
            # Keep the arrow's own direction while changing its length.
            vx = mark[keys[0]] - mark[other[0]]
            vy = mark[keys[1]] - mark[other[1]]
            denom = vx*vx + vy*vy
            if denom > 1e-12:
                factor = max(.01, ((x - mark[other[0]])*vx +
                                      (y - mark[other[1]])*vy)/denom)
                proposed_x = mark[other[0]] + factor*vx
                proposed_y = mark[other[1]] + factor*vy
        if from_center:
            mid_x = (mark['x1'] + mark['x2'])/2
            mid_y = (mark['y1'] + mark['y2'])/2
            ox, oy = 2*mid_x - proposed_x, 2*mid_y - proposed_y
            if not all(0 <= v <= 1 for v in (ox, oy, proposed_x, proposed_y)):
                return mark
            return {**mark, keys[0]: proposed_x, keys[1]: proposed_y,
                    other[0]: ox, other[1]: oy}
        if not 0 <= proposed_x <= 1 or not 0 <= proposed_y <= 1:
            return mark
        return {**mark, keys[0]: proposed_x, keys[1]: proposed_y}
    if handle not in ('tl', 'tr', 'bl', 'br'):
        raise ValueError('Invalid resize corner')
    left, top, right, bottom = vector_bounds(mark)
    if keep_aspect and mark['kind'] == 'shape' and mark.get('shape') in ('rectangle', 'ellipse'):
        orig_w, orig_h = max(1e-6, right-left), max(1e-6, bottom-top)
        if from_center:
            cx, cy = (left+right)/2, (top+bottom)/2
            ratio_x, ratio_y = abs((x-cx)/(orig_w/2)), abs((y-cy)/(orig_h/2))
            factor = max(.01, ratio_x if abs(ratio_x-1) >= abs(ratio_y-1) else ratio_y)
            factor = min(factor, cx/(orig_w/2), (1-cx)/(orig_w/2),
                         cy/(orig_h/2), (1-cy)/(orig_h/2))
            new_w, new_h = orig_w*factor, orig_h*factor
            left, right = cx-new_w/2, cx+new_w/2
            top, bottom = cy-new_h/2, cy+new_h/2
        else:
            anchor_x = right if 'l' in handle else left
            anchor_y = bottom if 't' in handle else top
            ratio_x, ratio_y = abs((x-anchor_x)/orig_w), abs((y-anchor_y)/orig_h)
            factor = max(.01, ratio_x if abs(ratio_x-1) >= abs(ratio_y-1) else ratio_y)
            max_x = anchor_x / orig_w if 'l' in handle else (1-anchor_x)/orig_w
            max_y = anchor_y / orig_h if 't' in handle else (1-anchor_y)/orig_h
            factor = min(factor, max_x, max_y)
            new_w, new_h = orig_w*factor, orig_h*factor
            left, right = ((anchor_x-new_w, anchor_x) if 'l' in handle
                           else (anchor_x, anchor_x+new_w))
            top, bottom = ((anchor_y-new_h, anchor_y) if 't' in handle
                           else (anchor_y, anchor_y+new_h))
        x = left if 'l' in handle else right
        y = top if 't' in handle else bottom
        # The rest of resizing should remap the original geometry only once.
    elif from_center and mark['kind'] in ('shape', 'stroke', 'highlight'):
        cx, cy = (left+right)/2, (top+bottom)/2
        wanted_half_w, wanted_half_h = abs(x-cx), abs(y-cy)
        wanted_half_w = min(wanted_half_w, cx, 1-cx)
        wanted_half_h = min(wanted_half_h, cy, 1-cy)
        left, right = cx-wanted_half_w, cx+wanted_half_w
        top, bottom = cy-wanted_half_h, cy+wanted_half_h
        x = left if 'l' in handle else right
        y = top if 't' in handle else bottom
    if 'l' in handle:
        left = min(float(x), right - 0.0001)
    else:
        right = max(float(x), left + 0.0001)
    if 't' in handle:
        top = min(float(y), bottom - 0.0001)
    else:
        bottom = max(float(y), top + 0.0001)
    left, top = max(0., left), max(0., top)
    right, bottom = min(1., right), min(1., bottom)
    before_left, before_top, before_right, before_bottom = vector_bounds(mark)

    def remap(px, py):
        u = ((px - before_left) / (before_right - before_left)
             if before_right > before_left else .5)
        v = ((py - before_top) / (before_bottom - before_top)
             if before_bottom > before_top else .5)
        return [min(1., max(0., left + u * (right - left))),
                min(1., max(0., top + v * (bottom - top)))]

    if mark['kind'] == 'highlight':
        resized = {**mark, 'x': left, 'y': top, 'w': right-left, 'h': bottom-top}
    elif mark['kind'] == 'stroke':
        resized = {**mark, 'points': [remap(*point) for point in mark['points']]}
    else:
        a = remap(mark['x1'], mark['y1'])
        b = remap(mark['x2'], mark['y2'])
        resized = {**mark, 'x1': a[0], 'y1': a[1], 'x2': b[0], 'y2': b[1]}
    if not valid_vector(resized):
        raise ValueError('Invalid resized annotation')
    return resized


def add_mark(marks: list[dict], mark: dict) -> list[dict]:
    """Append one uniquely identified vector without copying existing marks."""
    if not valid_vector(mark):
        raise ValueError('Invalid vector annotation')
    if any(m.get('kind') in VECTOR_KINDS and m.get('id') == mark['id'] for m in marks):
        return list(marks)
    return [*marks, mark]


def remove_stroke(marks: list[dict], stroke_id: str) -> list[dict]:
    return [m for m in marks
            if not (m.get('kind') in VECTOR_KINDS and m.get('id') == stroke_id)]


def restore_stroke(marks: list[dict], index: int, mark: dict) -> list[dict]:
    if not valid_vector(mark):
        raise ValueError('Invalid vector annotation')
    existing = (remove_stroke(marks, mark['id']) if mark.get('id') else list(marks))
    pos = max(0, min(int(index), len(existing)))
    return [*existing[:pos], mark, *existing[pos:]]


def replace_stroke(marks: list[dict], mark: dict) -> list[dict]:
    if not valid_vector(mark):
        raise ValueError('Invalid vector annotation')
    return [mark if m.get('kind') in VECTOR_KINDS and m.get('id') == mark['id'] else m
            for m in marks]
