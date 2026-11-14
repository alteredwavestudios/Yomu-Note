"""v0.5.4 source and release guards for environments without PySide6."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WINDOW = (ROOT / 'yomunote/window.py').read_text(encoding='utf8')


def method_source(name, cls='ProjectPane'):
    module = ast.parse(WINDOW)
    for node in module.body:
        if isinstance(node, ast.ClassDef) and node.name == cls:
            for child in node.body:
                if isinstance(child, ast.FunctionDef) and child.name == name:
                    return ast.get_source_segment(WINDOW, child)
    raise AssertionError(f'{cls}.{name} missing')


def test_reuses_one_appearance_widget_without_old_nested_popup():
    creation = method_source('_create_annotation_quick_edit')
    assert 'layout.addWidget(self.appearance_panel)' in creation
    assert 'self.appearance_menu' not in creation
    assert 'quick_arrow_sliders' not in WINDOW
    assert 'self.opacity_menu = ' not in WINDOW
    assert 'self.quick_thickness = AnnotationOpacitySlider' in WINDOW
    assert 'self.stroke_width_control = QDoubleSpinBox' in WINDOW


def test_appearance_edits_still_call_existing_history():
    selection = method_source('_annotation_selection_changed')
    assert '_sync_annotation_quick_edit(mark)' in selection
    assert '_palette_channel' in selection
    edits = method_source('_appearance_changed')
    assert 'self.history.perform(CallbackAction(' in edits
    assert 'Change Annotation Appearance' in edits
    assert '_displayed_appearance' in edits
    assert 'self._preview_annotation_appearance' in WINDOW


def test_theme_scope_and_draggable_panel():
    theme = method_source('_theme_annotation_quick_edit')
    assert 'QDoubleSpinBox' in theme
    assert "colours['paper']" in theme and "colours['ink']" in theme
    assert 'QSlider::groove:horizontal' in theme
    # v0.5.4b: a graphics effect on the whole panel made child controls
    # disappear on hover. The shadow belongs to a sibling backdrop instead.
    assert 'QGraphicsDropShadowEffect(panel)' not in WINDOW
    assert 'AnnotationQuickEditBackdrop(self.canvas.viewport())' in WINDOW
    assert 'panel.installEventFilter(self)' in WINDOW
    assert 'self.quick_drag_handle.installEventFilter(self)' in WINDOW
    assert '_quick_edit_custom_position = True' in method_source('eventFilter')
    assert 'self._quick_edit_custom_position' in method_source('_position_annotation_quick_edit')


def test_toolbar_comfortable_and_clear_separate():
    assert "mini_tool('Select'" in WINDOW
    assert "tool_group('▱ Draw'" in WINDOW
    assert "LabelledHighlightButton()" in WINDOW
    assert "mini_tool('Clear'" in WINDOW
    assert "mini_tool('Colour'" in WINDOW
    assert 'eraser.menu().addAction(' not in WINDOW
    assert "self.annotation_mode_buttons['eraser'] = eraser" in WINDOW


def test_navigator_setting_is_separate_from_width_cycle_and_reused_for_menu():
    assert "self.nav_cycle.setText('▦')" in WINDOW
    assert "self.settings.setValue('showPageNavigator', bool(visible))" in WINDOW
    assert 'self.shelf.setVisible(visible)' in method_source('set_navigator_visible')
    assert '_navigator_restore_width' in method_source('save')
    assert 'self.navigator_toggle.clicked.connect(self.toggle_navigator_visibility)' in WINDOW
    assert "view.addAction('Show Page Navigator')" in WINDOW
    assert "('Ctrl+Alt+Up', -1), ('Ctrl+Alt+Down', 1)" in WINDOW


def test_no_changes_to_core_modules_from_v053():
    # This test is also checked against the source archive during packaging.
    assert 'from .editor import NotesEditor' in WINDOW
    assert 'class ProjectPane(QWidget)' in WINDOW
    assert 'class MainWindow(QMainWindow)' in WINDOW
