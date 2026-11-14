"""No-Qt tests: page group integrity, old notebooks and reversible edits."""
import copy
import json
import tempfile
from pathlib import Path

import pytest
from yomunote import page_groups as g
from yomunote.project import Project
from yomunote.notebook import Notebook
from yomunote.history import UnifiedHistory, CallbackAction


def sample():
    return g.flat_tree(['a', 'b', 'c', 'd', 'e'])


def test_groups_are_ids_not_copied_pages():
    tree, gid = g.group_pages(sample(), ['b', 'c'], 'Reading')
    g.validate(tree, ['a', 'b', 'c', 'd', 'e'])
    assert g.flatten(tree) == ['a', 'b', 'c', 'd', 'e']
    assert g.get_group(tree, gid)['children'] == [g.page_node('b'), g.page_node('c')]
    assert not any('file' in str(node) for node in tree)


def test_nested_group_rename_and_collapse_preserve_order():
    root, first = g.group_pages(sample(), ['b', 'c'], 'Book')
    root, sub = g.add_group(root, 'Chapter', parent_id=first)
    root = g.rename_group(root, sub, 'Chapter One')
    root = g.set_collapsed(root, first, True)
    assert g.get_group(root, first)['collapsed']
    assert g.get_group(root, sub)['name'] == 'Chapter One'
    assert g.flatten(root) == ['a', 'b', 'c', 'd', 'e']


def test_ungroup_keeps_every_page_and_nested_folder():
    tree, gid = g.group_pages(sample(), ['b', 'c'], 'Book')
    tree, sub = g.add_group(tree, 'Empty chapter', parent_id=gid)
    result = g.ungroup(tree, gid)
    assert g.flatten(result) == ['a', 'b', 'c', 'd', 'e']
    assert g.get_group(result, sub) is not None
    assert g.get_group(result, gid) is None


def test_delete_group_reports_only_its_page_ids():
    tree, gid = g.group_pages(sample(), ['b', 'c'], 'Week 1')
    after, removed = g.remove_group_and_pages(tree, gid)
    assert removed == ['b', 'c']
    assert g.flatten(after) == ['a', 'd', 'e']
    g.validate(after, ['a', 'd', 'e'])


def test_noncontiguous_and_cross_parent_selection_is_rejected():
    with pytest.raises(ValueError, match='adjacent'):
        g.group_pages(sample(), ['a', 'c'], 'Nope')
    tree, gid = g.group_pages(sample(), ['b', 'c'], 'Book')
    with pytest.raises(ValueError, match='parent'):
        g.group_pages(tree, ['a', 'b'], 'Nope')
    assert g.flatten(tree) == ['a', 'b', 'c', 'd', 'e']


def test_move_pages_into_group_changes_only_reading_order():
    tree, gid = g.group_pages(sample(), ['b', 'c'], 'Book')
    result = g.move_pages_to_group(tree, ['a', 'e'], gid)
    assert g.flatten(result) == ['b', 'c', 'a', 'e', 'd']
    g.validate(result, g.flatten(result))
    assert len(g.flatten(result)) == 5


def test_flat_legacy_move_can_split_group_without_losing_pages():
    tree, _gid = g.group_pages(sample(), ['b', 'c'], 'Week')
    order = ['b', 'a', 'd', 'c', 'e']
    next_tree = g.reconcile(tree, order)
    assert g.flatten(next_tree) == order
    g.validate(next_tree, order)
    assert len([node for node in next_tree if node['type'] == 'group']) == 2


def test_reconcile_removes_old_page_and_inserts_new_one():
    tree, gid = g.group_pages(sample(), ['b', 'c'], 'Reading')
    next_tree = g.reconcile(tree, ['a', 'b', 'new', 'c', 'e'])
    assert g.flatten(next_tree) == ['a', 'b', 'new', 'c', 'e']
    g.validate(next_tree, ['a', 'b', 'new', 'c', 'e'])
    assert g.get_group(next_tree, gid) is not None


def test_duplicate_or_missing_id_refused():
    with pytest.raises(ValueError):
        g.validate(g.flat_tree(['a', 'a']), ['a', 'b'])
    with pytest.raises(ValueError):
        g.validate(g.flat_tree(['a']), ['a', 'b'])


def test_group_undo_and_redo_restore_all_page_ids():
    original = sample()
    after, _gid = g.group_pages(original, ['b', 'c'], 'Week')
    current = [copy.deepcopy(original)]
    history = UnifiedHistory()
    history.perform(CallbackAction('Group',
        lambda: current.__setitem__(0, copy.deepcopy(original)),
        lambda: current.__setitem__(0, copy.deepcopy(after))))
    assert g.flatten(current[0]) == ['a', 'b', 'c', 'd', 'e']
    history.undo()
    assert current[0] == original
    history.redo()
    assert current[0] == after


def test_project_manifest_round_trip_and_legacy_fallback(tmp_path):
    project = Project.create(tmp_path, 'Lecture')
    project.pages = [{'id': 'a', 'title': 'A'}, {'id': 'b', 'title': 'B'}]
    project.page_groups, _gid = g.group_pages(g.flat_tree(['a', 'b']), ['a', 'b'], 'Chapter')
    project.save()
    reopened = Project.load(project.path)
    assert reopened.page_groups == project.page_groups
    raw_path = project.path / 'project.json'
    raw = json.loads(raw_path.read_text())
    del raw['page_groups']
    raw_path.write_text(json.dumps(raw))
    legacy = Project.load(project.path)
    assert legacy.page_groups == g.flat_tree(['a', 'b'])


def test_corrupt_hierarchy_is_rejected_but_cosmetic_recovery_can_reset(tmp_path):
    project = Project.create(tmp_path, 'Lecture')
    project.pages = [{'id': 'a', 'title': 'A'}]
    project.save()
    path = project.path / 'project.json'
    payload = json.loads(path.read_text())
    payload['page_groups'] = [{'type': 'page', 'page_id': 'secret-missing'}]
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError):
        Project.load(project.path)
    warnings = []
    recovered = Project.load(project.path, recover_cosmetic=True,
                             recovery_warnings=warnings)
    assert recovered.page_groups == g.flat_tree(['a'])
    assert warnings


def test_notebook_archive_roundtrip_with_nested_groups(tmp_path):
    nb = Notebook.create(tmp_path, 'Group archive')
    path = nb.path
    project = nb.project(nb.tabs[0]['id'])
    project.pages = [
        {'id': 'aa', 'title': 'First'},
        {'id': 'bb', 'title': 'Second'},
    ]
    project.page_groups, gid = g.group_pages(
        g.flat_tree(['aa', 'bb']), ['aa', 'bb'], 'Book')
    project.page_groups = g.set_collapsed(project.page_groups, gid, True)
    project.save()
    nb.save()
    nb.close()
    loaded = Notebook.load(path)
    actual = loaded.project(loaded.tabs[0]['id'])
    assert actual.page_groups == project.page_groups
    assert [p['id'] for p in actual.pages] == ['aa', 'bb']
    loaded.close()
