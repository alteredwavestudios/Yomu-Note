"""Check the extended optional palettes without importing Qt.

A normal-sized paragraph must contrast against its page.
These tests use the standard WCAG relative-luminance method.
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TREE = ast.parse((ROOT / 'yomunote/window.py').read_text('utf-8'))


def new_palettes():
    for node in ast.walk(TREE):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == 'update'
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == 'THEMES'):
            return ast.literal_eval(node.args[0])
    raise AssertionError('Missing optional themes')


def luminance(hex_colour):
    parts = [int(hex_colour[i:i+2], 16)/255 for i in (1, 3, 5)]
    light = [c/12.92 if c <= 0.04045 else ((c+0.055)/1.055)**2.4
             for c in parts]
    return sum(x*y for x, y in zip((0.2126, 0.7152, 0.0722), light))


def contrast(first, second):
    a, b = sorted((luminance(first), luminance(second)), reverse=True)
    return (a+0.05)/(b+0.05)


def test_optional_palettes_and_accessible_text():
    data = new_palettes()
    assert len(data) == 16
    expected = {'name', 'window', 'panel', 'paper', 'shelf', 'canvas',
                'ink', 'muted', 'accent', 'accent2', 'border',
                'highlight', 'btn', 'btn2', 'preview'}
    for key, colours in data.items():
        assert set(colours) == expected, key
        for surface in ('paper', 'window', 'panel', 'btn'):
            assert contrast(colours[surface], colours['ink']) >= 4.5, (
                key, surface)


def test_light_and_dark_groups_exist():
    data = new_palettes()
    for key in ('asagao', 'ume', 'hinoki', 'sora', 'mizu',
                'yoru', 'sumi', 'beni', 'aoi', 'shibui'):
        assert key in data
