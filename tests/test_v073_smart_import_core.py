"""Smart Import 2.0: page safety, nested outlines and cancelled-stage cleanup."""
import ast
from copy import deepcopy
from pathlib import Path

import pytest

from yomunote.import_structure import (
    validate_sections, section_tree, fixed_range_sections,
    extract_pdf_outline, detected_structure,
)
from yomunote.import_planning import plan_import
from yomunote.import_staging import cleanup_uncommitted
from yomunote.page_groups import flatten, flat_tree, group_node, validate
from yomunote.project import Project


def chapter(title, page, level=1):
    return dict(title=title, start=page, level=level, origin='PDF bookmark')


def test_nested_outline_page_coverage_and_actual_boundaries():
    entries = [chapter('Intro', 1), chapter('Chapter 1', 3),
               chapter('1.1', 3, 2), chapter('1.2', 6, 2),
               chapter('Chapter 2', 10)]
    ids = [f'page-{i}' for i in range(1, 13)]
    built = section_tree(ids, entries)
    assert flatten(built) == ids
    assert built[1]['name'] == 'Chapter 1'
    assert built[1]['children'][0]['name'] == '1.1'
    assert [p['page_id'] for p in built[1]['children'][0]['children']] == ids[2:5]
    assert [p['page_id'] for p in built[1]['children'][1]['children']] == ids[5:9]
    validate(built, ids)


def test_ungrouped_front_matter_never_disappears():
    ids = ['cover', 'toc', 'a', 'b']
    built = section_tree(ids, [chapter('Chapter 1', 3)])
    assert [node['page_id'] for node in built[:2]] == ['cover', 'toc']
    assert flatten(built) == ids


@pytest.mark.parametrize('entries', [
    [chapter('', 2)], [chapter('Out of range', 999)],
    [chapter('Chapter', 2, 3)], [chapter('One', 4), chapter('Two', 3)],
    [chapter('One', 2), chapter('Two', 2)],
    [chapter('One', 3), chapter('Sub', 3, 2), chapter('Same-page sibling', 3, 2)],
])
def test_bad_outline_rejected_without_touching_live_tree(entries):
    base = flat_tree(['old'])
    original = deepcopy(base)
    with pytest.raises(ValueError):
        plan_import(base, ['old'], [('New', ['p1','p2','p3','p4'])],
                    smart=True, position=1, sections_by_file=[entries])
    assert original == base


def test_destination_is_strict_in_reviewed_imports():
    old = flat_tree(['old'])
    with pytest.raises(ValueError, match='destination group'):
        plan_import(old, ['old'], [('New', ['p'])], smart=True,
                    position=1, group_id='deadbeef'*4, strict_target=True)
    assert flatten(old) == ['old']


@pytest.mark.parametrize('mode', ['per_file', 'combined', 'none'])
def test_each_arrangement_contains_every_source_page_once(mode):
    old = [group_node('Existing', [{'type':'page','page_id':'old'}])]
    batches = [('Textbook', ['a','b','c']), ('Lecture', ['d','e'])]
    proposed = [[chapter('Intro', 1), chapter('Chapter 1', 2)],
                [chapter('Lecture', 1)]]
    result, okay = plan_import(old, ['old'], batches, smart=True,
                               group_mode=mode, position=1,
                               sections_by_file=proposed)
    assert okay
    assert flatten(result) == ['old','a','b','c','d','e']
    assert flatten(old) == ['old']
    validate(result, ['old','a','b','c','d','e'])
    if mode == 'per_file':
        assert [x['name'] for x in result[1:]] == ['Textbook','Lecture']
    elif mode == 'combined':
        assert result[1]['name'] == 'Imported documents'
    else:
        assert all(n['type'] == 'page' for n in result[1:])


def test_nested_under_explicit_group_and_undo_snapshot_integrity():
    old_group = group_node('Module', [{'type':'page','page_id':'old'}])
    before = deepcopy([old_group])
    result, _ = plan_import([old_group], ['old'], [('Paper', ['a','b'])],
                            smart=True, position=1, group_id=old_group['id'],
                            sections_by_file=[[chapter('Intro',1), chapter('Part B',2)]],
                            strict_target=True)
    assert before == [old_group]
    assert len(result[0]['children']) == 2
    assert result[0]['children'][1]['name'] == 'Paper'
    assert len(result[0]['children'][1]['children']) == 2
    validate(result, ['old','a','b'])


def test_fixed_page_intervals_and_size_limit():
    headings = fixed_range_sections(45, 20)
    assert [h['start'] for h in headings] == [1, 21, 41]
    assert headings[-1]['title'] == 'Pages 41–45'
    with pytest.raises(ValueError, match='larger page interval'):
        fixed_range_sections(20_000, 1)


