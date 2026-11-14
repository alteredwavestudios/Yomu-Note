"""Lightweight v0.7.2b source/contrast checks for runners without PySide6."""
from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1]
GROUPS = (ROOT / 'yomunote/page_groups_ui.py').read_text('utf8')
WINDOW = (ROOT / 'yomunote/window.py').read_text('utf8')
UI = (ROOT / 'yomunote/ui.py').read_text('utf8')


def _palette_update():
    tree = ast.parse(WINDOW)
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == 'update'
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == 'THEMES'):
            return ast.literal_eval(node.args[0])
    raise AssertionError('Missing theme registry update')


def _luminance(value):
    rgb = [int(value[i:i+2], 16) / 255 for i in (1, 3, 5)]
    rgb = [c/12.92 if c <= .04045 else ((c + .055)/1.055)**2.4 for c in rgb]
    return sum(a*b for a, b in zip((.2126, .7152, .0722), rgb))


def _contrast(one, two):
    hi, lo = sorted((_luminance(one), _luminance(two)), reverse=True)
    return (hi+.05)/(lo+.05)


def test_larger_checkbox_target_still_uses_native_data_and_undo_signal():
    assert 'def checkbox_hit_rect(' in GROUPS
    assert 'indicator.adjusted(-7, -8, 7, 8)' in GROUPS
    assert 'def editorEvent(' in GROUPS
    assert 'model.setData(index, new, Qt.ItemDataRole.CheckStateRole)' in GROUPS
    assert 'self.readToggled.emit(' in GROUPS
    assert 'def _checkbox_rect(' in GROUPS
    assert 'self._checkbox_rect(option, index)' in GROUPS
    assert 'item.setSizeHint(0, QSize(100, 72))' not in GROUPS


def test_navigator_density_has_no_extra_thumbnail_cache_or_horizontal_scroll():
    assert "density = ('mini' if width < 100" in GROUPS
    assert 'def set_navigator_density(' in GROUPS
    assert 'ScrollBarAlwaysOff' in GROUPS
    assert "'wide': QSize(58, 76)" in GROUPS
    assert 'self.doItemsLayout()' in GROUPS
    assert 'self.group_tree.set_navigator_density(width)' in WINDOW
    assert 'self.shelf.setMaximumWidth(540)' in WINDOW
    assert 'target = min(540, max(74' in WINDOW
    assert 'THUMB_LIMIT = 20' in WINDOW
    assert 'self._group_anim = QVariantAnimation(self)' in GROUPS


def test_kawaii_notice_qss_has_one_closing_brace():
    section = UI.split('class KawaiiNotice(QLabel):')[1].split('    def show_message(')[0]
    assert 'font-size: 12px; }")' in section
    assert 'font-size: 12px; }}")' not in section
    assert "self.setObjectName('kawaiiNotice')" in section


def test_playful_and_crisp_are_defaults_without_overwriting_saved_preferences():
    assert WINDOW.count("self.settings.value('readingCelebrationMotion', 'playful')") == 2
    assert "self.settings.value('previewClarity', 'crisp')" in WINDOW
    assert "self.settings.setValue('readingCelebrationMotion', reading_motion.currentData())" in WINDOW


def test_six_kawaii_palettes_have_readable_typography():
    data = _palette_update()
    for key in ('strawberry', 'melon-soda', 'peach-mochi',
                'candy-cloud', 'grape-fizz', 'arcade-hearts'):
        colours = data[key]
        for surface in ('paper', 'panel', 'window', 'shelf', 'btn', 'btn2'):
            assert _contrast(colours['ink'], colours[surface]) >= 4.5, (key, surface)
        assert _contrast(colours['muted'], colours['panel']) >= 4.5, key
        assert _contrast(colours['accent'], colours['panel']) >= 4.5, key
