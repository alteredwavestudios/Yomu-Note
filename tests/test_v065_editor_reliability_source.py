"""Audit assertions that can run without PySide6 on this machine."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EDITOR = (ROOT / 'yomunote/editor.py').read_text()
WINDOW = (ROOT / 'yomunote/window.py').read_text()
TREE = ast.parse(EDITOR)


def method(name):
    klass = next(n for n in TREE.body if isinstance(n, ast.ClassDef)
                 and n.name == 'NotesEditor')
    fn = next(n for n in klass.body if isinstance(n, ast.FunctionDef)
              and n.name == name)
    return ast.get_source_segment(EDITOR, fn)


def test_heading_uses_every_exact_selected_block():
    code = method('change_heading')
    assert '_target_block_positions(original)' in code
    assert 'for position in positions:' in code
    assert 'setHeadingLevel(index)' in code
    assert 'group.beginEditBlock()' in code
    assert 'select(cursor.SelectionType.BlockUnderCursor)' not in code


def test_clear_formatting_removes_inherited_hard_coded_ink():
    code = method('clear_formatting')
    assert "QColor('#26374b')" not in code
    assert 'cursor.setCharFormat(fmt)' in code
    assert 'editor.setCurrentCharFormat(fmt)' in code


def test_explicit_zero_and_reset_handled_structurally():
    assert 'fmt.hasProperty(_AFTER_PT_OVERRIDE)' in method('_apply_paragraph_defaults')
    assert 'fmt.setProperty(_AFTER_PT_OVERRIDE' in method('_set_selected_spacing')
    assert 'fmt.clearProperty(prop)' in method('reset_selected_spacing')
    assert 'add_spacing_metadata' in method('html')
    assert 'split_spacing_metadata' in method('set_html')


def test_page_setup_native_and_saved_settings_share_history():
    assert '_pending_page_setup_history' in WINDOW
    assert "'Notes Page Setup'" in WINDOW
    assert 'restore_page_setup_metadata' in WINDOW
    assert 'ed.preserve_view_state(ed.undo)' in WINDOW


def test_shared_undo_is_used_by_notes_context_menu():
    assert 'def contextMenuEvent(self, event):' in EDITOR
    assert 'self.createStandardContextMenu()' in EDITOR
    assert 'handler(True)' in EDITOR
    assert 'handler(False)' in EDITOR
    assert "redo_keys.append('Ctrl+Y')" in WINDOW
