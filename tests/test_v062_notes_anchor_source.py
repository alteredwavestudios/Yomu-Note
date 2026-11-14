"""v0.6.2 source-level checks for note-view anchoring and list presentation."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EDITOR_SOURCE = (ROOT / 'yomunote/editor.py').read_text(encoding='utf8')
WINDOW_SOURCE = (ROOT / 'yomunote/window.py').read_text(encoding='utf8')
EDITOR_TREE = ast.parse(EDITOR_SOURCE)
WINDOW_TREE = ast.parse(WINDOW_SOURCE)


def class_method(tree, source, cls_name, method_name):
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == cls_name)
    fn = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == method_name)
    return ast.get_source_segment(source, fn)


def test_link_text_edit_preserves_scroll_on_resize():
    resize = class_method(EDITOR_TREE, EDITOR_SOURCE, 'LinkTextEdit', 'resizeEvent')
    capture = class_method(EDITOR_TREE, EDITOR_SOURCE, 'LinkTextEdit', 'capture_view_state')
    restore = class_method(EDITOR_TREE, EDITOR_SOURCE, 'LinkTextEdit', 'restore_view_state')
    assert 'self._resize_anchor = self.capture_view_state()' in resize
    assert 'self._resize_restore_timer.start()' in resize
    assert 'cursorForPosition' in capture
    assert 'verticalScrollBar()' in capture
    assert 'self.setTextCursor' in restore
    assert 'bar.setValue' in restore


def test_notes_indent_and_make_list_are_view_anchored():
    indent = class_method(EDITOR_TREE, EDITOR_SOURCE, 'NotesEditor', 'indent')
    make_list = class_method(EDITOR_TREE, EDITOR_SOURCE, 'NotesEditor', 'make_list')
    normalize = class_method(EDITOR_TREE, EDITOR_SOURCE, 'NotesEditor', '_normalise_list_block_presentation')
    assert 'self._preserve_editor_view(apply_indent)' in indent
    assert 'positions = list(self._target_block_positions(selection))' in indent
    assert 'self._preserve_editor_view(apply_list)' in make_list
    assert 'self._normalise_list_block_presentation(block)' in make_list
    assert 'point.setBlockCharFormat' in normalize
    assert 'char_fmt.setFontPointSize(base)' in normalize


def test_native_text_undo_uses_editor_view_anchor():
    assert 'ed.preserve_view_state(ed.undo)' in WINDOW_SOURCE
    assert 'ed.preserve_view_state(ed.redo)' in WINDOW_SOURCE
