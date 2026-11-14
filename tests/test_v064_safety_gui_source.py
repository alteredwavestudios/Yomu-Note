"""Source checks for UI wiring when PySide6 cannot be loaded in CI."""
from pathlib import Path

CODE = (Path(__file__).resolve().parents[1] / 'yomunote' / 'window.py').read_text()


def test_ocr_switches_keep_completed_results():
    assert 'self.leave_ocr_mode(cancel_running=False)' in CODE
    assert 'self._ocr_results_by_page[page_id] = result' in CODE
    assert 'self._ocr_last_page_id = page_id' in CODE
    assert 'if not still_showing_source:' in CODE


def test_user_can_recover_into_separate_notebook_copy():
    assert 'Notebook.recover_copy(Path(path))' in CODE
    assert 'The original will not be changed.' in CODE
    assert 'Previous notebook could not open' in CODE


def test_clean_copy_menu_uses_a_background_worker():
    assert "'Export Clean Notebook for Sharing…'" in CODE
    assert 'Notebook.create_clean_share_copy(source, target)' in CODE
    assert 'start_task(self, worker, finished, priority=1)' in CODE
