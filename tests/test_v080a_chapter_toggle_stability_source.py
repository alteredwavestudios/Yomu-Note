"""Source-level guard that runs even without Qt installed."""
import ast
from pathlib import Path


def test_chapter_item_change_never_rebuilds_or_reloads_preview():
    path = Path(__file__).resolve().parents[1] / 'yomunote' / 'import_review_dialog.py'
    tree = ast.parse(path.read_text(encoding='utf-8'))
    review_class = next(n for n in tree.body if isinstance(n, ast.ClassDef)
                        and n.name == 'SmartImportReviewDialog')
    methods = {m.name: m for m in review_class.body
               if isinstance(m, ast.FunctionDef)}
    for name in ('_item_changed', '_toggle_all_chapters', '_title_changed'):
        names = [n.func.attr for n in ast.walk(methods[name])
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)]
        assert '_rebuild' not in names
        assert '_page_moved' not in names
    body = path.read_text()
    assert 'self.tree.blockSignals(True)' in body
    assert 'self._tree_section_items = []' in body
    assert 'self._sync_chapter_checkboxes()' in body


def test_app_version_and_installer_agree():
    root = Path(__file__).resolve().parents[1]
    from yomunote import __version__
    installer = (root / 'YomuNote_v050_Installer.iss').read_text()
    assert f'#define MyAppVersion "{__version__}"' in installer
    # Numeric version metadata is validated by test_v082_release_metadata.py.
    assert f'OutputBaseFilename=YomuNote_Setup_v{__version__}' in installer
