"""Tests for v5's incremental, single-file project and safe backups (no Qt)."""
import json
import sqlite3
from pathlib import Path
import pytest
from yomunote.project import Project
from yomunote.notebook import Notebook, NOTEBOOK_VERSION


def test_single_file_tabs_are_independent_and_reopen(tmp_path):
    nb = Notebook.create(tmp_path, 'Film Studies')
    original_id = nb.active_id
    first = nb.project(original_id)
    first.notes_html = '<h1>Seminar One</h1>'
    first.notes_scroll = 310
    first.pages.append({'id': 'slide-a', 'title': 'Slide A', 'kind': 'image',
                        'source': 'originals/slides.png', 'render_source': 'originals/slides.png',
                        'source_page': 1})
    first.asset_path('originals/slides.png').write_bytes(b'pretend image source')
    first.save()
    second_id = nb.add_tab('Reading Material')
    second = nb.project(second_id)
    second.notes_html = '<p>A different reading and independent notes.</p>'
    second.save()
    nb.active_id = second_id
    nb.save()
    assert nb.path.is_file()  # NOT a legacy .yominote directory
    with sqlite3.connect(nb.path) as conn:
        stored = [r[0] for r in conn.execute('SELECT path FROM files')]
    assert f'tabs/{original_id}/originals/slides.png' in stored
    assert not any('/cache/' in p for p in stored)
    nb.close()
    reloaded = Notebook.load(tmp_path/'Film Studies.yomunote')
    try:
        assert len(reloaded.tabs) == 2
        assert reloaded.active_id == second_id
        assert reloaded.project(original_id).notes_html == '<h1>Seminar One</h1>'
        assert reloaded.project(original_id).notes_scroll == 310
        assert reloaded.project(original_id).asset_path('originals/slides.png').read_bytes() == b'pretend image source'
        assert reloaded.project(second_id).notes_html.startswith('<p>A different reading')
        assert NOTEBOOK_VERSION == 5
    finally:
        reloaded.close()


def test_delete_undo_redo_after_save_preserves_pages_and_notes(tmp_path):
    nb = Notebook.create(tmp_path, 'Biology')
    other_id = nb.add_tab('Lecture One')
    p = nb.project(other_id)
    p.notes_html = 'Must not lose these notes'
    p.save()
    nb.save()
    index, saved = nb.delete_tab(other_id)
    nb.save()
    assert all(t['id'] != other_id for t in nb.tabs)
    nb.restore_tab(index, saved)
    nb.save()
    assert nb.project(other_id).notes_html == 'Must not lose these notes'
    nb.delete_tab(other_id)
    nb.save()
    with pytest.raises(KeyError):
        nb.project(other_id)
    nb.close()
    reopened = Notebook.load(tmp_path/'Biology.yomunote')
    assert len(reopened.tabs) == 1
    reopened.close()


def test_rotating_backups_exclude_caches_and_require_a_new_restore_destination(tmp_path):
    nb = Notebook.create(tmp_path, 'Sociology')
    p = nb.project(nb.active_id)
    (p.path/'cache'/'previews'/'giant.jpg').write_bytes(b'x'*4096)
    backups = tmp_path/'Backups'
    for n in range(4):
        p.notes_html = '<p>' + str(n) + '</p>'
        p.save()
        nb.save()
        snapshot = nb.backup(backups, limit=2)
        assert snapshot and snapshot.exists()
    assert len(list(backups.glob('*.yomunote'))) == 2
    with sqlite3.connect(snapshot) as conn:
        assert not any('/cache/' in p for (p,) in conn.execute('SELECT path FROM files'))
    destination = tmp_path/'Recovered.yomunote'
    Notebook.restore_copy(snapshot, destination)
    assert destination.is_file()
    recovered = Notebook.load(destination)
    assert recovered.project(recovered.active_id).notes_html == '<p>3</p>'
    assert recovered.identifier != nb.identifier
    recovered.close()
    with pytest.raises(FileExistsError):
        Notebook.restore_copy(snapshot, destination)
    with pytest.raises(FileExistsError):
        Notebook.restore_copy(snapshot, nb.path)
    nb.close()


def test_migrate_old_folder_into_new_file_without_overwriting(tmp_path):
    older = Project.create(tmp_path, 'Old Module')
    older.notes_html = '<p>Carefully kept legacy notes</p>'
    older.notes_scroll = 187
    older.pages.append({'id':'legacy-page','kind':'image','title':'Original',
                        'source':'originals/a.jpg','render_source':'originals/a.jpg'})
    older.asset_path('originals/a.jpg').write_bytes(b'old asset')
    older.save()
    original_bytes = (older.path/'project.json').read_bytes()
    imported = Notebook.load(older.path)
    try:
        assert imported.path.is_file()
        assert imported.path != older.path
        assert imported.project(imported.active_id).notes_html == older.notes_html
        assert imported.project(imported.active_id).notes_scroll == 187
        assert imported.project(imported.active_id).asset_path('originals/a.jpg').read_bytes() == b'old asset'
        assert (older.path/'project.json').read_bytes() == original_bytes
    finally:
        imported.close()
    assert (older.path/'project.json').is_file()


def test_page_transfer_copy_move_preserves_aspect_source_and_annotations(tmp_path):
    nb = Notebook.create(tmp_path, 'Slides')
    source_id = nb.active_id
    target_id = nb.add_tab('Week Two')
    source = nb.project(source_id)
    source.asset_path('originals/deck.pdf').write_bytes(b'%PDF fake content')
    source.pages = [
        {'id':'first','title':'One','kind':'pdf','source':'originals/deck.pdf',
         'render_source':'originals/deck.pdf','source_page':1},
        {'id':'second','title':'Two','kind':'pdf','source':'originals/deck.pdf',
         'render_source':'originals/deck.pdf','source_page':2},
    ]
    source.annotations = {'first':[{'kind':'highlight','x':.1,'y':.2,'w':.3,'h':.1,'color':'#ffcf69'}]}
    source.save()
    assert nb.transfer_pages(source_id,target_id,['first','second']) == 2
    result = nb.project(target_id)
    assert len(result.pages) == 2
    assert result.pages[0]['source'] == result.pages[1]['source']
    assert result.annotations[result.pages[0]['id']] == source.annotations['first']
    assert result.pages[0]['id'] != 'first'
    assert nb.project(source_id).pages[0]['id'] == 'first'
    assert nb.transfer_pages(source_id,target_id,['first','second'],move=True) == 2
    assert nb.project(source_id).pages == []
    assert len(nb.project(target_id).pages) == 4
    nb.save()
    nb.close()


def test_reject_untrusted_notebook_paths(tmp_path):
    nb = Notebook.create(tmp_path, 'Not Malicious')
    tabid = nb.active_id
    path = nb.path
    nb.close()
    with sqlite3.connect(path) as conn:
        conn.execute('INSERT INTO files(path,data,size,mtime_ns) VALUES(?,?,?,?)',
                     ('tabs/'+tabid+'/../../escape.txt',b'bad',3,11111))
    with pytest.raises(ValueError, match='Unsafe'):
        Notebook.load(path)
    assert not (tmp_path/'escape.txt').exists()


def test_no_unused_backup_when_unchanged(tmp_path):
    nb = Notebook.create(tmp_path, 'Backup Only Changes')
    folder = tmp_path/'Backups'
    assert nb.backup(folder) is not None  # first initial save
    assert nb.backup(folder) is None
    assert nb.save() is False
    assert nb.backup(folder) is None
    nb.close()
