"""Native Qt regression: dirty-only once-per-minute autosave scheduling."""
import pytest

qt_core = pytest.importorskip('PySide6.QtCore')
qt_widgets = pytest.importorskip('PySide6.QtWidgets')

from yomunote.project import Project
from yomunote.window import ProjectPane


def test_first_dirty_edit_schedules_one_minute_without_debouncing(tmp_path):
    app = qt_widgets.QApplication.instance() or qt_widgets.QApplication([])
    settings = qt_core.QSettings(str(tmp_path / 'prefs.ini'), qt_core.QSettings.Format.IniFormat)
    pane = ProjectPane(Project.create(tmp_path, 'Autosave'), settings)
    try:
        assert pane._save_timer.interval() == 60_000
        assert pane._save_timer.isSingleShot()
        assert not pane._save_timer.isActive()
        pane.schedule_save()
        assert pane._dirty and pane._save_timer.isActive()
        initial_id = pane._save_timer.timerId()
        pane.schedule_save()
        assert pane._save_timer.timerId() == initial_id
        pane.save()
        assert not pane._dirty
        assert not pane._save_timer.isActive()
        pane.schedule_save()
        assert pane._save_timer.isActive()
    finally:
        pane._save_timer.stop()
        pane._closed = True
        pane.close()
        app.processEvents()


def test_background_save_is_not_attempted_when_clean(tmp_path, monkeypatch):
    app = qt_widgets.QApplication.instance() or qt_widgets.QApplication([])
    settings = qt_core.QSettings(str(tmp_path / 'prefs.ini'), qt_core.QSettings.Format.IniFormat)
    pane = ProjectPane(Project.create(tmp_path, 'CleanAutosave'), settings)
    try:
        calls = []
        monkeypatch.setattr(pane, 'save', lambda: calls.append(1))
        pane._autosave()
        assert calls == []
        pane.schedule_save()
        pane._autosave()
        assert calls == [1]
    finally:
        pane._save_timer.stop()
        pane._closed = True
        pane.close()
        app.processEvents()
