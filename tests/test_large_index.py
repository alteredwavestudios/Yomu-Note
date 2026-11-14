"""Large-PDF smoke test: indexing many pages must not rasterize them."""
import tempfile
import unittest
from pathlib import Path
from yomunote.project import Project
from yomunote.importers import import_document


class LazyPageTests(unittest.TestCase):
    def test_hundred_pages_are_only_metadata(self):
        # ReportLab is optional and only used for this stress smoke test.
        try:
            from reportlab.pdfgen import canvas
        except ImportError:
            self.skipTest('Optional reportlab is unavailable')
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root/'big.pdf'
            pdf = canvas.Canvas(str(source), pagesize=(600, 800))
            for i in range(100):
                pdf.drawString(80, 700, f'Page {i+1}')
                pdf.showPage()
            pdf.save()
            project = Project.create(root, 'Stress')
            pages = import_document(project, source)
            self.assertEqual(len(pages), 100)
            self.assertEqual(list((project.path/'cache').rglob('*.jpg')), [])
            self.assertEqual(list((project.path/'pages').rglob('*.png')), [])
            project.pages.extend(pages)
            project.save()
            self.assertLess((project.path/'project.json').stat().st_size, 500_000)


if __name__ == '__main__':
    unittest.main()
