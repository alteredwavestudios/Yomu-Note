"""v0.7.3a: regression cases for collapsed Smart Import and [chapter] labels.

The pure model tests run without Qt. Optional widget tests are in the
v0.7.3a GUI module and should be run with PySide6 on Windows or macOS.
"""
from copy import deepcopy
import pytest

from yomunote.import_labels import (make_title, label_imported_pages,
                                    uses_chapter_token, relabel_reviewed_chapters)
from yomunote.import_structure import chapter_numbers_for_pages
from yomunote.import_planning import plan_import
from yomunote.page_groups import group_node, flatten, validate


def entry(title, start, level=1):
    return {'title':title, 'start':start, 'level':level, 'origin':'Manual'}


def groups(tree):
    result = []
    for node in tree:
        if node['type'] == 'group':
            result.append(node)
            result += groups(node['children'])
    return result


def test_square_and_curly_placeholders_work_with_real_chapter_number():
    assert make_title('Lecture', 6, 10, 'custom',
                      'Ch [chapter] — Page [page]', chapter=2) == 'Ch 2 — Page 6'
    assert make_title('Lecture', 6, 10, 'custom',
                      '{filename} C{chapter} P{page}', chapter=2) == 'Lecture C2 P6'
    assert make_title('Lecture', 6, 10, 'custom',
                      '[n2] of [total] / [roman]') == '06 of 10 / VI'
    assert uses_chapter_token('[chapter]')
    assert uses_chapter_token('{chapter}')
    assert not uses_chapter_token('[page]')
    assert not uses_chapter_token('[chaptr]')
    with pytest.raises(ValueError, match='numbering token'):
        make_title('Lecture', 1, 5, 'custom', '[filename] only')


def test_chapter_number_counts_only_top_level_approved_sections():
    headings = [entry('Introduction',3), entry('Part A',3,2),
                entry('Part B',5,2), entry('Chapter Two',7),
                entry('Final section',8,2)]
    numbers = chapter_numbers_for_pages(9, headings)
    assert numbers == [1,1,1,1,1,1,2,2,2]
    pages = [{'id':f'p{i}','source_page':i} for i in range(9)]
    label_imported_pages(pages, 'Textbook', 'custom',
                         'Chapter [chapter] — Page [page]', chapter_numbers=numbers)
    assert [p['title'] for p in pages] == [
        f'Chapter {numbers[i]} — Page {i+1}' for i in range(9)]
    assert [p['source_page'] for p in pages] == list(range(9))
    assert chapter_numbers_for_pages(2, []) == [1,1]


def test_edited_chapter_boundary_changes_labels():
    initial = [entry('First', 1), entry('Second', 4)]
    edited = [entry('First', 1), entry('Second', 6)]
    assert chapter_numbers_for_pages(7, initial) == [1,1,1,2,2,2,2]
    assert chapter_numbers_for_pages(7, edited) == [1,1,1,1,1,2,2]


@pytest.mark.parametrize('mode', ['per_file','combined'])
@pytest.mark.parametrize('collapsed', [True,False])
def test_new_smart_import_groups_collapsed_setting_preserves_old_groups(mode,collapsed):
    existing = group_node('Existing folder', [{'type':'page','page_id':'old'}], collapsed=False)
    original = deepcopy([existing])
    batches = [('First file',['a','b','c']), ('Second file',['d','e'])]
    sections = [[entry('Chapter 1',1),entry('Sub',2,2)],
                [entry('Chapter 1',1)]]
    result, available = plan_import([existing],['old'],batches,
        smart=True, position=1, group_mode=mode, sections_by_file=sections,
        collapse_new_groups=collapsed)
    assert available
    assert flatten(result) == ['old','a','b','c','d','e']
    validate(result, ['old','a','b','c','d','e'])
    assert result[0]['collapsed'] is False
    assert original == [existing]
    new_nodes = groups(result[1:])
    assert new_nodes
    assert all(node['collapsed'] is collapsed for node in new_nodes)


