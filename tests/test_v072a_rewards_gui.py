"""PySide6 smoke checks for the revised notice, progress and checkbox painting.

Run on a machine with the real app dependencies. Offscreen Qt is sufficient
for signals and geometry; the user should still visually test Windows themes.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import pytest
pytest.importorskip('PySide6')
from PySide6.QtCore import Qt, QAbstractAnimation
from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtTest import QTest
from yomunote.ui import ReadingProgressBar, KawaiiNotice, FocusTimer
from yomunote.focus_logic import FOCUS_REMINDERS, BREAK_REMINDERS
from yomunote.page_groups import group_node, page_node
from yomunote.page_groups_ui import PageGroupsTree
from yomunote.window import THEMES, application_palette, stylesheet

@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


def test_progress_bar_eases_both_ways_but_only_glints_on_increases(app):
    bar = ReadingProgressBar()
    bar.resize(200, 8)
    bar.show(); app.processEvents()
    bar.set_progress(62.50)
    assert bar._target_units == 6250
    assert bar._motion.state() == QAbstractAnimation.State.Running
    assert bar._flash.state() == QAbstractAnimation.State.Running
    QTest.qWait(600)
    assert bar.value() == 6250
    bar.set_progress(12.25)
    assert bar._target_units == 1225
    assert bar._flash.state() == QAbstractAnimation.State.Stopped
    bar.set_reduced_motion(True)
    assert bar.value() == 1225
    assert bar._motion.state() == QAbstractAnimation.State.Stopped
    bar.set_progress(83.0)
    assert bar.value() == 8300
    assert bar._flash.state() == QAbstractAnimation.State.Stopped
    bar.close()


def test_kawaii_notice_is_nonblocking_and_plaintext(app):
    parent = QWidget()
    parent.resize(640, 480)
    parent.show()
    app.processEvents()
    toast = KawaiiNotice(parent)
    toast.set_palette(THEMES['washi'])
    toast.show_message('<b>Tea</b>! (ﾉ◕ヮ◕)ﾉ', reduced_motion=True)
    assert toast.textFormat() == Qt.TextFormat.PlainText
    assert toast.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    assert toast.isVisible()
    assert '<b>Tea</b>' in toast.text()
    toast._fade_out()
    assert not toast.isVisible()
    parent.close()


def test_focus_timer_emits_each_mode_message(app):
    class Settings:
        def value(self, key, default=None):
            return default
    timer = FocusTimer(Settings())
    timer.sound_enabled = False
    emitted = []
    timer.reminder.connect(emitted.append)
    for mode, expected in [('Focus', FOCUS_REMINDERS[8]),
                           ('Short break', BREAK_REMINDERS[9])]:
        timer.overdue_mode = mode
        timer.last_reminder_slot = 8 if mode == 'Focus' else 9
        timer._notify()
        assert emitted[-1] == expected
    timer.close()


@pytest.mark.parametrize('theme', [key for key in THEMES if key != 'system'])
def test_checked_and_partial_group_marks_look_different(app, theme):
    app.setPalette(application_palette(THEMES[theme]))
    app.setStyleSheet(stylesheet(THEMES[theme]))
    group = group_node('Chapter', [page_node('x'),page_node('y')])
    tree = PageGroupsTree()
    tree.set_accent(THEMES[theme]['accent'])
    tree.load_tree([group], [{'id':'x','title':'One'},{'id':'y','title':'Two'}], 'x', ['x'])
    tree.resize(440, 310); tree.show(); app.processEvents()
    assert tree.find_item('group', group['id']).checkState(0) == Qt.CheckState.PartiallyChecked
    assert tree.find_item('page','x').checkState(0) == Qt.CheckState.Checked
    assert not tree.viewport().grab().isNull()
    # Drawing and repainting must not mutate model data or send read signals.
    messages = []
    tree.readToggled.connect(lambda *args: messages.append(args))
    tree.viewport().update(); app.processEvents()
    assert not messages
    tree.close()
