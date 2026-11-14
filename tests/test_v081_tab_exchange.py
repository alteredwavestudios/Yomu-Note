"""v0.8.1: complete, selective, privacy-clean tab sharing without Qt."""
from __future__ import annotations

import ast
import json
import sqlite3
from pathlib import Path
import shutil
import threading

import pytest

from yomunote import __version__
from yomunote.notebook import Notebook
from yomunote.page_groups import group_node, page_node
from yomunote.project import short_id
from yomunote.tab_exchange import (inspect_notebook, stage_import, commit_import,
                                   set_batch_present, export_tabs)
from yomunote.vector_marks import make_highlight


def populated_notebook(tmp_path):
    root = tmp_path / 'source'
    original = Notebook.create(root, 'Sociology course')
    first = original.active_id
    original.rename_tab(first, 'Week 1')
    second = original.add_tab('Week 2')
    third = original.add_tab('Week 3')
    original.active_id = first
    for i, tab_id in enumerate((first, second, third), 1):
        project = original.project(tab_id)
        pageid = short_id()
        document = f'originals/week-{i}.pdf'
        asset = project.asset_path(document)
        asset.parent.mkdir(parents=True, exist_ok=True)
        asset.write_bytes(b'%PDF-1.4\nSTUDY NOTES ' + bytes([65+i]) * (i * 500))
        project.pages = [{'id': pageid, 'title': f'Week {i} reading',
                          'kind': 'pdf', 'source': document, 'source_page': 1}]
        project.page_groups = [group_node('Chapter 1', [page_node(pageid)])]
        project.read_page_ids = [pageid]
        project.annotations = {pageid: [make_highlight((.1,.2,.3,.1), '#ffcf69')]}
        rich = f'<p><b>Week {i} lecture</b> and a source.</p>'
        project.notes_html = rich
        project.note_pages[0]['html'] = rich
        project.note_pages.append({'id': short_id(), 'title': 'Extra notes',
                                   'html': '<ul><li>Preserve <em>formatting</em></li></ul>',
                                   'scroll': 0, 'page_setup': None})
        # Retired media and old manifest backup must NOT escape a shared tab.
        project.asset_path('originals/deleted-private.pdf').write_bytes(b'PRIVATE OLD WORK')
        (project.path / 'project.v2.backup.json').write_text('{"secret":"old journal"}')
        project.save()
    original.save()
    return original, (first, second, third)


def test_inspection_and_single_tab_export_contains_all_content_and_no_private_files(tmp_path):
    source, ids = populated_notebook(tmp_path)
    try:
        infos = inspect_notebook(source.path)
        assert [t.title for t in infos] == ['Week 1', 'Week 2', 'Week 3']
        assert all(t.pages == 1 and t.notes_pages == 2 and t.bytes > 100 for t in infos)
        target = tmp_path/'Single week.yomunote'
        export_tabs(source.path, target, [ids[1]])
        exported = Notebook.load(target)
        try:
            assert len(exported.tabs) == 1
            assert exported.tabs[0]['title'] == 'Week 2'
            project = exported.project(exported.active_id)
            assert len(project.pages) == 1
            assert project.page_groups[0]['name'] == 'Chapter 1'
            assert len(project.annotations[next(iter(project.annotations))]) == 1
            assert len(project.read_page_ids) == 1
            assert '<b>Week 2 lecture</b>' in project.notes_html
            assert len(project.note_pages) == 2
            assert '<em>formatting</em>' in project.note_pages[1]['html']
            assert b'STUDY NOTES' in project.asset_path(project.pages[0]['source']).read_bytes()
            assert not project.asset_path('originals/deleted-private.pdf').exists()
            assert not (project.path / 'project.v2.backup.json').exists()
        finally:
            exported.close()
        with sqlite3.connect(target) as conn:
            paths = [x[0] for x in conn.execute('SELECT path FROM files')]
            assert len(paths) == 2  # project.json + the sole living PDF source
            assert all(ids[1] in s for s in paths)
            meta = json.loads(conn.execute('SELECT value FROM meta WHERE key=?',
                                           ('manifest',)).fetchone()[0])
            assert meta['app_version'] == __version__
            assert meta['version'] == 5
    finally:
        source.close()


