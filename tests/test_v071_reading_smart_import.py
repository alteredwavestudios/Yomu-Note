"""v0.7.1: completion, safe imports, label formats and subtree moves."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest
from PIL import Image

from yomunote.import_labels import FORMATS, label_imported_pages, make_title
from yomunote.importers import import_document
from yomunote.page_groups import (
    flat_tree, flatten, group_node, move_group, validate,
)
from yomunote.project import Project
from yomunote.reading_progress import (
    group_counts, notebook_totals, percentage, set_read_status,
    validated_read_ids,
)


def group(name, *children):
    return group_node(name, list(children))


def page(name):
    return {'type': 'page', 'page_id': name}


def test_group_progress_nested_and_empty():
    root = group('Semester', page('a'), group('Week 2', page('b'), page('c')))
    assert group_counts(root, {'a', 'c'}) == (2, 3)
    assert group_counts(group('Empty'), {'a'}) == (0, 0)
    assert percentage(2, 3) == 67
    assert percentage(0, 0) == 0
    assert percentage(1, 101) == 1


def test_bulk_read_is_one_state_change_and_moving_does_not_clear_it():
    existing = {'a'}
    after = set_read_status(existing, ['a', 'b', 'c'], ['b', 'c'], True)
    assert after == {'a', 'b', 'c'}
    assert set_read_status(after, ['a', 'b', 'c'], ['a', 'c'], False) == {'b'}
    assert existing == {'a'}
    with pytest.raises(ValueError):
        set_read_status(existing, ['a'], ['deleted'], True)


def test_saved_read_status_round_trip_and_legacy_default():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        prj = Project.create(root, 'lecture')
        prj.pages = [{'id': 'one', 'title': '1'},
                     {'id': 'two', 'title': '2'}]
        prj.page_groups = flat_tree(['one', 'two'])
        prj.read_page_ids = ['one']
        prj.save()
        reloaded = Project.load(prj.path)
        assert reloaded.read_page_ids == ['one']
        assert notebook_totals([reloaded]) == (1, 2)
        file = prj.path / 'project.json'
        saved = json.loads(file.read_text())
        saved.pop('read_page_ids')
        file.write_text(json.dumps(saved))
        assert Project.load(prj.path).read_page_ids == []


def test_deleted_page_read_value_not_serialized_but_still_in_session():
    with tempfile.TemporaryDirectory() as directory:
        prj = Project.create(Path(directory), 'notes')
        prj.pages = [{'id': 'secret', 'title': 'old'},
                     {'id': 'live', 'title': 'new'}]
        prj.page_groups = flat_tree(['secret', 'live'])
        prj.read_page_ids = ['secret', 'live']
        prj.save()
        prj.pages = prj.pages[1:]
        prj.page_groups = flat_tree(['live'])
        prj.save()
        assert 'secret' in prj.read_page_ids  # available for session Undo
        saved = json.loads((prj.path / 'project.json').read_text())
        assert saved['read_page_ids'] == ['live']
        assert Project.load(prj.path).read_page_ids == ['live']


def test_bad_read_ids_are_rejected():
    with pytest.raises(ValueError):
        validated_read_ids(['a', 'a'], ['a'])
    with pytest.raises(ValueError):
        validated_read_ids(['a', 'removed'], ['a'])
    with pytest.raises(ValueError):
        validated_read_ids('a', ['a'])


def test_group_move_reorders_every_descendant_without_losing_pages():
    middle = group('Week 2', page('b'), group('Notes', page('c')))
    mid_id = middle['id']
    tree = [group('Week 1', page('a')), middle, group('Week 3', page('d'))]
    changed = move_group(tree, mid_id, None, 0)
    assert flatten(changed) == ['b', 'c', 'a', 'd']
    assert flatten(tree) == ['a', 'b', 'c', 'd']
    validate(changed, ['a', 'b', 'c', 'd'])
    assert changed[0]['children'][1]['children'][0]['page_id'] == 'c'


def test_group_move_out_of_subgroup_and_invalid_descendant():
    inner = group('Nested', page('x'))
    root = group('Main', page('a'), inner)
    tree = [root, page('b')]
    moved = move_group(tree, inner['id'], None, 1)
    assert [n['type'] for n in moved] == ['group', 'group', 'page']
    assert flatten(moved) == ['a', 'x', 'b']
    with pytest.raises(ValueError):
        move_group(tree, root['id'], inner['id'])
    with pytest.raises(ValueError):
        move_group(tree, root['id'], root['id'])
    with pytest.raises(ValueError):
        move_group(tree, uuid4().hex)


def test_group_move_reparents_without_changing_read_id_set():
    left = group('Before', page('a'))
    right = group('After', page('b'))
    completed = {'a'}
    moved = move_group([left, right], left['id'], right['id'], 1)
    assert flatten(moved) == ['b', 'a']
    assert group_counts(moved[0], completed) == (1, 2)


@pytest.mark.parametrize('preset', [k for k in FORMATS if k != 'custom'])
def test_label_presets_are_stable(preset):
    name = make_title('Hobbes & Griffiths (2026)', 2, 12, preset)
    assert isinstance(name, str) and len(name) > 0


def test_custom_pattern_and_roman_numerals():
    assert make_title('Leviathan', 4, 10, 'custom',
                      '{filename} · {roman} / {total}') == 'Leviathan · IV / 10'
    assert make_title('Notes', 3, 12, 'page_padded') == 'Page 003'
    with pytest.raises(ValueError):
        make_title('Notes', 3, 12, 'custom', '{filename} only')
    assert make_title('{n} is a filename', 1, 1,
                      'filename_page') == '{n} is a filename · Page 1'


def test_source_page_number_unmodified_by_display_labeling():
    pages = [{'source_page': 6, 'id': 'a'},
             {'source_page': 7, 'id': 'b'}]
    label_imported_pages(pages, 'Article', 'filename_number')
    assert [p['title'] for p in pages] == ['Article · 1', 'Article · 2']
    assert [p['source_page'] for p in pages] == [6, 7]


def test_very_long_academic_image_filename_uses_safe_internal_asset():
    # The Windows problem was that the *display* name could be copied
    # into the internal relative path, then rejected on notebook save.
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / ('Long Academic Paper by University Scholars ' +
                         'and Their Research Findings ' * 4 + '.png')
        Image.new('RGB', (24, 24)).save(source)
        project = Project.create(root, 'test')
        pages = import_document(project, source)
        assert len(pages) == 1
        relative = pages[0]['source']
        assert relative.startswith('originals/')
        assert len(Path(relative).name) < 50
        assert pages[0]['original_name'] == source.name
        project.pages.extend(pages)
        project.save()
        assert Project.load(project.path).pages[0]['source'] == relative


def test_smart_import_creates_one_root_group_per_file():
    from yomunote.import_planning import plan_import
    before = [group('Existing', page('old'))]
    batches = [('Reading', ['r1', 'r2']), ('Slides', ['s1', 's2'])]
    result, available = plan_import(
        before, ['old'], batches, position=0, smart=True)
    assert available
    assert [n['name'] for n in result if n['type'] == 'group'] == [
        'Reading', 'Slides', 'Existing']
    assert flatten(result) == ['r1', 'r2', 's1', 's2', 'old']
    assert flatten(before) == ['old']


def test_smart_import_nests_each_file_under_selected_group():
    from yomunote.import_planning import plan_import
    root = group('Module', page('old'))
    tree, _available = plan_import(
        [root], ['old'], [('Week 1', ['a', 'b'])],
        position=0, group_id=root['id'], smart=True)
    assert tree[0]['children'][1]['name'] == 'Week 1'
    assert flatten(tree) == ['old', 'a', 'b']


def test_ordinary_import_is_ungrouped_unless_group_target_selected():
    from yomunote.import_planning import plan_import
    folder = group('Previous lesson', page('old1'), page('old2'))
    ungrouped, available = plan_import(
        [folder], ['old1', 'old2'], [('New', ['p1', 'p2'])],
        position=1, smart=False)
    assert available
    assert ungrouped[0]['id'] == folder['id']
    assert ungrouped[0]['children'] == folder['children']
    assert [n['page_id'] for n in ungrouped[1:]] == ['p1', 'p2']
    nested, available = plan_import(
        [folder], ['old1', 'old2'], [('New', ['p1', 'p2'])],
        position=1, group_id=folder['id'], smart=False)
    assert available
    assert flatten(nested) == ['old1', 'old2', 'p1', 'p2']


def test_smart_import_missing_group_is_rejected_not_silently_rerouted():
    from yomunote.import_planning import plan_import
    folder = group('Old', page('a'))
    original = [folder]
    with pytest.raises(ValueError, match='destination group'):
        plan_import(
            original, ['a'], [('New', ['b'])],
            position=1, group_id=uuid4().hex, smart=True)
    assert flatten(original) == ['a']


def test_smart_import_duplicate_page_ids_do_not_mutate_old_tree():
    from yomunote.import_planning import plan_import
    original = flat_tree(['a'])
    with pytest.raises(ValueError):
        plan_import(original, ['a'], [('Bad', ['a'])],
                    position=1, smart=True)
    assert flatten(original) == ['a']


def test_long_pdf_source_filename_keeps_original_as_metadata():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / ('Large Article by Author One, Author Two, and Author Three ' +
                         'Research Materials Across Universities ' * 3 + '.pdf')
        Image.new('RGB', (20, 20), 'white').save(source, format='PDF')
        project = Project.create(root, 'study')
        pages = import_document(project, source)
        assert len(pages) == 1
        assert pages[0]['original_name'] == source.name
        assert len(Path(pages[0]['source']).name) < 45
        assert pages[0]['render_source'] == pages[0]['source']
        project.pages = pages
        project.save()
        assert Project.load(project.path).pages[0]['title'] == source.stem + ' · 1'


def test_smart_import_can_combine_selected_images_into_one_group():
    from yomunote.import_planning import plan_import
    tree, available = plan_import(
        flat_tree(['before']), ['before'],
        [('image1', ['image1-id']), ('image2', ['image2-id'])],
        position=1, smart=True, group_mode='combined',
        single_group_label='Photographs for Week 3')
    assert available
    assert tree[1]['type'] == 'group'
    assert tree[1]['name'] == 'Photographs for Week 3'
    assert flatten(tree) == ['before', 'image1-id', 'image2-id']