def test_nested_destination_retains_existing_expansion():
    existing = group_node('Destination', [{'type':'page','page_id':'old'}], collapsed=False)
    result, available = plan_import([existing], ['old'], [('File',['a','b'])],
        smart=True, position=1, group_id=existing['id'],
        sections_by_file=[[entry('Chapter',1)]], collapse_new_groups=True)
    assert available
    assert result[0]['collapsed'] is False
    added = result[0]['children'][1]
    assert added['collapsed'] is True
    assert added['children'][0]['collapsed'] is True
    validate(result,['old','a','b'])


def test_ordinary_import_does_not_change_existing_group_state():
    existing = group_node('Existing', [{'type':'page','page_id':'old'}], collapsed=True)
    result, _ = plan_import([existing], ['old'], [('New',['a'])],
        smart=False, position=1, collapse_new_groups=True)
    assert result[0]['collapsed'] is True
    assert flatten(result) == ['old','a']


def test_reviewed_multi_source_labels_and_combined_page_counter():
    batches = [('Lecture A', [{'id':'a1'}, {'id':'a2'}, {'id':'a3'}]),
               ('Lecture B', [{'id':'b1'}, {'id':'b2'}])]
    headings = [[entry('Part 1',1),entry('Part 2',3)],
                [entry('Chapter B',1)]]
    relabel_reviewed_chapters(batches, headings,
        '[filename] / chapter [chapter] / page [page]', combined=False)
    assert [p['title'] for _n, ps in batches for p in ps] == [
        'Lecture A / chapter 1 / page 1',
        'Lecture A / chapter 1 / page 2',
        'Lecture A / chapter 2 / page 3',
        'Lecture B / chapter 1 / page 1',
        'Lecture B / chapter 1 / page 2']
    relabel_reviewed_chapters(batches, headings,
        '[filename] / chapter [chapter] / page [page] of [total]', combined=True)
    assert [p['title'] for _n, ps in batches for p in ps] == [
        'Lecture A / chapter 1 / page 1 of 5',
        'Lecture A / chapter 1 / page 2 of 5',
        'Lecture A / chapter 2 / page 3 of 5',
        'Lecture B / chapter 1 / page 4 of 5',
        'Lecture B / chapter 1 / page 5 of 5']


def test_real_pdf_chapter_labels_and_collapse_survive_save_reload(tmp_path):
    fitz = pytest.importorskip('fitz')
    from yomunote.importers import import_document
    from yomunote.import_structure import detected_structure
    from yomunote.project import Project

    path = tmp_path / 'testbook.pdf'
    doc = fitz.open()
    for _ in range(5):
        doc.new_page()
    doc.set_toc([[1,'Beginning',1], [2,'Details',2], [1,'Later',4]])
    doc.save(path)
    doc.close()
    project = Project.create(tmp_path, 'Chapter-save-test')
    pages = import_document(project, path)
    detected = detected_structure(project, pages)
    assert len(detected['sections']) == 3
    # Pretend the reader moved the second chapter boundary from 4 to 5.
    reviewed = deepcopy(detected['sections'])
    reviewed[-1]['start'] = 5
    batches = [('testbook', pages)]
    relabel_reviewed_chapters(batches, [reviewed],
                             'Ch [chapter], page [page]')
    hierarchy, valid = plan_import([], [],
        [('testbook', [page['id'] for page in pages])],
        position=0, smart=True, sections_by_file=[reviewed],
        collapse_new_groups=True)
    assert valid
    assert all(n['collapsed'] for n in groups(hierarchy))
    assert [p['title'] for p in pages] == [
        'Ch 1, page 1', 'Ch 1, page 2', 'Ch 1, page 3',
        'Ch 1, page 4', 'Ch 2, page 5']
    project.page_groups = hierarchy
    project.pages = pages
    project.save()
    loaded = Project.load(project.path)
    assert [p['title'] for p in loaded.pages] == [p['title'] for p in pages]
    assert [n['collapsed'] for n in groups(loaded.page_groups)] == [True]*4
    assert flatten(loaded.page_groups) == [p['id'] for p in loaded.pages]
