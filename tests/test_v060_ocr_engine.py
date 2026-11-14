"""Stage 4 source OCR tests. No Qt display is required."""
from __future__ import annotations
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from PIL import Image, ImageDraw, ImageFont

from yomunote.ocr_engine import (
    OCRCancelled, clean_ocr_text, find_tesseract, installed_languages,
    normalise_rectangle, reading_order, recognise_regions, render_source_region,
)


class Source:
    def __init__(self, folder):
        self.folder = Path(folder)

    def asset_path(self, relative):
        return self.folder / relative


class RegionTests(unittest.TestCase):
    def test_reverse_drag_and_clamp(self):
        for actual, expected in zip(normalise_rectangle((.9, .7, -.3, -.2)), (.6, .5, .3, .2)):
            self.assertAlmostEqual(actual, expected)
        for actual, expected in zip(normalise_rectangle((-.1, -.1, .4, .4)), (0., 0., .3, .3)):
            self.assertAlmostEqual(actual, expected)
        with self.assertRaises(ValueError):
            normalise_rectangle((.5, .5, 0, 0))

    def test_top_to_bottom_left_to_right_and_row_alignment(self):
        first = (.04, .08, .5, .1)
        second = (.55, .093, .4, .1)
        last = (.04, .33, .8, .12)
        for actual, expected in zip(reading_order([last, second, first]), [first, second, last]):
            for observed, target in zip(actual, expected):
                self.assertAlmostEqual(observed, target)

    def test_wrapped_text_and_preserved_paragraphs(self):
        value = 'A text wraps at the\nedge of one page.\n\nAnother paragraph\nstarts here.\n'
        self.assertEqual(clean_ocr_text(value), 'A text wraps at the edge of one page.\n\nAnother paragraph starts here.')
        self.assertEqual(clean_ocr_text(value, False), value.strip())
        self.assertEqual(clean_ocr_text('- One\n- Two'), '- One\n- Two')

    def test_missing_page_refuses_ocr(self):
        with TemporaryDirectory() as tmp:
            project = Source(tmp)
            with self.assertRaises(ValueError):
                recognise_regions(project, {'kind': 'blank', 'render_source': None}, [(0,0,1,1)])

    def test_cancellation_before_start(self):
        if not find_tesseract():
            self.skipTest('Tesseract unavailable')
        with TemporaryDirectory() as tmp:
            file = Path(tmp) / 'original.png'
            Image.new('RGB', (500, 200), 'white').save(file)
            event = threading.Event()
            event.set()
            with self.assertRaises(OCRCancelled):
                recognise_regions(Source(tmp), {'kind': 'image', 'render_source':'original.png'},
                                  [(0,0,1,1)], cancel=event)

    def test_real_image_ocr_from_selected_region(self):
        if not find_tesseract():
            self.skipTest('Tesseract unavailable')
        if 'eng' not in installed_languages(find_tesseract()):
            self.skipTest('Tesseract English data unavailable')
        with TemporaryDirectory() as tmp:
            file = Path(tmp) / 'original.png'
            img = Image.new('RGB', (900, 560), 'white')
            draw = ImageDraw.Draw(img)
            fonts = list(Path('/usr/share/fonts').rglob('Go-Bold.ttf'))
            font = ImageFont.truetype(str(fonts[0]), 36) if fonts else ImageFont.load_default()
            draw.text((70, 70), 'FIRST PARAGRAPH', font=font, fill='black')
            draw.text((70, 330), 'SECOND PARAGRAPH', font=font, fill='black')
            img.save(file)
            # Drawn in reverse order. The clipboard still reads top-down.
            result = recognise_regions(Source(tmp), {'kind':'image','render_source':'original.png'},
                    [(0.05, .54, .7, .16), (0.05, .08, .7, .16)])
            self.assertIn('FIRST', result)
            self.assertIn('SECOND', result)
            self.assertLess(result.index('FIRST'), result.index('SECOND'))

    def test_pdfium_clipped_source_at_300_dpi(self):
        try:
            from reportlab.pdfgen import canvas
        except ImportError:
            self.skipTest('PDF creation fixture unavailable')
        with TemporaryDirectory() as tmp:
            file = Path(tmp) / 'sample.pdf'
            pdf = canvas.Canvas(str(file), pagesize=(612,792))
            pdf.setFont('Helvetica-Bold', 22)
            pdf.drawString(70, 690, 'UNIQUE WORDS')
            pdf.drawString(70, 490, 'LOWER BLOCK')
            pdf.save()
            selected = (.08, .08, .76, .13)
            image = render_source_region(file, 'pdf', 1, selected, 300)
            self.assertGreater(image.width, 800)
            self.assertLess(image.width, 2300)
            self.assertGreater(image.height, 300)
            if find_tesseract() and 'eng' in installed_languages(find_tesseract()):
                result = recognise_regions(Source(tmp), {'kind':'pdf','render_source':'sample.pdf','source_page':1}, [selected])
                self.assertIn('UNIQUE WORDS', result)


if __name__ == '__main__':
    unittest.main()
