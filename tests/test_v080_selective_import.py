"""Smart Import 3.0 guarantees: selection is source-accurate and atomic."""
import ast
from pathlib import Path

import pytest

from yomunote.import_selection import (parse_page_ranges, select_source_pages,
    remap_selected_sections, filter_staged_import, heading_page_bounds)
from yomunote.import_planning import plan_import
from yomunote.page_groups import flat_tree, flatten, validate
from yomunote.import_labels import relabel_reviewed_chapters


def heading(title, start, level=1):
    return {'title': title, 'start': start, 'level': level, 'origin': 'PDF bookmark'}


def test_page_range_parser_preserves_source_order_and_deduplicates():
    assert parse_page_ranges('10-12, 2, 5-7, 6, 12, 8–9', 15) == [2, 5, 6, 7, 8, 9, 10, 11, 12]
    assert parse_page_ranges(' 1 ', 1) == [1]


@pytest.mark.parametrize('bad,count', [('', 5), (' , ',5),('1,',5),('0',5),('1-6',5),
                                         ('4-3',5),('3-4-5',5),('-1',5),
                                         ('2,foo',5),('1-9999999999',5),('1',0)])
def test_malformed_page_ranges_fail_closed(bad, count):
    with pytest.raises(ValueError):
        parse_page_ranges(bad,count)


def test_chapter_children_and_frontmatter_are_separately_selectable():
    sections = [heading('Part A',3),heading('A.1',4,2), heading('A.2',8,2),
                heading('Part B',12)]
    assert heading_page_bounds(sections,15) == [(3,11),(4,7),(8,11),(12,15)]
    assert select_source_pages(15, sections) == list(range(1,16))
    assert select_source_pages(15, sections, section_enabled=[True,False,True,False],
                               include_frontmatter=False) == [3,8,9,10,11]
    assert select_source_pages(15, sections, section_enabled=[False,True,False,False]) == [1,2,4,5,6,7]
    assert select_source_pages(15, sections, section_enabled=[True,False,True,False],
                               page_range=parse_page_ranges('1-5,10-13',15),
                               include_frontmatter=False) == [3,10,11]


def test_sparse_range_remaps_boundaries_and_prunes_empty_chapters():
    sections = [heading('Preface',1),heading('Part A',3),heading('A.1',3,2),
                heading('A.2',7,2), heading('Part B',11)]
    numbers = [5,6,8,11,14]
    result = remap_selected_sections(sections,15,numbers)
    assert [(h['title'],h['start'],h['level']) for h in result] == [
        ('Part A',1,1),('A.1',1,2),('A.2',3,2),('Part B',4,1)]
    assert remap_selected_sections(sections,15,[1,2]) == [heading('Preface',1)]
    assert remap_selected_sections(sections,15,[]) == []


def test_selection_filters_staged_without_modifying_original_metadata():
    sources = [('PDF', [{'id':f'p{i}','source_index':i-1} for i in range(1,7)]),
               ('Other', [{'id':f'q{i}','source_index':i-1} for i in range(1,5)])]
    headings = [[heading('C1',1), heading('C2',4)], [heading('One',1)]]
    retained, remapped, omitted = filter_staged_import(sources,headings,[[2,5],[]])
    assert [p['id'] for p in retained[0][1]] == ['p2','p5']
    assert [p['source_index'] for p in retained[0][1]] == [1,4]
    assert [(h['title'],h['start']) for h in remapped[0]] == [('C1',1),('C2',2)]
    assert len(omitted) == 2
    assert len(sources[0][1]) == 6 and len(sources[1][1]) == 4
    assert len(retained) == 1
    with pytest.raises(ValueError,match='Select at least one'):
        filter_staged_import(sources, headings, [[],[]])


def test_filtered_groups_commit_as_single_valid_flat_order_and_existing_unchanged():
    original = flat_tree(['existing'])
    batches = [('One', [{'id':f'p{i}'} for i in range(1,10)])]
    sections = [[heading('A',1),heading('B',5),heading('B.1',6,2)]]
    filtered, remapped, _omitted = filter_staged_import(batches,sections,[[3,7,8]])
    result, _ = plan_import(original, ['existing'],
                            [(name,[p['id'] for p in pages]) for name,pages in filtered],
                            position=1, smart=True, sections_by_file=remapped)
    assert flatten(result) == ['existing','p3','p7','p8']
    validate(result,['existing','p3','p7','p8'])
    assert flatten(original)==['existing']


def test_chapter_tokens_keep_original_source_chapter_number_after_filtering():
    batches = [('Textbook',[{'id':str(i)} for i in range(1,11)])]
    headings = [[heading('Chapter 1',1),heading('Chapter 2',4),heading('Chapter 3',8)]]
    relabel_reviewed_chapters(batches,headings,'[filename] Ch [chapter] Page [page]')
    filtered, remapped, _omitted = filter_staged_import(batches,headings,[[8,10]])
    assert all('Ch 3 ' in p['title'] for p in filtered[0][1])
    assert [s['title'] for s in remapped[0]] == ['Chapter 3']


def test_gui_and_worker_use_same_pure_selection_module():
    root=Path(__file__).resolve().parents[1]/'yomunote'
    for name in ('import_selection','import_review_dialog','window'):
        ast.parse((root/(name+'.py')).read_text(encoding='utf-8'))
    ui=(root/'import_review_dialog.py').read_text()
    window=(root/'window.py').read_text()
    assert 'selected_pages_by_file' in ui
    assert 'filter_staged_import(' in window
    assert 'cleanup_uncommitted(self.project, omitted_batches)' in window
    assert 'selection_only=not smart_import' in window


def test_real_pdf_selective_import_roundtrip(tmp_path):
    fitz=pytest.importorskip('fitz')
    from yomunote.importers import import_document
    from yomunote.import_structure import detected_structure
    from yomunote.project import Project
    source=tmp_path/'reading.pdf'
    doc=fitz.open()
    for _ in range(12):
        doc.new_page()
    doc.set_toc([[1,'Chapter A',1],[1,'Chapter B',5],[2,'B.1',7],
                 [1,'Chapter C',10]])
    doc.save(source)
    doc.close()
    project=Project.create(tmp_path,'Filtered')
    staged=import_document(project,source)
    analysis=detected_structure(project,staged)
    assert [h['start'] for h in analysis['sections']]==[1,5,7,10]
    selected=select_source_pages(12,analysis['sections'],
        page_range=parse_page_ranges('4,7-8,11',12),
        section_enabled=[False,True,True,True])
    assert selected==[7,8,11]
    batches, sections, _omitted=filter_staged_import(
        [(source.stem,staged)],[analysis['sections']],[selected])
    tree, _=plan_import(project.page_groups,[],
        [(source.stem,[p['id'] for p in batches[0][1]])],
        position=0,smart=True, sections_by_file=sections)
    project.pages=batches[0][1]
    project.page_groups=tree
    project.save()
    loaded=Project.load(project.path)
    assert [p['id'] for p in loaded.pages] == [staged[i-1]['id'] for i in selected]
    assert len(loaded.pages)==3
    assert flatten(loaded.page_groups)==[p['id'] for p in loaded.pages]
    validate(loaded.page_groups,[p['id'] for p in loaded.pages])
