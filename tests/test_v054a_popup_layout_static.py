"""Guards against v0.5.4's overlapping/disappearing Quick Edit controls."""
import ast
from pathlib import Path

WINDOW = (Path(__file__).resolve().parents[1] / 'yomunote/window.py').read_text(encoding='utf8')


def test_fixed_layout_inside_popup_instead_of_wrapping_toolbars():
    # Popup used two WrapBar instances. Their custom FlowLayout's height-for-
    # width calculation did not allocate enough height inside the popup,
    # allowing the swatches, palette, and thickness row to overlap.
    assert "bar = WrapBar('Compact annotation appearance controls')" not in WINDOW
    assert "quick = WrapBar('Quick annotation colour palette')" not in WINDOW
    assert "appearance_layout.addWidget(paint_widget)" in WINDOW
    assert "quick_grid = QGridLayout()" in WINDOW
    assert "quick_grid.addWidget(swatch, i // 5, i % 5)" in WINDOW
    assert "quick_layout.addLayout(quick_grid)" in WINDOW


def test_thickness_label_number_and_slider_have_independent_rows():
    assert 'thickness_row = QVBoxLayout(self.quick_thickness_row)' in WINDOW
    assert 'thickness_caption.addWidget(self.stroke_width_control)' in WINDOW
    assert 'thickness_row.addWidget(self.quick_thickness)' in WINDOW
    assert 'thickness_row.addLayout(thickness_caption)' in WINDOW


def test_live_colour_and_opacity_connections_preserved():
    assert 'self.pen_colour.clicked.connect(lambda: self._select_palette_channel(\'stroke\'))' in WINDOW
    assert 'self.fill_colour.clicked.connect(lambda: self._select_palette_channel(\'fill\'))' in WINDOW
    assert 'slider.editFinished.connect(self._appearance_changed)' in WINDOW
    assert "'Change Annotation Appearance'" in WINDOW
    assert 'self._quick_edit_dismissed' in WINDOW


def test_only_toolbar_button_sizing_is_increased():
    assert "button.setObjectName('annotationToolbarButton')" in WINDOW
    assert 'button.setFixedHeight(39)' in WINDOW
    assert 'padding: 6px 10px' in WINDOW
    assert 'self.setMinimumSize(118, 39)' in WINDOW
    assert "button.setToolTip(tip)" in WINDOW
