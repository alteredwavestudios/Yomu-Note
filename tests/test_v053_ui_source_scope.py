"""Source-level guards for UI scope, run without Qt on build servers."""
from pathlib import Path

BASE=Path(__file__).resolve().parents[1]
WINDOW=(BASE/'yomunote/window.py').read_text(encoding='utf-8')


def test_compact_groups_and_quick_editor_exists():
    for key in ('drawing', 'highlight', 'erase'):
        assert f"'{key}'" in WINDOW
    for key in ('_create_annotation_quick_edit',
                '_sync_annotation_quick_edit', '_position_annotation_quick_edit',
                '_dismiss_annotation_quick_edit', '_commit_arrow_head'):
        assert f'def {key}(' in WINDOW
    assert 'setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)' in WINDOW
    assert "self.appearance_button.setIcon(line_icon('palette'))" in WINDOW
    assert 'cl.addWidget(self.appearance_panel)' not in WINDOW


def test_page_arrows_reuse_existing_move_selection_and_shortcuts():
    for widget in ('navigator_previous', 'navigator_next',
                   'preview_previous', 'preview_next'):
        assert f'self.{widget}' in WINDOW
    assert "'Previous page · Ctrl+Alt+Up'" in WINDOW
    assert "'Next page · Ctrl+Alt+Down'" in WINDOW
    assert "('Ctrl+Alt+Up', -1), ('Ctrl+Alt+Down', 1)" in WINDOW
    assert 'self.nav_cycle.setText(\'▦\')' in WINDOW


def test_no_new_mouse_wheel_override_or_growing_mark_scene():
    assert 'self.canvas.editingGesture.connect(self._annotation_editing_gesture)' in WINDOW
    assert "self.set_annotation_mode('select')\n            self.canvas.select_mark_by_id(stroke['id'])" in WINDOW
    assert "max(0.5, min(100" not in WINDOW  # avoid hardcoded display-only width conversion
