"""Source-level invariants for native Qt paragraph and scroll handling."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
EDITOR=(ROOT/'yomunote/editor.py').read_text()
WINDOW=(ROOT/'yomunote/window.py').read_text()


def test_four_margins_are_native_root_frame_properties():
    assert 'document.rootFrame()' in EDITOR
    for name in ('setTopMargin','setBottomMargin','setLeftMargin','setRightMargin'):
        assert f'fmt.{name}' in EDITOR


def test_spacing_is_native_qt_block_format_and_list_native():
    assert 'QTextBlockFormat.LineHeightTypes.ProportionalHeight' in EDITOR
    assert 'fmt.setLineHeight' in EDITOR
    assert 'block.textList()' in EDITOR
    assert 'self._target_block_positions(selected)' in EDITOR
    assert 'self._refresh_list_neighbour_spacing(positions)' in EDITOR
    assert 'self.editor.list_return_handler' in EDITOR


def test_jump_to_edit_and_resize_do_not_mutate_text():
    assert 'showJumpEditPosition' in WINDOW
    assert 'self.jump_edit_button.setVisible' in EDITOR
    assert 'self.editor.ensureCursorVisible()' in EDITOR
    assert 'restore_view_state(state, restore_cursor=False)' in EDITOR
    assert 'bar.value() + displacement' in EDITOR
    assert 'ed.preserve_view_state(ed.undo)' in WINDOW


def test_page_setup_and_spacing_ui_both_available():
    assert "options.addAction(self.action('Notes Page Setup…'" in WINDOW
    assert "spacing_menu.addAction('Custom paragraph spacing…'" in EDITOR
    assert "more_menu.addAction('Notes page setup…'" in EDITOR
