"""Yomu Note v0.4.5 candidate: Qt-independent shared history foundation.

This is intentionally NOT a replacement for QTextDocument's native text undo stack.
It coordinates reversible operations across notes, annotations and structure.

Integration is required in the actual Yomu Note application. The model classes and
widgets in the user's current v0.4.4c archive were not available to this build.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Callable, Iterator, Protocol, TypeVar

MAX_ACTIONS = 1_000
MAX_MEMORY_BYTES = 200 * 1024 * 1024


class Undoable(Protocol):
    label: str
    estimated_bytes: int
    def undo(self) -> None: ...
    def redo(self) -> None: ...


@dataclass
class CallbackAction:
    """Wrap a model-specific reversible operation without cloning media bytes."""
    label: str
    undo_callback: Callable[[], None]
    redo_callback: Callable[[], None]
    estimated_bytes: int = 256

    def undo(self) -> None:
        self.undo_callback()

    def redo(self) -> None:
        self.redo_callback()


@dataclass
class GroupAction:
    """One Undo for a grouped import, multi-page operation or user transaction."""
    label: str
    actions: list[Undoable] = field(default_factory=list)

    @property
    def estimated_bytes(self) -> int:
        return 128 + sum(max(0, a.estimated_bytes) for a in self.actions)

    def redo(self) -> None:
        applied: list[Undoable] = []
        try:
            for action in self.actions:
                action.redo()
                applied.append(action)
        except Exception:
            for action in reversed(applied):
                action.undo()
            raise

    def undo(self) -> None:
        undone: list[Undoable] = []
        try:
            for action in reversed(self.actions):
                action.undo()
                undone.append(action)
        except Exception:
            # Try to restore a coherent state before propagating the failure.
            for action in reversed(undone):
                action.redo()
            raise


class UnifiedHistory:
    """Chronological, bounded undo/redo coordinator.

    * ``perform`` executes a new action once and registers it.
    * ``record_applied`` is used for operations already completed by Qt, e.g.
      QTextDocument.undoCommandAdded or a PDF drawing/annotation gesture.
    * redo history is invalidated on a newly performed action.
    * very large single entries remain undoable rather than being silently
      discarded; media should be held by stable on-disk references instead
      of embedding entire source PDFs in an action's data.

    The byte cap is an estimate of retained custom command payloads, NOT an
    application process RSS cap (Qt's native text stack is separate).
    """

    def __init__(self, max_actions: int = MAX_ACTIONS,
                 max_memory_bytes: int = MAX_MEMORY_BYTES,
                 sequence_provider: Callable[[], int] | None = None):
        if max_actions < 1 or max_memory_bytes < 1:
            raise ValueError("History limits must be positive")
        self.max_actions = int(max_actions)
        self.max_memory_bytes = int(max_memory_bytes)
        self._undo: list[Undoable] = []
        self._redo: list[Undoable] = []
        self._replaying = False
        self._sequence_provider = sequence_provider
        self._local_sequence = 0
        self._listeners: list[Callable[[str | None, str | None], None]] = []

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    @property
    def next_undo_label(self) -> str | None:
        return self._undo[-1].label if self._undo else None

    @property
    def next_redo_label(self) -> str | None:
        return self._redo[-1].label if self._redo else None

    @property
    def next_undo_sequence(self) -> int:
        return getattr(self._undo[-1], '_history_sequence', 0) if self._undo else -1

    @property
    def next_redo_sequence(self) -> int:
        return getattr(self._redo[-1], '_history_sequence', 0) if self._redo else 10**18

    @property
    def action_count(self) -> int:
        return len(self._undo)

    @property
    def estimated_bytes(self) -> int:
        return sum(max(0, int(a.estimated_bytes)) for a in self._undo)

    @property
    def replaying(self) -> bool:
        return self._replaying

    def on_changed(self, callback: Callable[[str | None, str | None], None]) -> None:
        self._listeners.append(callback)
        callback(self.next_undo_label, self.next_redo_label)

    def _notify(self) -> None:
        for callback in tuple(self._listeners):
            callback(self.next_undo_label, self.next_redo_label)

    @contextmanager
    def _replay_scope(self) -> Iterator[None]:
        if self._replaying:
            raise RuntimeError("Nested history replay is not supported")
        self._replaying = True
        try:
            yield
        finally:
            self._replaying = False

    def perform(self, action: Undoable) -> None:
        if self.replaying:
            raise RuntimeError("Cannot perform a new action during Undo/Redo")
        # If execution fails, do not consume the existing redo branch.
        with self._replay_scope():
            action.redo()
        self.record_applied(action)

    def record_applied(self, action: Undoable) -> None:
        if self.replaying:
            # Native document signals can fire during undo/redo; ignore them.
            return
        if int(action.estimated_bytes) < 0:
            raise ValueError("History size estimate must not be negative")
        self._redo.clear()
        self._local_sequence += 1
        setattr(action, '_history_sequence',
                self._sequence_provider() if self._sequence_provider else self._local_sequence)
        self._undo.append(action)
        while len(self._undo) > 1 and (
            len(self._undo) > self.max_actions
            or self.estimated_bytes > self.max_memory_bytes
        ):
            self._undo.pop(0)
        self._notify()

    def undo(self) -> bool:
        if not self._undo:
            return False
        action = self._undo[-1]
        with self._replay_scope():
            action.undo()
        self._undo.pop()
        self._redo.append(action)
        self._notify()
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        action = self._redo[-1]
        with self._replay_scope():
            action.redo()
        self._redo.pop()
        self._undo.append(action)
        self._notify()
        return True

    def clear(self) -> None:
        if self.replaying:
            raise RuntimeError("Cannot clear history while replaying")
        self._undo.clear()
        self._redo.clear()
        self._notify()


T = TypeVar("T")


def rename_action(kind: str, object_id: str, old: str, new: str,
                  setter: Callable[[str, str], None]) -> CallbackAction:
    """Undoable rename for a page or tab, using its *stable* ID."""
    label = f"Rename {kind.title()}"
    return CallbackAction(label,
                          undo_callback=lambda: setter(object_id, old),
                          redo_callback=lambda: setter(object_id, new),
                          estimated_bytes=256 + len(old.encode()) + len(new.encode()))


def reorder_pages_action(tab_id: str, before: list[str], after: list[str],
                         set_order: Callable[[str, list[str]], None]) -> CallbackAction:
    """Always restore exact page IDs, not stale row indices."""
    if set(before) != set(after) or len(before) != len(after):
        raise ValueError("Reordering must keep exactly the same page IDs")
    if len(set(before)) != len(before):
        raise ValueError("Page IDs must be unique")
    return CallbackAction(
        "Reorder Pages",
        undo_callback=lambda: set_order(tab_id, before[:]),
        redo_callback=lambda: set_order(tab_id, after[:]),
        estimated_bytes=256 + 2 * sum(len(p.encode()) for p in before),
    )


def insert_pages_action(tab_id: str, index: int, pages: list[T],
                        insert: Callable[[str, int, list[T]], None],
                        remove_ids: Callable[[str, list[str]], None],
                        page_id: Callable[[T], str]) -> CallbackAction:
    """One action for insertion of one blank page or a whole PDF import.

    Retains page *model objects/references* only; large PDF data stays on disk.
    The application owns cleanup of unreferenced imported files.
    """
    snapshot = list(pages)
    ids = [page_id(page) for page in snapshot]
    if len(set(ids)) != len(ids):
        raise ValueError("Cannot insert duplicate page IDs")
    return CallbackAction(
        "Add Blank Page" if len(snapshot) == 1 and getattr(snapshot[0], "is_blank", False)
        else "Import Pages" if len(snapshot) != 1 else "Add Page",
        undo_callback=lambda: remove_ids(tab_id, ids[:]),
        redo_callback=lambda: insert(tab_id, index, snapshot[:]),
        estimated_bytes=512 + 80 * len(snapshot) + sum(len(i.encode()) for i in ids),
    )


def delete_pages_action(tab_id: str, index: int, pages: list[T],
                        insert: Callable[[str, int, list[T]], None],
                        remove_ids: Callable[[str, list[str]], None],
                        page_id: Callable[[T], str]) -> CallbackAction:
    insert_action = insert_pages_action(tab_id, index, pages, insert, remove_ids, page_id)
    return CallbackAction("Delete Pages", undo_callback=insert_action.redo,
                          redo_callback=insert_action.undo,
                          estimated_bytes=insert_action.estimated_bytes)


def external_undo_action(label: str, undo: Callable[[], None],
                         redo: Callable[[], None], estimate: int = 128) -> CallbackAction:
    """For an ALREADY performed native Qt text command or PDF annotation.

    Register with ``record_applied``; do not use ``perform`` (which would
    execute the action a second time). Keep the native Qt document alive for
    as long as its history entry is retained. Ensure a Qt typing group cannot
    silently merge across intervening annotation/structural actions.
    """
    return CallbackAction(label, undo_callback=undo, redo_callback=redo,
                          estimated_bytes=estimate)
