"""Protect real study notebooks and preferences during MainWindow GUI tests.

Every test that imports MainWindow gets a disposable home and an INI-backed
QSettings store, including on Windows (where QSettings normally uses registry).
This also makes `python -m pytest` safe without the optional audit runner.
"""
from __future__ import annotations

from pathlib import Path
import re

import pytest


@pytest.fixture(autouse=True)
def isolate_mainwindow_user_state(request):
    """Avoid opening or modifying a user's real notebook in GUI smoke tests."""
    namespace = vars(request.module)
    mainwindow_test = any(
        (getattr(value, '__name__', None) == 'MainWindow'
         and getattr(value, '__module__', None) == 'yomunote.window')
        or getattr(value, '__name__', None) == 'yomunote.window'
        for value in namespace.values()
    )
    if not mainwindow_test:
        return

    # Import only for tests that already imported the Qt MainWindow. Pure
    # Python tests must remain runnable without PySide6 installed.
    from PySide6.QtCore import QSettings
    from yomunote import window as window_module

    tmp_path = request.getfixturevalue('tmp_path')
    monkeypatch = request.getfixturevalue('monkeypatch')
    home = tmp_path / 'test-home'
    home.mkdir(exist_ok=True)
    prefs = tmp_path / 'test-preferences'
    prefs.mkdir(exist_ok=True)

    monkeypatch.setenv('HOME', str(home))
    monkeypatch.setenv('USERPROFILE', str(home))
    monkeypatch.setenv('APPDATA', str(tmp_path / 'appdata'))
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'localappdata'))
    monkeypatch.setenv('XDG_CONFIG_HOME', str(prefs))
    monkeypatch.setattr(Path, 'home', classmethod(lambda cls: home))

    def private_qsettings(*args, **kwargs):
        if len(args) == 2 and not kwargs and all(isinstance(x, str) for x in args):
            name = '--'.join(re.sub(r'[^A-Za-z0-9_-]', '_', x) for x in args)
            return QSettings(str(prefs / f'{name}.ini'), QSettings.Format.IniFormat)
        return QSettings(*args, **kwargs)

    monkeypatch.setattr(window_module, 'QSettings', private_qsettings)
