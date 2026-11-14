"""Pure-Python checks for celebratory wording and milestone boundaries."""
from yomunote.reading_rewards import (
    GROUP_MESSAGES, TAB_MESSAGES, NOTEBOOK_MESSAGES, MILESTONE_MESSAGES,
    celebration_message, crossed_milestone,
)
from yomunote.focus_logic import (
    FOCUS_REMINDERS, BREAK_REMINDERS, MAX_REMINDER_CHARACTERS,
    escalating_reminder_message, reminder_slot,
)


def test_every_pomodoro_line_has_safe_length_and_last_focus_line_is_exact():
    assert len(FOCUS_REMINDERS) == len(BREAK_REMINDERS) == 10
    assert all(0 < len(line) <= MAX_REMINDER_CHARACTERS
               for line in FOCUS_REMINDERS + BREAK_REMINDERS)
    assert FOCUS_REMINDERS[-1] == (
        "Ah, hyperfocusing, are we? Well I won't disturb you anymore "
        "but feel free to take a break when you're ready!")
    assert 'stop pestering' in BREAK_REMINDERS[-1]
    assert any('ﾉ' in message or '｡' in message
               for message in FOCUS_REMINDERS + BREAK_REMINDERS)


def test_reminders_map_to_exact_slots_without_extending_ten_minute_limit():
    assert reminder_slot(0) == 0
    assert reminder_slot(59.99) == 0
    assert reminder_slot(60) == 1
    assert reminder_slot(599.999) == 9
    assert reminder_slot(600) is None
    for mode, lines in [('Focus', FOCUS_REMINDERS), ('Short break', BREAK_REMINDERS),
                        ('Long break', BREAK_REMINDERS)]:
        for i, message in enumerate(lines):
            assert escalating_reminder_message(mode, i) == message


def test_milestone_is_exact_not_rounded_and_no_repeats_on_undo():
    assert crossed_milestone(0, 1, 100) is None
    assert crossed_milestone(24, 25, 100) == 25
    assert crossed_milestone(24, 50, 100) == 50
    assert crossed_milestone(25, 26, 100) is None
    assert crossed_milestone(49, 50, 100) == 50
    assert crossed_milestone(74, 75, 100) == 75
    assert crossed_milestone(75, 74, 100) is None
    assert crossed_milestone(50, 50, 100) is None
    assert crossed_milestone(0, 9, 10) == 75
    assert crossed_milestone(0, 0, 0) is None
    assert set(MILESTONE_MESSAGES) == {25, 50, 75}


def test_reading_reward_templates_use_actual_names_and_plain_strings():
    for name, templates, level in (
        ('Week 3', GROUP_MESSAGES, 'group'),
        ('Film Studies', TAB_MESSAGES, 'tab'),
        ('My notebook', NOTEBOOK_MESSAGES, 'notebook'),
    ):
        assert len(templates) >= 3
        for variant in range(len(templates)):
            message = celebration_message(level, name, variant=variant)
            assert name in message
            assert 0 < len(message) < 220
    assert '<b>Tea</b>' in celebration_message('group', '<b>Tea</b>', variant=0)
    assert len(celebration_message('group', 'X'*500, variant=0)) < 200


def test_reward_observer_does_not_change_read_model():
    from yomunote.reading_progress import set_read_status, notebook_totals
    class Project:
        def __init__(self, ids, read):
            self.pages = [{'id': id} for id in ids]
            self.read_page_ids = read
    p = Project(['A','B'], ['A'])
    p2 = Project(['C'], [])
    before = notebook_totals([p,p2])
    new = set_read_status(set(p.read_page_ids), ['A','B'], ['B'], True)
    # Only the model layer mutates the completion list.
    assert notebook_totals([p,p2]) == before
    p.read_page_ids = list(new)
    assert notebook_totals([p,p2]) == (2,3)
