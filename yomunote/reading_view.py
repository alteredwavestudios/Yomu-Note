"""Persistent, bounded reading-view metadata for each Yomu Note project.

All coordinates are scene-relative fractions, not Qt scrollbar pixels. This
module contains no Qt imports, so it can be tested without a display.

Group zoom is inherited from the *outermost* (root) group. A page that is not
inside a root group uses its own zoom. A page may opt into an independent zoom,
while all pages always keep individual reading positions.
"""
from __future__ import annotations

import math

MAX_ITEMS = 20_000
MIN_ZOOM = 0.03
MAX_ZOOM = 15.0


def empty_view():
    return {
        'positions': {}, 'group_zooms': {}, 'page_zooms': {},
        'independent_pages': [], 'unshared_roots': [],
    }


def fit_zoom():
    return {'mode': 'fit'}


def zoom_value(mode, scale=None):
    """Return a valid zoom or Fit. Guard NaN/Infinity and absurd transforms."""
    if mode != 'manual':
        return fit_zoom()
    if type(scale) not in (float, int):
        return fit_zoom()
    try:
        scale = float(scale)
    except (OverflowError, ValueError):
        return fit_zoom()
    if not math.isfinite(scale) or not MIN_ZOOM <= scale <= MAX_ZOOM:
        return fit_zoom()
    return {'mode': 'manual', 'scale': round(scale, 6)}


def normalise_zoom(raw):
    if not isinstance(raw, dict):
        return fit_zoom()
    return zoom_value(raw.get('mode'), raw.get('scale'))


def normalise_position(raw):
    if not isinstance(raw, dict):
        return None
    x, y = raw.get('x'), raw.get('y')
    if type(x) not in (float, int) or type(y) not in (float, int):
        return None
    try:
        x, y = float(x), float(y)
    except (OverflowError, ValueError):
        return None
    if (not math.isfinite(x) or not math.isfinite(y)
            or not 0 <= x <= 1 or not 0 <= y <= 1):
        return None
    return {'x': round(x, 7), 'y': round(y, 7),
            'bottom': raw.get('bottom') is True}


def root_for_page(tree, page_id):
    """Return the outermost enclosing group ID; ungrouped pages return None."""
    def contains(nodes):
        for node in nodes:
            if node['type'] == 'page' and node['page_id'] == page_id:
                return True
            if node['type'] == 'group' and contains(node['children']):
                return True
        return False
    for node in tree or []:
        if node['type'] == 'group' and contains(node['children']):
            return node['id']
    return None


def root_for_group(tree, group_id):
    def contains_group(nodes):
        for node in nodes:
            if node['type'] == 'group':
                if node['id'] == group_id or contains_group(node['children']):
                    return True
        return False
    for node in tree or []:
        if node['type'] == 'group' and contains_group([node]):
            return node['id']
    return None


def pages_in_group(tree, group_id):
    def find(nodes):
        for node in nodes:
            if node['type'] != 'group':
                continue
            if node['id'] == group_id:
                return node
            result = find(node['children'])
            if result is not None:
                return result
        return None
    def collect(node):
        for item in node['children']:
            if item['type'] == 'page':
                yield item['page_id']
            else:
                yield from collect(item)
    group = find(tree or [])
    return list(collect(group)) if group else []


def root_ids(tree):
    return {node['id'] for node in tree or [] if node['type'] == 'group'}


def clean_reading_view(raw, pages, tree):
    """Never let malformed cosmetic view metadata block a saved notebook."""
    out = empty_view()
    if not isinstance(raw, dict):
        return out
    live = {p['id'] if isinstance(p, dict) else p for p in pages}
    roots = root_ids(tree)
    for field, allowed, converter in (
        ('positions', live, normalise_position),
        ('group_zooms', roots, normalise_zoom),
        ('page_zooms', live, normalise_zoom),
    ):
        source = raw.get(field)
        if not isinstance(source, dict) or len(source) > MAX_ITEMS:
            continue
        for key, value in source.items():
            if isinstance(key, str) and key in allowed:
                cleaned = converter(value)
                if cleaned is not None:
                    out[field][key] = cleaned
    for field, allowed in (('independent_pages', live),
                           ('unshared_roots', roots)):
        source = raw.get(field)
        if not isinstance(source, list) or len(source) > MAX_ITEMS:
            continue
        out[field] = sorted({item for item in source
                             if isinstance(item, str) and item in allowed})
    return out


def effective_zoom(view, tree, page_id, shared=True):
    """Resolve a page's effective zoom without changing its saved metadata."""
    root = root_for_page(tree, page_id)
    independent = page_id in view.get('independent_pages', ())
    unshared = root in view.get('unshared_roots', ())
    if root and shared and not independent and not unshared:
        return normalise_zoom(view.get('group_zooms', {}).get(root))
    page_zoom = view.get('page_zooms', {}).get(page_id)
    if page_zoom is not None:
        return normalise_zoom(page_zoom)
    if root:
        return normalise_zoom(view.get('group_zooms', {}).get(root))
    return fit_zoom()


def remember_zoom(view, tree, page_id, value, shared=True):
    """User zoom updates the root group unless this page opts out."""
    root = root_for_page(tree, page_id)
    value = normalise_zoom(value)
    if root and shared and page_id not in view['independent_pages'] \
            and root not in view['unshared_roots']:
        view['group_zooms'][root] = value
    else:
        view['page_zooms'][page_id] = value


def set_root_shared(view, tree, root, shared):
    if root not in root_ids(tree):
        return
    unshared = set(view['unshared_roots'])
    if shared:
        unshared.discard(root)
        for page_id in pages_in_group(tree, root):
            if page_id not in view['independent_pages']:
                view['page_zooms'].pop(page_id, None)
    else:
        # Give every page its own starting value so turning sharing off
        # doesn't unexpectedly change the page currently being read.
        for page_id in pages_in_group(tree, root):
            if page_id not in view['page_zooms']:
                view['page_zooms'][page_id] = effective_zoom(view, tree, page_id)
        unshared.add(root)
    view['unshared_roots'] = sorted(unshared)


def set_page_independent(view, tree, page_id, independent, shared=True):
    items = set(view['independent_pages'])
    if independent:
        if page_id not in view['page_zooms']:
            view['page_zooms'][page_id] = effective_zoom(view, tree, page_id, shared)
        items.add(page_id)
    else:
        items.discard(page_id)
        view['page_zooms'].pop(page_id, None)
    view['independent_pages'] = sorted(items)
