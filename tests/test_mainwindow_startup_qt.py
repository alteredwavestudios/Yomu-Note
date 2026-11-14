"""Offscreen startup/re-theme smoke test (runs only when PySide6 is installed)."""
from pathlib import Path
import pytest
pytest.importorskip('PySide6')
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
from yomunote.window import MainWindow, THEMES


def test_window_initialises_and_can_retheme(monkeypatch, tmp_path):
    # HOME/XDG_CONFIG_HOME are not enough on Windows: QSettings normally
    # reads the registry, and Path.home() normally uses USERPROFILE.
    # Isolate BOTH so tests never reopen or change a real study notebook.
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.setenv('USERPROFILE', str(tmp_path))
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'cfg'))
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path / 'data'))
    monkeypatch.setattr(Path, 'home', classmethod(lambda cls: tmp_path))

    settings_dir = tmp_path / 'cfg'
    settings_dir.mkdir()

    def isolated_settings(_organisation, application):
        # MainWindow's two preference stores get disposable INI files on
        # every platform instead of accessing Windows registry or live prefs.
        return QSettings(str(settings_dir / f'{application}.ini'),
                         QSettings.Format.IniFormat)

    monkeypatch.setattr('yomunote.window.QSettings', isolated_settings)
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    try:
        assert window.notebook is not None
        assert window.notebook.path.is_relative_to(tmp_path)
        assert window.tabs.count() == 1  # Fresh disposable notebook.
        for theme in ('washi', 'indigo', 'matcha'):
            window.set_theme(theme)
            assert window.current_palette == THEMES[theme]
        assert window.active() is not None
    finally:
        window.close()
        app.processEvents()
