"""Run offscreen with PySide6 on Windows to validate reported regressions."""
import pytest
pytest.importorskip('PySide6.QtWidgets')
from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor, QKeySequence
from PySide6.QtWidgets import QApplication
from yomunote.editor import NotesEditor
from yomunote.window import MainWindow
from yomunote.notebook import Notebook


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


def test_ctrl_k_is_page_link_not_web_link(app):
    editor = NotesEditor()
    try:
        shortcuts = {s.key().toString(QKeySequence.SequenceFormat.PortableText): s
                     for s in editor._shortcuts}
        assert 'Ctrl+K' in shortcuts
        assert 'Ctrl+Alt+K' in shortcuts
        hits = []
        editor.pageLinkRequested.connect(lambda: hits.append('page'))
        shortcuts['Ctrl+K'].activated.emit()
        assert hits == ['page']
    finally:
        editor.close()


def test_blank_paragraph_grows_and_shrinks_without_fixed_height(app):
    editor = NotesEditor()
    try:
        editor.set_html('<p></p>')
        editor.resize(600, 500)
        editor.show()
        app.processEvents()
        c = editor.editor.textCursor()
        c.movePosition(QTextCursor.MoveOperation.Start)
        editor.editor.setTextCursor(c)
        editor.set_font_size_immediately(12)
        app.processEvents()
        small = editor.editor.document().firstBlock().layout().boundingRect().height()
        editor.set_font_size_immediately(40)
        app.processEvents()
        large = editor.editor.document().firstBlock().layout().boundingRect().height()
        editor.set_font_size_immediately(16)
        app.processEvents()
        shrunk = editor.editor.document().firstBlock().layout().boundingRect().height()
        fmt = editor.editor.document().firstBlock().blockFormat()
        from PySide6.QtGui import QTextBlockFormat
        assert fmt.lineHeightType() != QTextBlockFormat.LineHeightTypes.FixedHeight.value
        assert large > small + 8, (small, large)
        assert shrunk < large, (shrunk, large)
    finally:
        editor.close()


def test_many_adds_keep_first_pane_instance(app, tmp_path, monkeypatch):
    nb = Notebook.create(tmp_path, 'No Rebuild Test')
    window = MainWindow()
    try:
        window.show_notebook(nb)
        initial = window.tabs.widget(0)
        # Simulate accepted name input, avoid opening a modal dialog.
        from PySide6.QtWidgets import QInputDialog
        monkeypatch.setattr(QInputDialog, 'getText', lambda *a, **kw: ('Another', True))
        for i in range(6):
            window.add_tab()
        assert window.tabs.widget(0) is initial
        assert window.tabs.count() == 7
        assert window.tabs.cornerWidget().width() == 38
    finally:
        window.close()
