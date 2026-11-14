"""Safety checks for v0.4.4c: emergency restoration of native editing."""
from pathlib import Path
import ast
ROOT = Path(__file__).resolve().parents[1] / 'yomunote'

def test_v045_native_text_history_is_preserved_while_unified_dispatch_is_added():
    w=(ROOT/'window.py').read_text()
    e=(ROOT/'editor.py').read_text()
    assert 'NativeTextCommand' not in w  # old broken v0.4.4b proxy
    assert 'history_dispatch' not in e
    assert 'undoCommandAdded.connect' in w
    assert 'self.undo_notes_action' in w
    assert 'self.history = UnifiedHistory(' in w
    assert 'self.annotation_history = QUndoStack(self)' not in w
    assert 'editor.history_key_handler' in w
    assert 'self.editor.setHtml(html)' in e
    assert 'cursor.endEditBlock()' in e

def test_no_fixed_height_used_for_new_typing():
    e=(ROOT/'editor.py').read_text()
    f=e.split('def set_font_size_immediately',1)[1].split('def count_fixed_height_paragraphs',1)[0]
    assert 'LineHeightTypes.FixedHeight' not in f
    assert 'LineHeightTypes.MinimumHeight.value' in f
    assert 'cursor.setBlockFormat(block_fmt)' in f
    assert 'cursor.endEditBlock()' in f
    assert 'finally:' in f
    assert 'cursor.insertText' not in f

def test_fixed_height_repair_is_opt_in_and_undoable():
    w=(ROOT/'window.py').read_text()
    e=(ROOT/'editor.py').read_text()
    assert "'Repair Notes Line Spacing…', self.repair_notes_line_spacing" in w
    assert 'QMessageBox.question(' in w.split('def repair_notes_line_spacing',1)[1].split('def _update_undo_actions',1)[0]
    assert 'group.beginEditBlock()' in e
    assert 'group.endEditBlock()' in e
    assert 'int(QTextBlockFormat.LineHeightTypes.SingleHeight.value)' in e
    assert 'QTextBlockFormat.LineHeightTypes.FixedHeight.value' in e

def test_tab_theme_and_order_are_preserved():
    w=(ROOT/'window.py').read_text()
    assert 'bar.setMovable(True)' in w
    assert 'bar.tabMoved.connect(self._on_tab_moved)' in w
    assert 'self.change_tab()\n        # Only newly attached panes' in w
    assert 'self._theme_one_pane(self.tabs.widget(i))' in w

def test_python_parses():
    for name in ('window.py','editor.py','notebook.py'):
        ast.parse((ROOT/name).read_text())
