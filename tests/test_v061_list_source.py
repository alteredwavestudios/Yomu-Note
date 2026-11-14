"""List/indent invariants that run even without a GUI/Qt installation."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / 'yomunote/editor.py').read_text(encoding='utf8')
WINDOW = (ROOT / 'yomunote/window.py').read_text(encoding='utf8')
TREE = ast.parse(SOURCE)


def method(name):
    editor = next(node for node in TREE.body if isinstance(node, ast.ClassDef) and node.name == 'NotesEditor')
    function = next(node for node in editor.body if isinstance(node, ast.FunctionDef) and node.name == name)
    return ast.get_source_segment(SOURCE, function)


def test_indent_never_changes_shared_list_format():
    code = '\n\n'.join([method('indent'), method('_change_list_item_level'), method('_put_block_in_list')])
    assert not any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                   and n.func.attr == 'setFormat' for n in ast.walk(ast.parse(code)))
    # A first nested item can move deeper if a real parent list item precedes it.
    assert 'self._has_previous_list_parent(block)' in code
    assert 'actual_list.remove(block)' in code
    assert 'peer.add(block)' in code
    assert 'point.createList(fmt)' in code
    assert 'fmt.setIndent(target_indent)' in code
    assert 'beginEditBlock()' in method('indent')


def test_explicit_block_ownership_and_selection_end_are_not_inferred_from_lines():
    target = method('_target_block_positions')
    assert 'cursor.selectionEnd() - 1' in target
    assert 'findBlock(' in target and 'block.next()' in target
    assert 'blockNumber()' not in method('indent')
    assert 'textList()' in method('indent')
    assert 'textList()' in method('_peer_list')
    assert 'textList()' in method('make_list')
    assert '_is_visually_blank_paragraph(block.text())' in method('indent')
    assert '_is_visually_blank_paragraph(block.text())' in method('make_list')


def test_native_list_renderer_and_ordered_blank_continuity():
    assert 'QTextListFormat.Style.ListDecimal' in method('make_list')
    assert 'QTextListFormat.Style.ListDisc' in method('make_list')
    assert 'ordered and _is_visually_blank_paragraph(neighbour.text())' in method('_peer_list')
    # Never build a fake marker span or text-prefix numbering scheme.
    assert 'insertText(' not in method('make_list')
    assert 'insertHtml(' not in method('make_list')
    assert 'insertText(' not in method('indent')


def test_ctrl_brackets_are_editor_local_with_mac_command_mapping():
    handler = method('handle_docs_keystroke')
    assert 'Qt.Key.Key_BracketRight' in handler
    assert 'Qt.Key.Key_BracketLeft' in handler
    assert 'self.indent(+1)' in handler and 'self.indent(-1)' in handler
    assert "'Ctrl+]': self.indent" not in SOURCE  # handled directly by the focused editor
    assert 'IS_MAC' in SOURCE


def test_ocr_plaintext_editor_receives_palette_styles():
    assert "QTextEdit, QPlainTextEdit {{ background: {c['paper']}; color: {c['ink']}" in WINDOW
    assert 'QPlainTextEdit#ocrReviewText' in WINDOW
    assert "editor.setObjectName('ocrReviewText')" in WINDOW
    assert "selection-color: {c['ink']}" in WINDOW