def test_cancel_removes_only_staged_files_not_live_assets(tmp_path):
    project = Project.create(tmp_path, 'Cancel-safety')
    original = project.asset_path('originals/already.pdf')
    original.write_bytes(b'LIVE')
    new = project.asset_path('originals/new.pdf')
    new.write_bytes(b'NOT-COMMITTED')
    render = project.asset_path('originals/render.pdf')
    render.write_bytes(b'RENDER')
    project.pages = [{'id':'live', 'source':'originals/already.pdf',
                      'render_source':'originals/already.pdf'}]
    batch = [('A', [{'id':'staged', 'source':'originals/new.pdf',
                    'render_source':'originals/render.pdf'}])]
    cleanup_uncommitted(project, batch)
    assert original.read_bytes() == b'LIVE'
    assert not new.exists() and not render.exists()
    assert [p['id'] for p in project.pages] == ['live']


def test_real_pdf_bookmarks_are_read_without_rasterisation(tmp_path):
    fitz = pytest.importorskip('fitz')
    path = tmp_path / 'outline.pdf'
    doc = fitz.open()
    for _ in range(12):
        doc.new_page()
    doc.set_toc([[1,'Preface',1],[1,'Chapter 1',3],
                 [2,'1.1',3],[2,'1.2',6],[1,'Chapter 2',10]])
    doc.save(path)
    doc.close()
    count, sections, warnings = extract_pdf_outline(path)
    assert count == 12 and warnings == []
    assert [(s['title'], s['start'], s['level']) for s in sections] == [
        ('Preface',1,1),('Chapter 1',3,1),('1.1',3,2),
        ('1.2',6,2),('Chapter 2',10,1)]


def test_review_dialog_and_import_ui_compile_even_when_qt_is_unavailable():
    root = Path(__file__).resolve().parents[1] / 'yomunote'
    for name in ('import_options_dialog.py','import_review_dialog.py','window.py'):
        ast.parse((root / name).read_text(encoding='utf-8'))
    ui = (root / 'import_options_dialog.py').read_text(encoding='utf-8')
    review = (root / 'import_review_dialog.py').read_text(encoding='utf-8')
    win = (root / 'window.py').read_text(encoding='utf-8')
    assert 'Root of this tab (outside existing groups)' in ui
    assert 'One group for each source file' in ui
    assert 'self.destination.currentData()' in ui
    assert 'All pages will be imported exactly once' in review
    assert 'cleanup_uncommitted(self.project, batches)' in win
    assert 'strict_target=True' in win


def test_real_import_indexes_then_commits_bookmarks_with_stable_ids(tmp_path):
    """Full PDF -> staging -> PDFium outline -> grouped manifest -> reload."""
    fitz = pytest.importorskip('fitz')
    from yomunote.importers import import_document
    path = tmp_path / 'academic-reading.pdf'
    doc = fitz.open()
    for _ in range(8):
        doc.new_page()
    doc.set_toc([[1,'Introduction',2], [1,'Theories',4], [2,'Marx',5]])
    doc.save(path)
    doc.close()
    project = Project.create(tmp_path, 'Sociology')
    original_pages = list(project.pages)
    staged = import_document(project, path)
    assert not project.pages  # review has not changed the live notebook
    inspected = detected_structure(project, staged)
    assert [s['start'] for s in inspected['sections']] == [2, 4, 5]
    batch = [(path.stem, [page['id'] for page in staged])]
    proposed, available = plan_import(project.page_groups, [], batch,
        position=0, smart=True, group_mode='per_file',
        sections_by_file=[inspected['sections']], strict_target=True)
    assert available
    assert flatten(proposed) == batch[0][1]
    validate(proposed, [p['id'] for p in staged])
    project.page_groups = proposed
    project.pages = staged
    project.save()
    reloaded = Project.load(project.path)
    assert flatten(reloaded.page_groups) == [p['id'] for p in staged]
    assert reloaded.page_groups[0]['children'][0]['page_id'] == staged[0]['id']
    assert reloaded.page_groups[0]['children'][1]['name'] == 'Introduction'
    assert reloaded.page_groups[0]['children'][2]['name'] == 'Theories'
    assert reloaded.page_groups[0]['children'][2]['children'][1]['name'] == 'Marx'


def test_oversized_pdf_outline_requires_manual_review(tmp_path):
    fitz = pytest.importorskip('fitz')
    pdf = tmp_path / 'many.pdf'
    doc = fitz.open()
    for _ in range(305):
        doc.new_page()
    doc.set_toc([[1,f'Slide {i}',i] for i in range(1,306)])
    doc.save(pdf)
    doc.close()
    count, headings, warnings = extract_pdf_outline(pdf)
    assert count == 305
    assert headings == []
    assert any('Too many bookmarks' in message for message in warnings)
