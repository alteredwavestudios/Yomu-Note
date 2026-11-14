"""Pure/static checks that do not need a Qt GUI runtime."""
import ast
import copy
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / 'yomunote/window.py').read_text(encoding='utf8')
UI = (ROOT / 'yomunote/ui.py').read_text(encoding='utf8')
TREE = ast.parse(SOURCE)


def method(cls, name):
    node = next(t for t in TREE.body if isinstance(t, ast.ClassDef) and t.name == cls)
    node = next(t for t in node.body if isinstance(t, ast.FunctionDef) and t.name == name)
    return ast.get_source_segment(SOURCE, node)


def test_opaque_backdrop_uses_separate_shadow():
    init = method('AnnotationQuickEditBackdrop', '__init__')
    theme = method('AnnotationQuickEditBackdrop', 'set_theme')
    assert 'self._surface.setAlpha(255)' in init
    assert 'surface.setAlpha(255)' in theme
    assert 'WA_TransparentForMouseEvents' in init
    assert 'QGraphicsDropShadowEffect' not in method('ProjectPane', '_create_annotation_quick_edit')


def test_wide_resizable_panel_and_breakpoints():
    creation = method('ProjectPane', '_create_annotation_quick_edit')
    assert '_quick_edit_user_width = 490' in creation
    assert 'quick_resize_handle.installEventFilter(self)' in creation
    assert '_quick_columns = QBoxLayout' in SOURCE
    reposition = method('ProjectPane', '_position_annotation_quick_edit')
    assert 'desired_width >= 420' in reposition
    assert 'self._quick_columns.setDirection(direction)' in reposition
    assert 'viewport.width() - 12' in reposition
    eventfilter = method('ProjectPane', 'eventFilter')
    assert '_quick_edit_resize_start' in eventfilter
    assert '_quick_edit_user_width' in eventfilter


def test_toolbar_breakpoints_and_saturated_icons():
    layout = method('ProjectPane', '_update_annotation_toolbar_layout')
    assert "mode = 'labels'" in layout and "mode = 'icons'" in layout
    assert "mode = 'small'" in layout
    assert '_annotation_overflow' in layout
    assert 'setToolButtonStyle' in layout
    theme = method('ProjectPane', '_theme_annotation_toolbar')
    assert "colours['accent']" in theme and "colours['accent2']" in theme
    assert 'min(ratio(tint, bg), ratio(tint, active_bg)) >= 3.1' in theme
    for icon in ('mouse-pointer-2', 'hand', 'shapes', 'eraser', 'link-2'):
        assert f"'{icon}':" in UI


def test_eraser_uses_single_gesture_and_proper_cleanup():
    canvas = method('ImageCanvas', '_erase_along_segment')
    assert 'self._stroke_hit(sample)' in canvas
    assert 'item.setVisible(False)' in canvas
    assert 'self._eraser_hidden' in canvas
    finished = method('ImageCanvas', '_finish_eraser_drag')
    assert 'self.strokesEraseGestureRequested.emit(indexes)' in finished
    assert 'self._cancel_eraser_drag()' in finished
    assert '_cancel_eraser_drag()' in method('ImageCanvas', 'clear_marks')
    assert '_cancel_eraser_drag()' in method('ImageCanvas', 'set_annotation_tool')


def test_batch_erase_undo_redo_restores_legacy_and_id_marks():
    # Compile ONLY the pure PySide-free ProjectPane.erase_strokes method into
    # a miniature fake, checking actual callback behaviour, not only strings.
    target = next(t for t in TREE.body if isinstance(t, ast.ClassDef) and t.name == 'ProjectPane')
    fn = next(t for t in target.body if isinstance(t, ast.FunctionDef) and t.name == 'erase_strokes')
    exec_module = ast.Module(body=[fn], type_ignores=[])
    ast.fix_missing_locations(exec_module)
    class Action:
        def __init__(self, label, undo, redo, size):
            self.label, self.undo, self.redo, self.size = label, undo, redo, size
    ns = {'copy': copy, 'CallbackAction': Action}
    exec(compile(exec_module, '<erase-test>', 'exec'), ns)
    class FakeHistory:
        def __init__(self): self.actions=[]
        def perform(self, action):
            self.actions.append(action)
            action.redo()
    class FakePane:
        def __init__(self, marks):
            self.project = SimpleNamespace(annotations={'p': list(marks)})
            self.history = FakeHistory()
        def current_page(self): return {'id':'p'}
        def _separate_text_commands(self): return None
        def _edit_stroke_marks(self, page_id, change):
            self.project.annotations[page_id] = change(self.project.annotations[page_id])
    originals = [
        {'kind':'highlight','rect':[.1,.1,.1,.1]},  # old anonymous annotation
        {'id':'second','kind':'shape','points':[]},
        {'id':'third','kind':'stroke','points':[[.1,.1],[.2,.2]]},
        {'id':'fourth','kind':'shape','points':[]},
    ]
    pane = FakePane(originals)
    ns['erase_strokes'](pane, [0,2,2,500])
    assert [m.get('id') for m in pane.project.annotations['p']] == ['second','fourth']
    assert len(pane.history.actions) == 1
    action = pane.history.actions[0]
    assert action.label == 'Erase Annotations'
    action.undo()
    assert pane.project.annotations['p'] == originals
    action.redo()
    assert [m.get('id') for m in pane.project.annotations['p']] == ['second','fourth']
