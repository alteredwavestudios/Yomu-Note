"""Source guards for non-GUI runners; native Qt tests live separately."""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1] / 'yomunote'


def test_pomodoro_notification_is_a_signal_not_a_disappearing_tooltip():
    ui = (ROOT/'ui.py').read_text('utf8')
    window = (ROOT/'window.py').read_text('utf8')
    assert 'reminder = Signal(str)' in ui
    assert 'self.reminder.emit(message)' in ui
    assert 'QToolTip.showText' not in ui
    assert 'self.focus_timer.reminder.connect(self._show_focus_reminder)' in window
    assert 'Qt.TextFormat.PlainText' in ui


def test_all_reading_bar_variants_are_animated_and_accessibility_aware():
    ui = (ROOT/'ui.py').read_text('utf8')
    window = (ROOT/'window.py').read_text('utf8')
    groups = (ROOT/'page_groups_ui.py').read_text('utf8')
    assert 'QEasingCurve.Type.InOutCubic' in ui
    assert 'self._target_units' in ui
    assert 'self.reduced_motion' in ui
    assert 'group_display_ratio' in groups
    assert 'self._group_anim = QVariantAnimation(self)' in groups
    assert "QProgressBar#readingProgress::chunk" in window
    assert 'readingAction = Signal(str, str, int)' in window
    assert 'self._show_reading_reward(MILESTONE_MESSAGES[threshold]' in window


def test_reading_states_not_bound_to_visual_message_or_timer():
    window = (ROOT/'window.py').read_text('utf8')
    assert 'self.readingAction.emit(level, name, delta)' in window
    assert 'self.readingAction.emit' not in window.split('    def _apply_read_snapshot(')[1].split('    def _toggle_read_status(')[0]
    assert "self.settings.value('readingCelebrations', 'true')" in window
    assert "self.settings.value('readingMilestones', 'true')" in window
