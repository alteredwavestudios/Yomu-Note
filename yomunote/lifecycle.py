"""Deferred release of closed notebook workspaces (no Qt dependency).

A running background task may still read a closed notebook's extracted PDF.
Never remove that workspace before the owning pane's task completion has
reached the GUI thread.  Disposal is deliberately two-phase: the first idle
pass schedules Qt widget deletion; the following pass closes the workspace.

Only whole *closed/replaced* notebooks enter this queue.  Undoable deleted
TABS in the currently open notebook remain parked until their history is
cleared; this module must not silently invalidate Undo/Redo.
"""

from dataclasses import dataclass
from typing import Callable


@dataclass
class _Retired:
    notebook: object
    panes: tuple
    deletion_requested: bool = False


class RetiredNotebookQueue:
    """Simple single-GUI-thread lifecycle gate for workspaces and widgets."""

    def __init__(self):
        self._entries: list[_Retired] = []

    def __len__(self) -> int:
        return len(self._entries)

    def add(self, notebook: object, panes) -> None:
        if any(entry.notebook is notebook for entry in self._entries):
            return
        # Deduplicate pane identities so a parked + visible reference cannot
        # schedule two deferred Qt deletions for the same widget.
        unique = {id(p): p for p in panes if p is not None}
        self._entries.append(_Retired(notebook, tuple(unique.values())))

    def advance(self, delete_pane: Callable[[object], None]) -> bool:
        """Perform one non-blocking cleanup step; return True if work remains.

        Called from a GUI QTimer.  A pane's `_tasks` set is cleared ONLY by
        its queued GUI-thread task completion callback.  `delete_pane` should
        call QObject.deleteLater(), never delete synchronously.
        """
        remaining = []
        for entry in self._entries:
            if not entry.deletion_requested:
                if any(getattr(pane, '_tasks', None) for pane in entry.panes):
                    remaining.append(entry)
                    continue
                for pane in entry.panes:
                    delete_pane(pane)
                entry.deletion_requested = True
                remaining.append(entry)
            else:
                # One subsequent Qt event-loop turn must happen after
                # deleteLater() before deleting original source assets.
                try:
                    entry.notebook.close()
                except OSError:
                    # A temporary file can still be briefly held by a native
                    # parser on Windows. Retry cleanup instead of losing the
                    # only owned reference to the working directory.
                    remaining.append(entry)
        self._entries = remaining
        return bool(remaining)
