"""Regression coverage for the v0.4.5c visually blank-line font hotfix."""
import ast
from pathlib import Path


SOURCE = Path(__file__).resolve().parents[1] / 'yomunote' / 'editor.py'


def _blank_classifier_without_qt():
    """Execute only the real pure-Python classifier, without importing Qt."""
    tree = ast.parse(SOURCE.read_text(encoding='utf-8'))
    nodes = [node for node in tree.body
             if ((isinstance(node, ast.Assign) and any(
                 isinstance(target, ast.Name) and target.id == '_INVISIBLE_LINE_MARKS'
                 for target in node.targets))
                 or (isinstance(node, ast.FunctionDef)
                     and node.name == '_is_visually_blank_paragraph'))]
    assert len(nodes) == 2
    env = {}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), 'exec'), env)
    return env['_is_visually_blank_paragraph']


def test_whitespace_and_zero_width_text_is_visually_blank():
    blank = _blank_classifier_without_qt()
    for text in ('', ' ', '    ', '\t', '\u00a0', '\u200b', '\u200e',
                 ' \u200b \t\u00a0', '\u2028\u2028', '\ufeff', '\u2060'):
        assert blank(text), repr(text)


def test_visible_glyphs_are_not_treated_as_blank():
    blank = _blank_classifier_without_qt()
    for text in ('a', 'text ', ' \u200bword', '•', '→', '5', '\u2028text'):
        assert not blank(text), repr(text)


def test_only_blank_line_path_changed_to_handle_formatted_runs():
    source = SOURCE.read_text(encoding='utf-8')
    assert source.count('if _is_visually_blank_paragraph(cursor.block().text()):') == 1
    assert 'run_cursor.mergeCharFormat(fmt)' in source
    assert 'LineHeightTypes.MinimumHeight.value' in source
    assert 'LineHeightTypes.FixedHeight.value))' not in source
