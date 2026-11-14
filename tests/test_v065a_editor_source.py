"""Headless source audit for the focused v0.6.5a fixes.

These tests do not replace the live-Qt tests. They ensure that future edits
cannot accidentally remove important guardrails when Qt is unavailable.
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EDITOR = (ROOT / 'yomunote/editor.py').read_text(encoding='utf8')
WINDOW = (ROOT / 'yomunote/window.py').read_text(encoding='utf8')


def test_numbering_is_native_and_nested_bullets_have_distinct_styles():
    assert 'QTextListFormat.Style.ListCircle' in EDITOR
    assert 'QTextListFormat.Style.ListSquare' in EDITOR
    assert 'self._has_previous_list_parent(block)' in EDITOR
    assert 'actual_list.itemNumber(block) <= 0' not in EDITOR
    assert 'point.createList(fmt)' in EDITOR
    assert 'peer.add(block)' in EDITOR


def test_enter_uses_current_caret_and_preserves_the_reading_position():
    assert 'writer = QTextCursor(self.textCursor())' in EDITOR
    assert 'self.restore_view_state(view, restore_cursor=False)' in EDITOR
    assert 'self._normalise_list_block_presentation(block)' in EDITOR
    assert 'self.editor.list_return_handler = self._after_list_return' in EDITOR


def test_heading_status_reads_qt_block_heading_not_font_guess():
    assert 'cursorPositionChanged.connect(self._sync_heading_choice)' in EDITOR
    assert 'selectionChanged.connect(self._sync_heading_choice)' in EDITOR
    assert '.blockFormat().headingLevel()' in EDITOR
    assert 'with QSignalBlocker(self.heading_choice)' in EDITOR
    assert "'H6', 'Mixed'" in EDITOR


def test_all_dialog_numeric_inputs_inherit_the_global_theme():
    assert 'def application_palette(c: dict)' in WINDOW
    assert 'app.setPalette(application_palette(colours))' in WINDOW
    assert 'QDoubleSpinBox' in WINDOW and 'QAbstractSpinBox' in WINDOW
    assert "QPalette.ColorRole.Base: 'paper'" in WINDOW
    assert "QPalette.ColorRole.Text: 'ink'" in WINDOW
    ast.parse(EDITOR)
    ast.parse(WINDOW)
