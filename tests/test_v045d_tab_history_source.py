"""Static guard that tab histories never alias the window-global object."""
from pathlib import Path


def test_per_tab_history_is_allocated_and_used_for_native_text():
    src = (Path(__file__).resolve().parents[1] / 'yomunote' / 'window.py').read_text()
    assert 'pane.history = UnifiedHistory(max_actions=1000,' in src
    assert 'pane.history.record_applied(external_undo_action(' in src
    assert 'pane.history = self.history' not in src
    assert 'return pane.history if pane is not None else self._fallback_history' in src


def test_scroll_position_restored_after_separating_text_commands():
    src = (Path(__file__).resolve().parents[1] / 'yomunote' / 'window.py').read_text()
    separator = src.split('def _separate_text_commands(self):',1)[1].split('def add_blank(',1)[0]
    assert 'reading_position = bar.value()' in separator
    assert 'bar.setValue(max(bar.minimum(),' in separator
