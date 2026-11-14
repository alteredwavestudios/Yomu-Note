"""Pure-Python tests for platform-specific display labels and font setup."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from yomunote import platform_shortcuts as ps
import fetch_fonts


class PlatformShortcutTests(unittest.TestCase):
    def test_mac_labels_match_google_docs(self):
        with patch.object(ps, 'IS_MAC', True):
            self.assertEqual(ps.docs_shortcut('larger_font'), '⌘⇧.')
            self.assertEqual(ps.docs_shortcut('indent'), '⌘]')
            self.assertEqual(ps.docs_shortcut('find'), '⌘F')
            self.assertEqual(ps.docs_shortcut('strike'), '⌘⇧X')

    def test_windows_and_linux_labels_match_google_docs(self):
        with patch.object(ps, 'IS_MAC', False):
            self.assertEqual(ps.docs_shortcut('larger_font'), 'Ctrl+Shift+.')
            self.assertEqual(ps.docs_shortcut('indent'), 'Ctrl+]')
            self.assertEqual(ps.docs_shortcut('bulleted'), 'Ctrl+Shift+8')
            self.assertEqual(ps.docs_shortcut('find'), 'Ctrl+F')
            self.assertEqual(ps.docs_shortcut('strike'), 'Alt+Shift+5')

    def test_font_installer_rejects_nonfont_payload(self):
        """A bad download must not leave behind a usable-looking file."""
        class FakeResponse:
            def __enter__(self): return self
            def __exit__(self, *_): return None
            def read(self, _max_bytes): return b'NOT A REAL FONT'
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'bad.ttf'
            with patch.object(fetch_fonts, 'urlopen', return_value=FakeResponse()):
                with self.assertRaisesRegex(ValueError, 'sfnt font'):
                    fetch_fonts.download_file('https://example.test/bad.ttf', target, expect_font=True)
            self.assertFalse(target.exists())


if __name__ == '__main__':
    unittest.main()


def test_mac_zoom_in_plus_key_shows_plus_not_just_command():
    with patch.object(ps, 'IS_MAC', True):
        assert ps.docs_shortcut('notes_zoom_in') == '⌘+'
        assert ps.docs_shortcut('notes_zoom_out') == '⌘-'
