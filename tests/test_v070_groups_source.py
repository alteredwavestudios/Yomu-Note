"""Static Qt integration checks run without PySide6."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WINDOW = (ROOT/'yomunote/window.py').read_text(encoding='utf8')
UI = (ROOT/'yomunote/page_groups_ui.py').read_text(encoding='utf8')


def test_hierarchy_persists_and_fallback_view_remains():
    assert 'self.nav_views.addWidget(self.pages_list)' in WINDOW
    assert 'self.nav_views.addWidget(self.group_tree)' in WINDOW
    assert 'self.group_tree.structureChanged.connect(self._group_tree_dropped)' in WINDOW
    assert 'self.group_tree.pageActivated.connect(self.select_page_id)' in WINDOW


def test_groups_do_not_interfere_with_page_preview_or_notes():
    section = WINDOW.split('    def _commit_group_edit(', 1)[1].split('\n    def ', 1)[0]
    assert 'self.history.perform(CallbackAction(' in section
    assert 'validate_group_tree(tree, order)' in section
    assert 'self.project.pages' in section
    assert 'self.notes.editor.setHtml' not in section


def test_no_duplicated_qt_drop_handler():
    tree = ast.parse(UI)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef)
               and n.name=='PageGroupsTree')
    methods = [n.name for n in cls.body if isinstance(n, ast.FunctionDef)]
    for name in ('dropEvent', 'startDrag', 'keyPressEvent', 'load_tree'):
        assert methods.count(name) == 1


def test_group_deletion_and_thumbnail_reorder_restore_snapshots():
    assert 'remove_group_and_pages(' in WINDOW
    assert 'before_tree, before_pages' in WINDOW
    assert 'previous_tree = copy.deepcopy(self.project.page_groups)' in WINDOW
