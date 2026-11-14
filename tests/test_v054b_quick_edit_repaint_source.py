"""Fast guards for the v0.5.4b hover-paint regression, without Qt imports."""
from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / 'yomunote/window.py').read_text(encoding='utf-8')
MODULE = ast.parse(SOURCE)


def body(cls, name):
    for node in MODULE.body:
        if isinstance(node, ast.ClassDef) and node.name == cls:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == name:
                    return ast.get_source_segment(SOURCE, item)
    raise AssertionError(f'Missing {cls}.{name}')


def test_shadow_and_transparency_are_not_effects_on_interactive_children():
    source = body('ProjectPane', '_create_annotation_quick_edit')
    assert 'AnnotationQuickEditBackdrop(self.canvas.viewport())' in source
    assert 'QGraphicsDropShadowEffect' not in source
    assert 'setGraphicsEffect(' not in source
    assert 'setWindowOpacity(' not in source
    assert 'panel.installEventFilter(self)' in source
    theme = body('ProjectPane', '_theme_annotation_quick_edit')
    assert 'background: transparent' in theme
    assert 'self._quick_edit_backdrop.set_theme(colours)' in theme
    background = body('AnnotationQuickEditBackdrop', 'paintEvent')
    assert 'QPainter(self)' in background
    assert 'painter.setBrush(self._surface)' in background
    assert 'QGraphics' not in background


def test_backdrop_tracks_and_never_blocks_interactive_widgets():
    init = body('AnnotationQuickEditBackdrop', '__init__')
    assert 'WA_TransparentForMouseEvents' in init
    assert 'WA_TranslucentBackground' in init
    assert 'setAutoFillBackground(False)' in init
    source = body('ProjectPane', 'eventFilter')
    assert '_sync_annotation_quick_edit_backdrop(' in source
    assert 'QEvent.Type.Move' in source and 'QEvent.Type.Hide' in source
    sync = body('ProjectPane', '_sync_annotation_quick_edit_backdrop')
    assert 'backing.stackUnder(panel)' in sync
    assert 'backing.hide()' in sync


def test_all_new_multiply_highlighting_tools_start_fully_opaque():
    # The UI passes the explicit opacity into new marks; legacy saved marks
    # remain unchanged, as do the default-less stroke/highlight model readers.
    source = body('ImageCanvas', '__init__')
    assert "self.tool_styles['marker'] = {'color': self.highlight_color, 'opacity': 100," in source
    assert "self.tool_styles['highlight'] = {'color': self.highlight_color,\n                                          'opacity': 100," in source
    assert "self.tool_styles['highlight_line'] = {'color': self.highlight_color,\n                                               'opacity': 100," in source
    assert "kind == 'highlight'" in body('ImageCanvas', '_apply_item_appearance')
    # Older alpha values such as 35 remain accepted and saved unchanged.
    from yomunote.vector_marks import make_highlight, make_highlight_line, make_stroke
    assert make_highlight((.1, .1, .3, .1), '#ffcc33', 35)['opacity'] == 35
    assert make_highlight_line((.1, .1), (.4, .1), '#ffcc33', .01, 35)['opacity'] == 35
    assert make_stroke([[.1,.1],[.2,.2]], '#ffcc33', .005,
                       blend='multiply', opacity=35)['opacity'] == 35