def test_stage_import_and_one_batch_undo_redo_preserves_edits(tmp_path):
    source, ids = populated_notebook(tmp_path)
    receiving = Notebook.create(tmp_path / 'target', 'My semester')
    try:
        receiving.rename_tab(receiving.active_id, 'Week 2')  # collision
        existing = receiving.active_id
        stage, entries = stage_import(source.path, [ids[1], ids[2]],
                                      receiving.workspace,
                                      [t['title'] for t in receiving.tabs])
        assert [t['title'] for t in entries] == ['Week 2 (Imported)', 'Week 3']
        assert receiving.tabs == [{'id': existing, 'title': 'Week 2'}]
        assert {d.name for d in (stage/'tabs').iterdir()} == {e['id'] for e in entries}
        imported = commit_import(receiving, stage, entries)
        assert not stage.exists()
        assert len(receiving.tabs) == 3
        assert imported[0]['id'] != ids[1]
        rich = receiving.project(imported[0]['id'])
        assert '<b>Week 2 lecture</b>' in rich.notes_html
        rich.notes_html = '<p><strong>My edited notes</strong></p>'
        rich.note_pages[0]['html'] = rich.notes_html
        rich.save()
        receiving.save()
        set_batch_present(receiving, imported, False)
        assert [t['id'] for t in receiving.tabs] == [existing]
        # Still in working directory for in-session Redo, not in the SQLite file.
        assert (receiving.workspace/'tabs'/imported[0]['id']/'project.json').exists()
        reopened = Notebook.load(receiving.path)
        try:
            assert len(reopened.tabs) == 1
        finally:
            reopened.close()
        set_batch_present(receiving, imported, True, 1)
        assert len(receiving.tabs) == 3
        assert '<strong>My edited notes</strong>' in receiving.project(imported[0]['id']).notes_html
        reopened = Notebook.load(receiving.path)
        try:
            assert len(reopened.tabs) == 3
            assert reopened.project(imported[0]['id']).notes_html == rich.notes_html
        finally:
            reopened.close()
    finally:
        receiving.close()
        source.close()


def test_import_same_source_twice_creates_independent_tab_ids_and_names(tmp_path):
    source, ids = populated_notebook(tmp_path)
    receiver = Notebook.create(tmp_path/'receiver', 'Receiver')
    try:
        for _ in range(2):
            staged, entries = stage_import(source.path, [ids[0]], receiver.workspace,
                                           [t['title'] for t in receiver.tabs])
            commit_import(receiver, staged, entries)
        assert len({t['id'] for t in receiver.tabs}) == 3
        assert [t['title'] for t in receiver.tabs] == ['My Notes', 'Week 1', 'Week 1 (Imported)']
    finally:
        source.close()
        receiver.close()


def test_export_only_selected_tabs_even_if_other_pages_have_private_assets(tmp_path):
    src, ids = populated_notebook(tmp_path)
    try:
        destination = tmp_path/'Week 3 shared.yomunote'
        export_tabs(src.path, destination, [ids[2]])
        with sqlite3.connect(destination) as conn:
            paths = [row[0] for row in conn.execute('SELECT path FROM files')]
        assert paths and all(path.startswith(f'tabs/{ids[2]}/') for path in paths)
        with pytest.raises(FileExistsError):
            export_tabs(src.path, destination, [ids[1]])
        with pytest.raises(FileExistsError):
            export_tabs(src.path, src.path, [ids[1]])
    finally:
        src.close()


def test_invalid_selection_and_missing_asset_fail_before_modifying_destination(tmp_path):
    src, ids = populated_notebook(tmp_path)
    recv = Notebook.create(tmp_path/'receiving', 'Receiver')
    try:
        before = list(recv.tabs)
        with pytest.raises(ValueError, match='not in this notebook'):
            stage_import(src.path, ['a'*32], recv.workspace)
        with pytest.raises(ValueError, match='unique'):
            stage_import(src.path, [ids[0], ids[0]], recv.workspace)
        with sqlite3.connect(src.path) as conn:
            conn.execute('DELETE FROM files WHERE path=?',
                         (f'tabs/{ids[0]}/originals/week-1.pdf',))
        with pytest.raises(ValueError, match='missing required asset'):
            stage_import(src.path, [ids[0]], recv.workspace)
        assert recv.tabs == before
        assert not list(recv.workspace.glob('.tab-exchange-*'))
    finally:
        src.close()
        recv.close()


def test_failed_sqlite_commit_rolls_back_all_tab_changes(tmp_path, monkeypatch):
    src, ids = populated_notebook(tmp_path)
    recv = Notebook.create(tmp_path/'receiver', 'Receiver')
    try:
        stage, entries = stage_import(src.path, [ids[0]], recv.workspace)
        old = list(recv.tabs)
        real_save = recv.save
        monkeypatch.setattr(recv, 'save', lambda: (_ for _ in ()).throw(OSError('Disk full')))
        with pytest.raises(OSError, match='Disk full'):
            commit_import(recv, stage, entries)
        assert recv.tabs == old
        assert not (recv.workspace/'tabs'/entries[0]['id']).exists()
        monkeypatch.setattr(recv, 'save', real_save)
        assert len(Notebook.load(recv.path).tabs) == 1
    finally:
        recv.close()
        src.close()


def test_cancellation_does_not_leave_partial_export_or_staging(tmp_path):
    source, ids = populated_notebook(tmp_path)
    receiver = Notebook.create(tmp_path/'receiver', 'Receiver')
    try:
        cancel = threading.Event()
        cancel.set()
        with pytest.raises(RuntimeError, match='cancelled'):
            stage_import(source.path, [ids[0]], receiver.workspace, cancel=cancel)
        assert not list(receiver.workspace.glob('.tab-exchange-*'))
        destination = tmp_path/'Cancelled.yomunote'
        with pytest.raises(RuntimeError, match='cancelled'):
            export_tabs(source.path, destination, [ids[0]], cancel)
        assert not destination.exists()
    finally:
        receiver.close()
        source.close()


