"""No-Qt resource-lifetime checks; run on CI even without PySide6."""
from yomunote.lifecycle import RetiredNotebookQueue


class FakeNotebook:
    def __init__(self):
        self.closed = 0

    def close(self):
        self.closed += 1


class FakePane:
    def __init__(self, tasks=()):
        self._tasks = set(tasks)
        self.deleted = 0

    def deleteLater(self):
        self.deleted += 1


def test_workers_guard_workspace_until_gui_completion():
    queue = RetiredNotebookQueue()
    book = FakeNotebook()
    pane = FakePane({'rendering-large-pdf'})
    queue.add(book, [pane])
    assert queue.advance(lambda p: p.deleteLater())
    assert book.closed == pane.deleted == 0
    pane._tasks.clear()  # equivalent to queued GuiReceiver.finished() callback
    assert queue.advance(lambda p: p.deleteLater())
    assert pane.deleted == 1 and book.closed == 0
    assert not queue.advance(lambda p: p.deleteLater())
    assert book.closed == 1
    assert len(queue) == 0


def test_multiple_panes_wait_for_last_task_and_are_deduplicated():
    queue = RetiredNotebookQueue()
    book = FakeNotebook()
    first, second = FakePane(), FakePane({'ocr'})
    queue.add(book, [first, second, first])
    queue.add(book, [second])  # double retirement is ignored
    assert len(queue) == 1
    queue.advance(lambda p: p.deleteLater())
    assert first.deleted == second.deleted == 0
    second._tasks.clear()
    queue.advance(lambda p: p.deleteLater())
    assert first.deleted == second.deleted == 1
    queue.advance(lambda p: p.deleteLater())
    assert book.closed == 1


def test_separate_notebooks_release_independently():
    queue = RetiredNotebookQueue()
    slow, fast = FakeNotebook(), FakeNotebook()
    active = FakePane({'worker'})
    queue.add(slow, [active])
    queue.add(fast, [FakePane()])
    queue.advance(lambda p: p.deleteLater())
    queue.advance(lambda p: p.deleteLater())
    assert fast.closed == 1 and slow.closed == 0
    active._tasks.clear()
    queue.advance(lambda p: p.deleteLater())
    queue.advance(lambda p: p.deleteLater())
    assert slow.closed == 1


def test_empty_notebook_can_be_released():
    queue = RetiredNotebookQueue()
    book = FakeNotebook()
    queue.add(book, [])
    queue.advance(lambda p: p.deleteLater())
    assert book.closed == 0
    assert not queue.advance(lambda p: p.deleteLater())
    assert book.closed == 1


def test_workspace_cleanup_retries_windows_temp_lock():
    class LockedNotebook(FakeNotebook):
        def close(self):
            self.closed += 1
            if self.closed == 1:
                raise PermissionError('locked in Windows temporary folder')

    queue = RetiredNotebookQueue()
    book = LockedNotebook()
    pane = FakePane()
    queue.add(book, [pane])
    queue.advance(lambda p: p.deleteLater())
    assert queue.advance(lambda p: p.deleteLater())
    assert pane.deleted == 1
    assert not queue.advance(lambda p: p.deleteLater())
    assert book.closed == 2
