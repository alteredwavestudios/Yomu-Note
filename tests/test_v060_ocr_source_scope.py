"""Validate Stage 4 wiring even without PySide6 installed."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / 'yomunote/window.py').read_text(encoding='utf8')
ENGINE = (ROOT / 'yomunote/ocr_engine.py').read_text(encoding='utf8')
TREE = ast.parse(SOURCE)


def method(cls, name):
    node = next(n for n in TREE.body if isinstance(n, ast.ClassDef) and n.name == cls)
    member = next(n for n in node.body if isinstance(n, ast.FunctionDef) and n.name == name)
    return ast.get_source_segment(SOURCE, member)


def test_transient_canvas_regions_and_scroll_stays_standard():
    assert "'ocr'" in method('ImageCanvas', 'set_annotation_tool')
    assert 'self.ocrRegionsChanged.emit(' in method('ImageCanvas', '_ocr_finish_drag')
    assert 'self.verticalScrollBar()' in method('ImageCanvas', '_ocr_autoscroll')
    assert 'self.horizontalScrollBar()' in method('ImageCanvas', '_ocr_autoscroll')
    assert 'super().wheelEvent(event)' in method('ImageCanvas', 'wheelEvent')
    assert 'self._ocr_regions' in method('ImageCanvas', 'ocr_regions')
    assert 'self.clear_ocr_regions()' in method('ImageCanvas', 'show_image')
    assert 'self.clear_ocr_regions()' in method('ImageCanvas', 'set_annotation_tool')
    assert 'self._ocr_mask' in method('ImageCanvas', '_refresh_ocr_overlay')


def test_high_dpi_ocr_is_not_preview_raster_and_is_cancellable():
    assert 'render_source_region(source, kind, number, region, dpi)' in ENGINE
    assert 'page.render(scale=scale, crop=crop, draw_annots=False)' in ENGINE
    assert 'MAX_REGION_PIXELS' in ENGINE
    assert 'effective_dpi' in ENGINE
    assert 'OCRCancelled' in ENGINE
    assert 'process.kill()' in ENGINE
    assert 'subprocess.TimeoutExpired' in ENGINE
    assert 'image_for_page' not in ENGINE
    assert 'from PySide6' not in ENGINE and 'import QPixmap' not in ENGINE


def test_clipboard_and_review_do_not_edit_notebook():
    fn = method('ProjectPane', 'recognise_ocr_selection')
    assert 'QApplication.clipboard().setText(result)' in fn
    assert 'self.show_ocr_review()' in fn
    assert 'self._ocr_cancel_event' in fn
    assert 'start_task(self, worker, done' in fn
    assert 'self._ocr_entry_action.setEnabled(False)' in fn
    review = method('ProjectPane', 'show_ocr_review')
    assert 'QPlainTextEdit' in review
    assert 'QApplication.clipboard().setText(self._ocr_last_text)' in review
    assert 'self.notes.editor' not in review
    assert 'self.project.annotations' not in review


def test_pen_thickness_is_contextual_and_saved_as_preference():
    setup = method('ProjectPane', '__init__')
    assert 'pen_size_widget' in setup
    assert 'self.pen_size_widget.hide()' in setup
    assert "self.pen_size_widget.setVisible(tool == 'pen')" in method('ProjectPane', 'set_annotation_mode')
    assert "self.canvas.tool_styles['pen']['width']" in method('ProjectPane', '_set_pen_size')
    assert "self.settings.setValue('annotationPenWidth'" in method('ProjectPane', '_set_pen_size')
