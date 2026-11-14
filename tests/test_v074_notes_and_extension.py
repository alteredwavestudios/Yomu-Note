"""v0.7.4 model-level no-data-loss and filename-migration regressions."""
import copy
import json
import sqlite3
import hashlib
import uuid

import pytest

from yomunote.project import Project, validated_note_pages
from yomunote.notebook import Notebook


def _page(name, html, scroll=0, setup=None):
    return {'id': uuid.uuid4().hex, 'title': name, 'html': html,
            'scroll': scroll, 'page_setup': setup}


def test_pre074_project_notes_html_migrates_verbatim(tmp_path):
    p = Project.create(tmp_path, 'Old Class')
    original = '<p><a href="yomu-page:p-1">Page link</a> <b>and bold!</b></p>'
    p.notes_html = original
    p.notes_scroll = 412
    p.save()
    manifest = p.path / 'project.json'
    old = json.loads(manifest.read_text())
    old.pop('note_pages', None)
    old.pop('active_note_id', None)
    manifest.write_text(json.dumps(old))
    loaded = Project.load(p.path)
    assert loaded.notes_html == original
    assert loaded.notes_scroll == 412
    assert len(loaded.note_pages) == 1
    assert loaded.note_pages[0]['html'] == original
    assert loaded.note_pages[0]['scroll'] == 412
    loaded.save()
    reopened = Project.load(p.path)
    assert reopened.note_pages[0]['html'] == original
    assert reopened.notes_html == original


def test_multiple_note_pages_and_links_roundtrip_independently(tmp_path):
    p = Project.create(tmp_path, 'Research')
    first = _page('Lecture summaries', '<p><b>Strong</b> <a href="yomu-page:abc">linked</a></p>', 42)
    second = _page('Bibliography', '<table><tr><td>References</td></tr></table>', 118)
    third = _page('Draft essay', '<p><span style="font-size:18pt">A paragraph</span></p>', 9)
    p.note_pages = [copy.deepcopy(first), copy.deepcopy(second), copy.deepcopy(third)]
    p.active_note_id = second['id']
    p.save()
    stored = Project.load(p.path)
    assert stored.active_note_id == second['id']
    assert stored.note_pages == [first, second, third]
    assert stored.notes_html == first['html']  # legacy compatibility mirror
    assert stored.notes_scroll == first['scroll']
    stored.note_pages[2]['html'] += '<p>More words</p>'
    stored.save()
    reopened = Project.load(stored.path)
    assert reopened.note_pages[0]['html'] == first['html']
    assert reopened.note_pages[1]['html'] == second['html']
    assert reopened.note_pages[2]['html'].endswith('<p>More words</p>')


def test_single_page_old_api_remains_writable(tmp_path):
    p = Project.create(tmp_path, 'Single')
    p.notes_html = '<p>First direct edit</p>'
    p.notes_scroll = 888
    p.save()
    reopened = Project.load(p.path)
    assert reopened.note_pages[0]['html'] == '<p>First direct edit</p>'
    assert reopened.note_pages[0]['scroll'] == 888


def test_note_pages_reject_bad_ids_duplicates_and_malformed_text():
    page = _page('Chapter', '<p>Notes</p>')
    with pytest.raises(ValueError, match='duplicate'):
        validated_note_pages([page, copy.deepcopy(page)], None, '', 0, None)
    bad = copy.deepcopy(page)
    bad['html'] = []
    with pytest.raises(ValueError, match='content'):
        validated_note_pages([bad], None, '', 0, None)
    with pytest.raises(ValueError, match='maximum'):
        validated_note_pages([_page(str(i), '') for i in range(129)], None, '', 0, None)


def test_notebook_v5_keeps_note_page_metadata_inside_existing_file_format(tmp_path):
    notebook = Notebook.create(tmp_path, 'Lecture Notes')
    try:
        p = notebook.project(notebook.active_id)
        p.note_pages = [_page('One', '<p>Original</p>'), _page('Two', '<p>Separate!</p>')]
        p.active_note_id = p.note_pages[1]['id']
        p.save()
        notebook.save()
        path = notebook.path
        assert path.suffix == '.yomunote'
    finally:
        notebook.close()
    reopened = Notebook.load(path)
    try:
        p = reopened.project(reopened.active_id)
        assert len(p.note_pages) == 2
        assert p.note_pages[0]['html'] == '<p>Original</p>'
        assert p.note_pages[1]['html'] == '<p>Separate!</p>'
        assert p.active_note_id == p.note_pages[1]['id']
    finally:
        reopened.close()


def test_open_old_extension_creates_new_copy_without_touching_old_bytes(tmp_path):
    import shutil
    notebook = Notebook.create(tmp_path, 'A Lesson')
    old = notebook.path.with_suffix('.yominote')
    notebook.close()
    shutil.move(tmp_path / 'A Lesson.yomunote', old)
    before = hashlib.sha256(old.read_bytes()).hexdigest()
    converted = Notebook.load(old)
    try:
        assert converted.path.suffix == '.yomunote'
        assert converted.path.is_file()
        assert old.is_file()
        assert hashlib.sha256(old.read_bytes()).hexdigest() == before
        # Save into the NEW file; old immutable snapshot must remain intact.
        p = converted.project(converted.active_id)
        p.notes_html = 'Changed'
        p.save()
        converted.save()
        assert hashlib.sha256(old.read_bytes()).hexdigest() == before
    finally:
        converted.close()


def test_sanitized_name_and_extension_do_not_change_existing_path(tmp_path):
    notebook = Notebook.create(tmp_path, 'Chapter / Notes')
    assert notebook.path.suffix == '.yomunote'
    notebook.close()
