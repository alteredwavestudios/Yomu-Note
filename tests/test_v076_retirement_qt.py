"""Exercise actual PySide6 lifecycle without touching the user's settings."""
import pytest

QtCore = pytest.importorskip('PySide6.QtCore')
QtWidgets = pytest.importorskip('PySide6.QtWidgets')

from yomunote.notebook import Notebook
import yomunote.window as window_module


def test_closed_notebook_waits_for_tasks_then_reclaims_temp_workspace(tmp_path, monkeypatch):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    first = Notebook.create(tmp_path, 'Original Notebook')
    path = first.path
    first.close()
    pref = QtCore.QSettings(str(tmp_path / 'settings.ini'), QtCore.QSettings.Format.IniFormat)
    pref.setValue('preferencesMigrated', True)
    pref.setValue('openProjects', [str(path)])
    monkeypatch.setattr(window_module, 'QSettings', lambda *args, **kwargs: pref)
    window = window_module.MainWindow()
    try:
        old = window.notebook
        old_workspace = old.workspace
        oldpane = window.active()
        # Simulate a long-running worker; closing its workspace here would
        # break a real PDF render/OCR job mid-read.
        if not hasattr(oldpane, '_tasks'):
            oldpane._tasks = set()
        pending = object()
        oldpane._tasks.add(pending)
        new = Notebook.create(tmp_path, 'Replacement Notebook')
        window.show_notebook(new)
        window._retirement_timer.stop()
        window._drain_retired_resources()
        assert old_workspace.exists() and not old._closed
        # Other real start_task callbacks must also finish on the UI thread.
        oldpane._tasks.remove(pending)
        assert QtCore.QThreadPool.globalInstance().waitForDone(10_000)
        for _ in range(10):
            app.processEvents()
        window._drain_retired_resources()  # queue deleteLater on old panes
        assert not old._closed
        app.processEvents()               # execute deferred QObject deletes
        window._drain_retired_resources()  # now safe to close temp workspace
        assert old._closed and not old_workspace.exists()
        assert window.notebook is new
    finally:
        window.close()
        QtCore.QThreadPool.globalInstance().waitForDone(10_000)
        app.processEvents()
