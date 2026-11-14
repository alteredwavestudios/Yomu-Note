"""Offline OCR discovery and packaging regression tests; no Qt required."""
from pathlib import Path
from unittest import mock
import os
import sys
import tempfile
import unittest
from yomunote import ocr_runtime

class OCRBundleTests(unittest.TestCase):
    def test_bundled_engine_precedes_system_and_needs_english_model(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root) / 'ocr'
            directory.mkdir()
            binary = directory / ('tesseract.exe' if os.name == 'nt' else 'tesseract')
            binary.write_bytes(b'dummy')
            (directory / 'tessdata').mkdir()
            (directory / 'tessdata' / 'eng.traineddata').write_bytes(b'dummy')
            with mock.patch.object(sys, 'frozen', True, create=True), mock.patch.object(sys, '_MEIPASS', root, create=True):
                self.assertEqual(ocr_runtime.find_tesseract(), str(binary))
                self.assertEqual(ocr_runtime.tesseract_data_args(str(binary)),
                                 ['--tessdata-dir', str(directory / 'tessdata')])
                (directory / 'tessdata' / 'eng.traineddata').unlink()
                self.assertNotEqual(ocr_runtime.find_tesseract(), str(binary))

    def test_source_environment_uses_system_when_no_bundle(self):
        with mock.patch.object(sys, 'frozen', False, create=True):
            self.assertEqual(ocr_runtime.tesseract_data_args('/no/engine'), [])

    def test_bundle_verifier_rejects_missing_runtime(self):
        import importlib.util
        verifier = Path(__file__).resolve().parents[1] / 'ocr_packaging' / 'verify_ocr_bundle.py'
        spec = importlib.util.spec_from_file_location('yomu_ocr_verifier', verifier)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(RuntimeError):
                module.verify_bundle(Path(folder), 'windows')
            with self.assertRaises(RuntimeError):
                module.verify_bundle(Path(folder), 'macos')

if __name__ == '__main__':
    unittest.main()
