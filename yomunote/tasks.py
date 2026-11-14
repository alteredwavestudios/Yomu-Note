"""Worker tasks with explicit Qt GUI-thread delivery of results."""
from __future__ import annotations
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot, Qt

from .diagnostics import logger


class TaskSignals(QObject):
    """A Qt signal carrier (QRunnable itself cannot declare signals)."""
    complete = Signal(object, object)


class Task(QRunnable):
    """A job that runs on a Qt worker thread, NOT on the UI thread.

    The job sends a result or error via a Qt signal. GuiReceiver then runs
    its callback on the main thread, which is the only thread allowed to
    create widgets or update previews and text editors.
    """
    def __init__(self, callback, *args):
        super().__init__()
        self.callback = callback
        self.args = args
        self.signals = TaskSignals()
        self.setAutoDelete(False)

    def run(self):
        try:
            result = self.callback(*self.args)
            self.signals.complete.emit(result, None)
        except Exception as error:
            # Keep the full traceback in a private local error log.
            # The GUI still receives a short, readable error message.
            logger.exception('Background task failed')
            self.signals.complete.emit(None, f'{type(error).__name__}: {error}')


class GuiReceiver(QObject):
    """A QObject in the main thread so UI callbacks never run in worker threads."""
    def __init__(self, owner, task, handler):
        super().__init__(owner)
        self.owner = owner
        self.task = task
        self.handler = handler

    @Slot(object, object)
    def finished(self, result, error):
        self.owner._tasks.discard(self.task)
        try:
            if not getattr(self.owner, '_closed', False):
                self.handler(result, error)
        finally:
            self.deleteLater()


def start_task(owner, callback, handler, *args, priority=0):
    """Queue slow file work; deliver its result on the Qt GUI thread.

    ``owner._tasks`` holds a strong reference while the job is running, so
    Python cannot garbage-collect the QRunnable prematurely. ``handler``
    should update widgets only when the owning tab/window is still alive.
    """
    task = Task(callback, *args)
    if not hasattr(owner, '_tasks'):
        owner._tasks = set()
    owner._tasks.add(task)
    receiver = GuiReceiver(owner, task, handler)
    task.signals.complete.connect(receiver.finished, Qt.ConnectionType.QueuedConnection)
    QThreadPool.globalInstance().start(task, priority)
