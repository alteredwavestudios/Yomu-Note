"""Tests runnable without Qt; PDFium/Pillow are used just like in the desktop app."""
import json
import tempfile
import unittest
from pathlib import Path
from PIL import Image
from yomunote.project import Project, FORMAT_VERSION
from yomunote.importers import import_document, image_for_page


class ProjectImportTests(unittest.TestCase):
    def test_lazy_pdf_jpeg_cache_and_version(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            images = [Image.new('RGB', (580, 760), (250-i*10, 250, 240)) for i in range(12)]
            source = base / 'twelve.pdf'
            images[0].save(source, 'PDF', save_all=True, append_images=images[1:])
            project = Project.create(base, 'Test project')
            pages = import_document(project, source)
            self.assertEqual(len(pages), 12)
            project.pages.extend(pages)
            project.save()
            self.assertEqual(json.loads((project.path/'project.json').read_text())['version'], FORMAT_VERSION)
            self.assertEqual(list((project.path/'cache/thumbs').glob('*.jpg')), [])
            self.assertEqual(list((project.path/'cache/previews').glob('*.jpg')), [])
            self.assertFalse(list((project.path/'pages').glob('*.png')))
            a = image_for_page(project, pages[0], thumbnail=True)
            b = image_for_page(project, pages[0], thumbnail=False)
            c = image_for_page(project, pages[0], thumbnail=False, high=True)
            self.assertTrue(a.exists() and b.exists() and c.exists())
            with Image.open(a) as pic: self.assertLessEqual(max(pic.size), 144)
            with Image.open(b) as pic: self.assertLessEqual(pic.width*pic.height, 12_000_000+100)
            with Image.open(c) as pic: self.assertLessEqual(pic.width*pic.height, 18_000_000+100)
            self.assertLess(b.stat().st_size, 3_000_000)
            reopened = Project.load(project.path)
            self.assertEqual(len(reopened.pages), 12)
            copied = reopened.duplicate_to(base, 'Copy')
            self.assertFalse((copied.path/'cache').exists())
            self.assertEqual(len(copied.pages), 12)

    def test_paths_and_version_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Project.create(Path(d), 'Small')
            with self.assertRaises(ValueError): p.asset_path('originals/../../private.txt')
            with self.assertRaises(ValueError): p.asset_path('/etc/hosts')
            manifest = p.path / 'project.json'
            data = json.loads(manifest.read_text())
            data['version'] = 999
            manifest.write_text(json.dumps(data))
            with self.assertRaises(ValueError): Project.load(p.path)


if __name__ == '__main__':
    unittest.main()
