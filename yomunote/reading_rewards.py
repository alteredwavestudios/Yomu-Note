"""Optional, display-only study encouragement for Yomu Note.

Completion and milestone messages do not alter reading flags, file storage,
Undo, notebook hierarchy, timers or any content. Keeping these functions Qt-free
allows us to test boundaries without starting the GUI.
"""
from __future__ import annotations
import random

GROUP_MESSAGES = (
    "A little victory! You've finished {name}! (ﾉ◕ヮ◕)ﾉ*:･ﾟ✧",
    "Lovely work! {name} is officially explored. (´｡• ᵕ •｡`) ♡",
    "Another chapter of lore unlocked: {name}! (≧▽≦) 🌸",
)
TAB_MESSAGES = (
    "You did it! You've finished {name}! (ﾉ´ヮ`)ﾉ*: ･ﾟ✧",
    "A whole tab completed: {name}! Your brain is unstoppable. (｡•̀ᴗ-)✧",
    "Hooray for {name}! All those pages, all done. ♡ (⁎˃ᴗ˂⁎)",
)
NOTEBOOK_MESSAGES = (
    "すごい！ You've completed {name}! Every page, every chapter! (ﾉ◕ヮ◕)ﾉ*:･ﾟ✧",
    "The entire {name} notebook is done! Time for a victory dance! (≧▽≦) ♡",
    "All readings complete in {name}! You absolute star! (´｡• ᵕ •｡`) 🌸",
)
MILESTONE_MESSAGES = {
    25: "25% of your notebook explored! Little steps really add up. (｡･ω･｡)ﾉ♡",
    50: "Halfway through the notebook! Look how far you've come. (ﾉ´ヮ`)ﾉ*:･ﾟ✧",
    75: "75% complete! The finish line is waving hello! (⁎˃ᴗ˂⁎) 🌸",
}

def _short_name(name: str, limit: int = 74) -> str:
    """Keep user-created headings readable and safe in a small notice card."""
    compact = ' '.join(str(name).split()) or 'your reading'
    return compact if len(compact) <= limit else compact[:limit-1] + '…'


def celebration_message(level: str, name: str, *, variant: int | None = None) -> str:
    """Return a varied plain-text message without interpreting heading markup."""
    sequences = {'group': GROUP_MESSAGES, 'tab': TAB_MESSAGES,
                 'notebook': NOTEBOOK_MESSAGES}
    lines = sequences[level]
    template = random.choice(lines) if variant is None else lines[variant % len(lines)]
    return template.format(name=_short_name(name))


def crossed_milestone(before_done: int, after_done: int, total: int) -> int | None:
    """Highest 25/50/75 threshold crossed by this *positive* manual action.

    Use exact integer ratios instead of display percentages, which round up.
    Large group ticks crossing several thresholds produce just one notice.
    """
    if total <= 0 or after_done <= before_done:
        return None
    passed = [pct for pct in (25, 50, 75)
              if before_done * 100 < pct * total <= after_done * 100]
    return passed[-1] if passed else None
