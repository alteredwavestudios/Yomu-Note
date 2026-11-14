"""Guard the Montserrat resource setup without requiring a GUI display."""
import unittest
from pathlib import Path
import fetch_fonts

ROOT = Path(__file__).resolve().parents[1]


class MontserratBundleTests(unittest.TestCase):
    def test_downloads_regular_and_italic_from_official_repo(self):
        montserrat = [(remote, local) for family, remote, local in fetch_fonts.FONT_FILES
                      if family == 'montserrat']
        self.assertEqual(montserrat, [
            ('Montserrat%5Bwght%5D.ttf', 'Montserrat-wght.ttf'),
            ('Montserrat-Italic%5Bwght%5D.ttf', 'Montserrat-Italic-wght.ttf'),
        ])
        self.assertIn('google/fonts/main/ofl/', fetch_fonts.BASE)

    def test_ui_font_prefers_montserrat_without_forcing_notes(self):
        start_code = (ROOT / 'main.py').read_text(encoding='utf-8')
        self.assertIn("if 'Montserrat' in families:", start_code)
        self.assertIn("app.setFont(QFont('Montserrat', 11))", start_code)
        editor_code = (ROOT / 'yomunote' / 'editor.py').read_text(encoding='utf-8')
        self.assertIn('document().setDefaultFont(base_font)', editor_code)

    def test_all_three_build_scripts_fetch_and_bundle_assets(self):
        for script in ['build-windows.ps1', 'build-mac.command', 'build-linux.sh']:
            content = (ROOT / script).read_text(encoding='utf-8')
            with self.subTest(script=script):
                self.assertIn('fetch_fonts.py', content)
                self.assertIn('assets', content)


if __name__ == '__main__':
    unittest.main()
