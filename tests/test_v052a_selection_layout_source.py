"""v0.5.2a source-level regression tests (work without PySide6)."""
from pathlib import Path
import ast

SOURCE = Path(__file__).resolve().parents[1] / 'yomunote' / 'window.py'


def _source():
    return SOURCE.read_text(encoding='utf-8')


def test_resize_handle_uses_rectf_directly():
    source = _source()
    # QGraphicsItem.mapRectToScene(QRectF) returns a QRectF, not a QPainterPath.
    assert 'item.mapRectToScene(item.path().boundingRect()).boundingRect()' not in source
    assert source.count('item.mapRectToScene(item.path().boundingRect())') == 3


def test_native_colour_pick_does_not_edit_alpha():
    source = _source()
    root = ast.parse(source)
    method = next(n for n in ast.walk(root) if isinstance(n, ast.FunctionDef)
                  and n.name == '_pick_appearance_color')
    assert 'ShowAlphaChannel' not in ast.get_source_segment(source, method)
    assert 'opacity.setValue' not in ast.get_source_segment(source, method)


def test_appearance_stays_local_to_annotation_pane_and_has_one_reusable_editor():
    source = _source()
    assert 'class AnnotationColourSwatch' in source
    assert 'class AnnotationOpacitySlider' in source
    assert 'self.opacity_menu = QMenu(self.opacity_button)' not in source
    assert 'layout.addWidget(self.appearance_panel)' in source
    assert 'self.stroke_width_control = QDoubleSpinBox' in source
    assert "self._palette_channel = 'stroke'" in source
    assert 'self.palette_target = QComboBox()' not in source
    assert 'self.stroke_opacity_control = slider' in source
    assert 'self.fill_opacity_control = slider' in source
    assert 'self._appearance_changed()' in source
