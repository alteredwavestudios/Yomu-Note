"""Pure geometry helpers for table editing guides.

This file does not import Qt. That makes its small calculations
safe to test even on a computer without a desktop interface.

The IMPORTANT distinction is that guides are not table borders.
They are temporary lines that help you see a borderless table.
Saving a notebook must never include these guides.
"""
from __future__ import annotations

import math


def proportional_column_edges(left, right, widths):
    """Turn saved percentage widths into true column boundaries.

    Text alignment moves the typing cursor INSIDE a cell.
    It does not move the actual cell boundary. We therefore
    never use a text cursor's X coordinate as a column edge.
    """
    if not widths or right <= left:
        return []
    try:
        weights = [float(width) for width in widths]
    except (TypeError, ValueError):
        return []
    if any(not math.isfinite(w) or w <= 0 for w in weights):
        return []
    total = sum(weights)
    edges = [float(left)]
    accumulated = 0.0
    for weight in weights[:-1]:
        accumulated += weight
        edges.append(left + (right - left) * accumulated / total)
    edges.append(float(right))
    return edges


def grid_segments(owners, xs, ys):
    """Return grid lines that do not cut across merged cells.

    ``owners[row][column]`` identifies the REAL cell occupying
    that grid square. Two positions with the same owner belong
    to one merged cell and must NOT have a line between them.

    Results are (x1, y1, x2, y2). Adjacent short segments are
    joined, so shared borders are painted only once.
    """
    rows = len(owners)
    if not rows:
        return []
    columns = len(owners[0])
    if (not columns or len(xs) != columns + 1
            or len(ys) != rows + 1
            or any(len(row) != columns for row in owners)):
        return []
    segments = []

    # Each horizontal edge separates two ROWS of real cells.
    for row in range(1, rows):
        start = None
        for col in range(columns):
            separated = owners[row - 1][col] != owners[row][col]
            if separated and start is None:
                start = col
            if start is not None and (not separated or col == columns - 1):
                end = col + 1 if separated else col
                if end > start:
                    segments.append((xs[start], ys[row], xs[end], ys[row]))
                start = None

    # Each vertical edge separates two COLUMNS of real cells.
    for col in range(1, columns):
        start = None
        for row in range(rows):
            separated = owners[row][col - 1] != owners[row][col]
            if separated and start is None:
                start = row
            if start is not None and (not separated or row == rows - 1):
                end = row + 1 if separated else row
                if end > start:
                    segments.append((xs[col], ys[start], xs[col], ys[end]))
                start = None
    return segments


def would_cut_merged_cell(owners, axis, index):
    """Reject deletion if it would cut through a merged cell.

    We allow a whole merged cell to be deleted with its row
    or column. We do NOT allow deleting just part of it,
    because that could shift or merge neighbouring data.
    """
    rows = len(owners)
    cols = len(owners[0]) if rows else 0
    if axis == 'row':
        if not 0 <= index < rows:
            return True
        target = set(owners[index])
        for r, row in enumerate(owners):
            if r != index and target.intersection(row):
                return True
        return False
    if axis == 'column':
        if not 0 <= index < cols:
            return True
        target = {row[index] for row in owners}
        for row in owners:
            for c, value in enumerate(row):
                if c != index and value in target:
                    return True
        return False
    raise ValueError('axis must be row or column')


def resize_adjacent_percentages(widths, boundary, shift_percent, min_percent=5.0):
    """Resize only the TWO columns touching a dragged divider.

    The sum of their widths stays unchanged, so columns to the
    left and right do not mysteriously move. This is a pure
    calculation: no live notes document changes during a drag.
    """
    try:
        values = [float(x) for x in widths]
        shift = float(shift_percent)
        minimum = float(min_percent)
    except (ValueError, TypeError):
        return None
    if (not 1 <= boundary < len(values) or
            any(not math.isfinite(x) or x <= 0 for x in values) or
            not math.isfinite(shift) or not math.isfinite(minimum)):
        return None
    left, right = values[boundary - 1], values[boundary]
    total = left + right
    # Never impose a minimum larger than the available pair.
    minimum = max(0.1, min(minimum, total / 2.0))
    new_left = max(minimum, min(total - minimum, left + shift))
    result = list(values)
    result[boundary - 1] = new_left
    result[boundary] = total - new_left
    return result


def closest_table_edge(value, edges, tolerance=5.0, *, include_final=False):
    """Find a draggable divider without counting an outer border.

    Column drags use internal edges only. Row drags may also
    use the bottom outside edge to resize the last row.
    """
    indexes = range(1, len(edges) if include_final else len(edges) - 1)
    choices = [(abs(value - edges[i]), i) for i in indexes]
    if not choices:
        return None
    distance, index = min(choices)
    return index if distance <= tolerance else None
