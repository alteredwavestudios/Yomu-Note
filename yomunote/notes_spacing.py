"""Save explicit paragraph spacing without depending on screen DPI.

BEGINNER NOTE
-------------
HTML is the format Yomu uses to save its rich-text notes.
Qt saves ordinary text and visible paragraph styles in HTML, but it
may drop custom format properties that only our application knows.

We add one small HTML comment with those properties. A comment is
invisible when someone reads or prints the document. The note text
and its normal HTML formatting are still saved exactly as before.

Values stored here use points: 72 points make one inch.
We do NOT store rendered pixel measurements, because the same
notebook may be opened on a different operating system or screen.
"""
from __future__ import annotations

import base64
import json
import math
import re

_PREFIX = 'YOMU_SPACING_V1:'
_MARKER = re.compile(r'<!--\s*YOMU_SPACING_V1:([A-Za-z0-9_-]+)\s*-->')
_NAMES = {'before_pt', 'after_pt', 'line'}
_MAX_BYTES = 1_000_000
_MAX_BLOCKS = 100_000


def _valid_override(name: str, value: object) -> bool:
    """Reject broken metadata before giving it to Qt's layout engine."""
    if not isinstance(value, (float, int)) or isinstance(value, bool):
        return False
    if not math.isfinite(value):
        return False
    if name == 'line':
        return 1.0 <= value <= 3.0
    return name in ('before_pt', 'after_pt') and 0 <= value <= 288


def add_spacing_metadata(html: str, overrides: dict) -> str:
    """Append point-based overrides to otherwise unchanged Qt HTML."""
    if not overrides:
        return html
    data = {}
    for index, values in overrides.items():
        if not isinstance(index, int) or index < 0 or index >= _MAX_BLOCKS:
            raise ValueError('Invalid paragraph index')
        if not isinstance(values, dict):
            raise ValueError('Invalid paragraph overrides')
        chosen = {}
        for name, value in values.items():
            if name not in _NAMES or not _valid_override(name, value):
                raise ValueError('Invalid paragraph spacing value')
            chosen[name] = round(float(value), 5)
        if chosen:
            data[str(index)] = chosen
    payload = json.dumps(data, separators=(',', ':'), sort_keys=True).encode('utf-8')
    if len(payload) > _MAX_BYTES:
        raise ValueError('Too many paragraph overrides')
    encoded = base64.urlsafe_b64encode(payload).decode('ascii').rstrip('=')
    return html + '\n<!-- ' + _PREFIX + encoded + ' -->'


def split_spacing_metadata(html: str) -> tuple[str, dict[int, dict]]:
    """Separate invisible metadata before giving HTML back to Qt.

    Damaged metadata should never prevent a user's actual note text
    from opening. In that case the text loads with its regular CSS.
    """
    matches = list(_MARKER.finditer(html))
    if not matches:
        return html, {}
    clean = _MARKER.sub('', html)
    payload = matches[-1].group(1)
    if len(payload) > (_MAX_BYTES * 4 // 3 + 8):
        return clean, {}
    try:
        decoded = base64.urlsafe_b64decode(
            payload + '=' * (-len(payload) % 4))
        if len(decoded) > _MAX_BYTES:
            return clean, {}
        raw = json.loads(decoded)
        if not isinstance(raw, dict) or len(raw) > _MAX_BLOCKS:
            return clean, {}
        result = {}
        for index, values in raw.items():
            if (not isinstance(index, str) or not index.isdecimal()
                    or int(index) >= _MAX_BLOCKS or not isinstance(values, dict)):
                return clean, {}
            if (not values or not set(values) <= _NAMES or
                    any(not _valid_override(k, v) for k, v in values.items())):
                return clean, {}
            result[int(index)] = values
        return clean, result
    except (ValueError, TypeError, OverflowError, UnicodeError, KeyError):
        return clean, {}