def test_gui_paths_and_version_are_wired_without_requiring_qt(tmp_path):
    source = Path(__file__).resolve().parents[1]/'yomunote'
    win = (source/'window.py').read_text(encoding='utf-8')
    ast.parse(win)
    ast.parse((source/'tab_exchange_dialog.py').read_text(encoding='utf-8'))
    assert 'Import Tabs from Notebook…' in win
    assert 'Export Selected Tabs as Notebook…' in win
    assert 'bar.notebookDropped.connect(self.import_notebook_tabs)' in win
    assert 'pane.notebookDropped.connect(self.import_notebook_tabs)' in win
    assert 'set_batch_present(destination_nb, imported, False)' in win
    assert 'self._notebook_history.record_applied(CallbackAction(' in win


def test_export_excludes_stale_blob_records_even_if_database_contains_them(tmp_path):
    source, ids = populated_notebook(tmp_path)
    try:
        with sqlite3.connect(source.path) as conn:
            tid = ids[0]
            for rel, payload in (
                (f'tabs/{tid}/originals/PRIVATE-OLD-NOTES.txt', b'SECRET_DELETED_LECTURE_NOTES'),
                (f'tabs/{tid}/project.v2.backup.json', b'{"secret":"old notes"}'),
            ):
                conn.execute('INSERT OR REPLACE INTO files(path,data,size,mtime_ns) VALUES(?,?,?,0)',
                             (rel, payload, len(payload)))
        path = tmp_path/'Privacy test.yomunote'
        export_tabs(source.path, path, [ids[0]])
        with sqlite3.connect(path) as conn:
            paths = [x[0] for x in conn.execute('SELECT path FROM files')]
            assert len(paths) == 2
            assert all('PRIVATE' not in rel and 'backup' not in rel for rel in paths)
        assert b'SECRET_DELETED_LECTURE_NOTES' not in path.read_bytes()
    finally:
        source.close()


def test_malicious_page_path_is_rejected_by_inspector_and_stage(tmp_path):
    source, ids = populated_notebook(tmp_path)
    receiving = Notebook.create(tmp_path/'target', 'Target')
    try:
        with sqlite3.connect(source.path) as conn:
            rel = f'tabs/{ids[0]}/project.json'
            item = json.loads(conn.execute('SELECT data FROM files WHERE path=?',
                                           (rel,)).fetchone()[0])
            item['pages'][0]['source'] = 'originals/../../private.txt'
            content = json.dumps(item).encode('utf-8')
            conn.execute('UPDATE files SET data=?,size=? WHERE path=?',
                         (content, len(content), rel))
        with pytest.raises(ValueError, match='(Unsafe|asset|path)'):
            inspect_notebook(source.path)
        with pytest.raises(ValueError, match='(Unsafe|asset|path)'):
            stage_import(source.path, [ids[0]], receiving.workspace)
        assert not list(receiving.workspace.glob('.tab-exchange-*'))
    finally:
        receiving.close()
        source.close()


def test_undo_failure_preserves_live_tab_manifest(tmp_path, monkeypatch):
    source, ids = populated_notebook(tmp_path)
    receiving = Notebook.create(tmp_path/'target', 'Target')
    try:
        stage, entries = stage_import(source.path, [ids[0]], receiving.workspace)
        imported = commit_import(receiving, stage, entries)
        before = list(receiving.tabs)
        previous = receiving.active_id
        real_save = receiving.save
        monkeypatch.setattr(receiving, 'save', lambda: (_ for _ in ()).throw(OSError('Disk full')))
        with pytest.raises(OSError, match='Disk full'):
            set_batch_present(receiving, imported, False)
        assert receiving.tabs == before
        assert receiving.active_id == previous
        monkeypatch.setattr(receiving, 'save', real_save)
        loaded = Notebook.load(receiving.path)
        try:
            assert len(loaded.tabs) == 2
        finally:
            loaded.close()
    finally:
        receiving.close()
        source.close()


def test_cancel_mid_stream_drops_partial_staging_files(tmp_path):
    source, ids = populated_notebook(tmp_path)
    receiving = Notebook.create(tmp_path/'target', 'Target')
    try:
        class CancelAfterFirstChunk:
            def __init__(self):
                self.calls = 0
            def is_set(self):
                self.calls += 1
                # Called first between tabs, again in individual blob chunks.
                return self.calls > 2
        with pytest.raises(RuntimeError, match='cancelled'):
            stage_import(source.path, [ids[0]], receiving.workspace,
                         cancel=CancelAfterFirstChunk())
        assert not list(receiving.workspace.glob('.tab-exchange-*'))
    finally:
        receiving.close()
        source.close()
