"""Optional real-Qt tests for v0.7.1a reading progress / checkbox colours.

Run on Windows with PySide6 to catch C++ Qt lifetime faults.  The pure-Python
suite cannot exercise native QApplication widget ownership or rendering.
"""
from __future__ import annotations

import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
pytest.importorskip('PySide6')
from shiboken6 import isValid
from PySide6.QtCore import Qt, QSettings
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication

from yomunote import window as window_module
from yomunote.page_groups import group_node, page_node
from yomunote.page_groups_ui import PageGroupsTree
from yomunote.window import MainWindow, THEMES, application_palette, stylesheet


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


def test_status_widgets_survive_read_checkbox_undo_and_tab_creation(app, monkeypatch, tmp_path):
    # Isolate settings and the notebook from the user's existing files.
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'settings'))
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path / 'data'))
    monkeypatch.setattr(window_module.Path, 'home', classmethod(lambda _cls: tmp_path))
    # Windows QSettings normally uses the registry, so redirect it to a
    # temporary INI file rather than touching any real user preferences.
    monkeypatch.setattr(window_module, 'QSettings',
                        lambda *args, **kwargs: QSettings(
                            str(tmp_path / 'preferences.ini'),
                            QSettings.Format.IniFormat))
    window = MainWindow()
    try:
        label = window._notebook_progress_label
        bar = window._notebook_progress_bar
        assert isValid(label) and isValid(bar)
        assert label.parentWidget().parentWidget() is window.header
        assert bar.parentWidget().parentWidget() is window.header

        pane = window.active()
        pane.add_blank()
        page_id = pane.project.pages[-1]['id']
        app.processEvents()
        item = pane.group_tree.find_item('page', page_id)
        assert item is not None
        item.setCheckState(0, Qt.CheckState.Checked)
        app.processEvents()  # the existing handler uses QTimer.singleShot(0)
        assert page_id in pane.project.read_page_ids
        assert bar.value() == 10_000
        assert '1/1' in label.text()

        pane.history.undo()
        app.processEvents()
        assert page_id not in pane.project.read_page_ids
        assert bar.value() == 0
        pane.history.redo()
        app.processEvents()
        assert bar.value() == 10_000

        class NonInteractiveTabName:
            @staticmethod
            def getText(*args, **kwargs):
                return 'New Reading Tab', True
        monkeypatch.setattr(window_module, 'QInputDialog', NonInteractiveTabName)
        window.add_tab()
        app.processEvents()
        assert window.tabs.count() == 2
        assert label is window._notebook_progress_label
        assert isValid(label) and isValid(bar)
        assert '1/1' in label.text()
        window.tabs.setCurrentIndex(0)
        app.processEvents()
        assert isValid(label) and isValid(bar)
    finally:
        window.close()
        app.processEvents()


@pytest.mark.parametrize('theme', list(THEMES))
def test_read_checkboxes_repaint_in_each_light_and_dark_theme(app, theme):
    colours = THEMES[theme]
    app.setPalette(application_palette(colours))
    app.setStyleSheet(stylesheet(colours))
    group = group_node('Course', [page_node('a'), page_node('b')])
    tree = PageGroupsTree()
    tree.set_accent(colours['accent'])
    try:
        tree.load_tree([group], [{'id': 'a', 'title': 'Slide 1'},
                                 {'id': 'b', 'title': 'Slide 2'}], 'a', ['a'])
        tree.resize(420, 280)
        tree.show()
        app.processEvents()
        assert tree.find_item('group', group['id']).checkState(0) == Qt.CheckState.PartiallyChecked
        assert tree.find_item('page', 'a').checkState(0) == Qt.CheckState.Checked
        assert tree.find_item('page', 'b').checkState(0) == Qt.CheckState.Unchecked
        assert tree.itemDelegate().accent.name() == colours['accent']
        assert tree.palette().color(QPalette.ColorRole.Base).name() == colours['paper']
        # Exercise the actual Qt delegate for group, page, partial and full
        # checkboxes; painting must not emit read/unread changes.
        received = []
        tree.readToggled.connect(lambda *args: received.append(args))
        assert not tree.viewport().grab().isNull()
        assert received == []
    finally:
        tree.close()
