"""Qt runtime checks for isolated per-tab edit histories and reading scroll."""
import pytest
pytest.importorskip('PySide6.QtWidgets')
from PySide6.QtWidgets import QApplication
from yomunote.notebook import Notebook
from yomunote.window import MainWindow

@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


def test_notes_and_page_undo_isolated_between_tabs(app, tmp_path):
    nb = Notebook.create(tmp_path, 'Per Tab History Test')
    nb.add_tab('Second')
    window = MainWindow()
    try:
        window.show_notebook(nb)
        window.tabs.setCurrentIndex(0)
        first = window.active()
        first.notes.editor.insertPlainText('Tab one')
        first.add_blank()
        first_count = first.history.action_count
        window.tabs.setCurrentIndex(1)
        second = window.active()
        assert first.history is not second.history
        assert not second.history.can_undo
        second.notes.editor.insertPlainText('Tab two')
        assert window.history is second.history
        window.undo_shared()
        assert second.notes.editor.toPlainText() == ''
        assert first.notes.editor.toPlainText() == 'Tab one'
        assert len(first.project.pages) == 1
        assert first.history.action_count == first_count
        window.tabs.setCurrentIndex(0)
        assert window.history is first.history
        window.undo_shared()
        assert len(first.project.pages) == 0
        window.undo_shared()
        assert first.notes.editor.toPlainText() == ''
        window.tabs.setCurrentIndex(1)
        window.redo_shared()
        assert second.notes.editor.toPlainText() == 'Tab two'
    finally:
        window.close()


def test_annotation_undo_separator_preserves_scrolled_reading_position(app, tmp_path):
    nb = Notebook.create(tmp_path, 'Reading Position Test')
    window = MainWindow()
    try:
        window.show_notebook(nb)
        pane = window.active()
        editor = pane.notes.editor
        editor.setPlainText('\n'.join('Paragraph %03d text' % i for i in range(350)))
        window.show()
        app.processEvents()
        scrollbar = editor.verticalScrollBar()
        assert scrollbar.maximum() > 0
        # Cursor is at the end, but reading is at the top of the notes.
        scrollbar.setValue(0)
        app.processEvents()
        pane._separate_text_commands()
        assert scrollbar.value() == 0
    finally:
        window.close()
