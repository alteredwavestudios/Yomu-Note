"""Tiny, testable rules for Pomodoro completion and non-nagging reminders.

This module intentionally has no dependency on Qt. The visual timer can call
``reminder_slot`` from a once-per-second tick; if the UI pauses temporarily,
it plays at most one notification when the event loop resumes.
"""
from __future__ import annotations

REMINDER_PERIOD_SECONDS = 60
REMINDER_WINDOW_SECONDS = 10 * 60


def reminder_slot(overdue_seconds: float) -> int | None:
    """Return which reminder minute is due, or None after ten minutes.

    Slot 0 is the first sound when a session ends, slots 1–9 repeat at
    minute boundaries. There are no notifications at or after minute 10.
    Negative values indicate the session has not yet finished.
    """
    if overdue_seconds < 0 or overdue_seconds >= REMINDER_WINDOW_SECONDS:
        return None
    return int(overdue_seconds // REMINDER_PERIOD_SECONDS)


def finished_session_message(mode: str) -> tuple[str, str]:
    """Select the original three-second jingle and friendly message."""
    if mode == 'Focus':
        return 'break', 'Your study flower bloomed! Time for a wee break 🌸'
    return 'study', 'Break over! Ready for a fresh little study session? ✨'


# Keep each message at most 150 characters. A future preferences editor can
# reuse this bound without changing the reminder schedule or timer data.
MAX_REMINDER_CHARACTERS = 150

FOCUS_REMINDERS = (
    "Time for a wee break! You earned a stretch. (｡･ω･｡)ﾉ♡",
    "I know you're working hard, but breaks are important! (´｡• ᵕ •｡`) ♡",
    "Hydration check! Your teacup misses you. (っ˘ω˘ς )",
    "Psst... even clever brains need a loading screen. (・ω・)ノ",
    "Your shoulders have filed a formal complaint. (￣▽￣*)ゞ",
    "The break fairy is tapping on the window now. (ﾉ◕ヮ◕)ﾉ*:･ﾟ✧",
    "This is a tiny intervention from your chair. Please stand. (¬‿¬)",
    "You've been studying so hard the desk is learning the subject. (≧▽≦)",
    "One last nudge: I promise the pages won't run away! (｡•̀ᴗ-)✧",
    "Ah, hyperfocusing, are we? Well I won't disturb you anymore but feel free to take a break when you're ready!",
)

BREAK_REMINDERS = (
    "Break's over! Fancy a fresh little focus session? (ﾉ´ヮ`)ﾉ*: ･ﾟ",
    "Hellooo? Your notes are waving from across the room. (｡･∀･)ﾉﾞ",
    "That was a very respectable tea break. Shall we? (´• ω •`)",
    "Your study flower has packed its tiny schoolbag. (⁎˃ᴗ˂⁎)",
    "Are the biscuits holding you hostage? Blink twice. (¬‿¬)",
    "Ahem! Official summons from the Ministry of Getting Stuff Done. (｀・ω・´)",
    "Your notebook has begun sending concerned postcards. (ಥ_ಥ)",
    "The sofa is lovely, but it can't write your notes for you! (≧▽≦)",
    "I'm starting to think you and the kettle are co-authoring a thesis. (￣▽￣)",
    "Okay, you and the sofa win this round! I'll stop pestering. Come back whenever you're ready. (｡•̀ᴗ-)✧",
)

assert all(0 < len(s) <= MAX_REMINDER_CHARACTERS
           for s in FOCUS_REMINDERS + BREAK_REMINDERS)

def escalating_reminder_message(mode: str, slot: int) -> str:
    """A fixed, safe ten-step reminder ladder, ending without more nudges."""
    messages = FOCUS_REMINDERS if mode == 'Focus' else BREAK_REMINDERS
    return messages[max(0, min(len(messages)-1, int(slot)))]
