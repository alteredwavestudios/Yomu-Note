"""Catch accidental UI/import regressions even without Qt installed."""
import ast
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
WINDOW = (ROOT / 'yomunote/window.py').read_text(encoding='utf8')
UI = (ROOT / 'yomunote/page_groups_ui.py').read_text(encoding='utf8')
TREE = ast.parse(UI)


def method(name):
    klass = next(node for node in TREE.body if isinstance(node, ast.ClassDef)
                 and node.name == 'PageGroupsTree')
    fn = next(node for node in klass.body if isinstance(node, ast.FunctionDef)
              and node.name == name)
    return ast.get_source_segment(UI, fn)


def test_import_has_explicit_root_and_group_destinations():
    # v0.7.1 moved the planner into a testable, Qt-free module.
    planning = (ROOT / 'yomunote/import_planning.py').read_text(encoding='utf8')
    assert 'move_pages_to_root(' in planning
    assert 'move_pages_to_group(' in planning
    assert 'plan_import(' in WINDOW
    assert 'group_id=group_id' in WINDOW
    assert "self._navigator_view == 'groups'" in WINDOW
    assert 'self.group_tree.selected_group_id()' in method('selected_group_id') or 'self.group_tree.selected_group_id()' in WINDOW


def test_active_page_independent_of_user_selection():
    code = method('mark_active')
    assert 'ROLE_ACTIVE' in code
    assert 'ROLE_ACTIVE_ANCESTOR' in code
    assert 'clearSelection()' not in code
    assert 'setCurrentItem(' not in code
    assert 'self.scrollToItem(visible)' in code


def test_thumbnail_resources_stay_bounded():
    assert 'self.setUniformRowHeights(False)' in UI
    assert "QFont('Montserrat', 9" in UI
    assert 'QFont.Weight.Bold' in UI
    assert 'self._group_thumb_pending' in WINDOW
    assert 'self.group_tree.discard_other_thumbnails(visible)' in WINDOW
    assert 'self.group_tree.visible_page_ids(limit=THUMB_LIMIT)' in WINDOW
    assert 'self.group_tree.set_page_thumbnail(' in WINDOW
