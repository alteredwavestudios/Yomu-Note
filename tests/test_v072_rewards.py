"""Qt-free checks for the v0.7.2 Pomodoro reminder ladder."""
from yomunote.focus_logic import (FOCUS_REMINDERS, BREAK_REMINDERS,
                                   escalating_reminder_message, reminder_slot)

def test_ten_reminders_per_mode():
    assert len(FOCUS_REMINDERS) == len(BREAK_REMINDERS) == 10
    assert all(0 < len(m) <= 150 for m in FOCUS_REMINDERS + BREAK_REMINDERS)
    assert 'hyperfocusing' in FOCUS_REMINDERS[-1]
    assert 'stop pestering' in BREAK_REMINDERS[-1]

def test_reminders_advance_without_overrun():
    for mode, lines in [('Focus', FOCUS_REMINDERS), ('Short break', BREAK_REMINDERS)]:
        for i, line in enumerate(lines):
            assert escalating_reminder_message(mode, i) == line
        assert escalating_reminder_message(mode, 999) == lines[-1]
    assert reminder_slot(599) == 9
    assert reminder_slot(600) is None
