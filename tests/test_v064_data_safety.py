"""Real storage and PDFium regression tests for the v0.6.4 safety release.

These tests run WITHOUT the Qt graphical interface.
They use tiny fake notebook files, never personal documents.
"""

import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import threading
import types

import pytest

from yomunote.importers import _index_pdf
from yomunote.notebook import Notebook
from yomunote.pdfium_guard import PDFIUM_LOCK
from yomunote.project import Project


def _entries(db):
    with sqlite3.connect(db) as conn:
        return {row[0] for row in conn.execute('SELECT path FROM files')}


def test_pdf_index_uses_shared_lock_through_document_close(monkeypatch):
    """The PDF indexer must wait while another thread renders."""
    entered = threading.Event()

    class FakeDocument:
        def __init__(self, path):
            entered.set()

        def __len__(self):
            return 2

        def close(self):
            assert PDFIUM_LOCK._is_owned()

    monkeypatch.setitem(sys.modules, 'pypdfium2',
                        types.SimpleNamespace(PdfDocument=FakeDocument))
    errors = []

    def worker():
        try:
            assert len(_index_pdf(Path('fake.pdf'), 'originals/a.pdf',
                                  'originals/a.pdf', 'Test')) == 2
        except Exception as exc:
            errors.append(exc)

    PDFIUM_LOCK.acquire()
    try:
        thread = threading.Thread(target=worker)
        thread.start()
        assert not entered.wait(0.15), 'Indexing bypassed the PDFium lock'
    finally:
        PDFIUM_LOCK.release()
    thread.join(timeout=3)
    assert not thread.is_alive()
    assert not errors
    assert entered.is_set()


def test_removed_files_and_annotations_not_packaged_but_undo_survives(tmp_path):
    nb = Notebook.create(tmp_path, 'Remove Safely')
    try:
        page_id = 'lecture-page'
        source = 'originals/confidential.pdf'
        p = nb.project(nb.active_id)
        p.pages = [{'id': page_id, 'kind': 'pdf',
                    'title': 'Lecture', 'source': source,
                    'render_source': source, 'source_page': 1}]
        p.asset_path(source).write_bytes(b'SECRET_CONTENT_ONLY_FOR_TEST')
        mark = {'kind': 'highlight', 'x': .1, 'y': .1,
                'w': .3, 'h': .1, 'color': '#ffcf69'}
        p.annotations = {page_id: [mark]}
        p.save()
        nb.save()
        rel = f'tabs/{nb.active_id}/{source}'
        assert rel in _entries(nb.path)
        # Removing the page does not delete its undo source in memory.
        saved_page = p.pages.pop()
        p.save()
        nb.save()
        assert rel not in _entries(nb.path)
        assert p.asset_path(source).is_file()
        with sqlite3.connect(nb.path) as conn:
            raw = conn.execute('SELECT data FROM files WHERE path=?',
                (f'tabs/{nb.active_id}/project.json',)).fetchone()[0]
        assert page_id not in json.loads(raw)['annotations']
        # Undo while the notebook remains open restores the old file.
        p.pages.append(saved_page)
        p.save()
        nb.save()
        assert rel in _entries(nb.path)
    finally:
        nb.close()


def test_clean_copy_compacts_db_and_has_a_new_identity(tmp_path):
    nb = Notebook.create(tmp_path, 'Share')
    try:
        old_id = nb.identifier
        output = tmp_path / 'Share Clean Copy.yomunote'
        result = Notebook.create_clean_share_copy(nb.path, output)
        assert result == output
        assert output.exists()
        clean = Notebook.load(output)
        try:
            assert clean.identifier != old_id
        finally:
            clean.close()
        with pytest.raises(FileExistsError):
            Notebook.create_clean_share_copy(nb.path, output)
    finally:
        nb.close()


def test_corrupted_mark_recovery_preserves_original_notebook(tmp_path):
    nb = Notebook.create(tmp_path, 'Recovery')
    tab = nb.active_id
    p = nb.project(tab)
    p.pages = [{'id': 'p', 'title': 'A', 'kind': 'blank'}]
    p.notes_html = '<p>Keep these notes safe.</p>'
    p.save()
    nb.save()
    original = nb.path
    nb.close()

    # Make only the stroke invalid, as if one saved record was damaged.
    relative = f'tabs/{tab}/project.json'
    with sqlite3.connect(original) as conn:
        payload = json.loads(conn.execute(
            'SELECT data FROM files WHERE path=?', (relative,)).fetchone()[0])
        payload['annotations'] = {'p': [
            {'kind': 'stroke', 'id': 'bad', 'points': [[-1, 0], [.2, .2]],
             'color': '#000000', 'width': .01},
        ]}
        blob = json.dumps(payload).encode('utf-8')
        conn.execute('UPDATE files SET data=?,size=? WHERE path=?',
                     (blob, len(blob), relative))
    old_hash = hashlib.sha256(original.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match='Invalid vector stroke'):
        Notebook.load(original)

    recovered = Notebook.recover_copy(original)
    try:
        assert recovered.path != original
        assert recovered.recovery_warnings
        repaired = recovered.project(tab)
        assert repaired.notes_html == '<p>Keep these notes safe.</p>'
        assert not repaired.annotations.get('p')
    finally:
        recovered.close()
    assert hashlib.sha256(original.read_bytes()).hexdigest() == old_hash


@pytest.mark.parametrize('part', ['D:secrets', 'CON.txt', 'NUL', 'file:stream',
                                   'trailing.', 'trailing '])
def test_untrusted_windows_paths_rejected_on_every_platform(tmp_path, part):
    nb = Notebook.create(tmp_path, 'Reject Paths')
    tab = nb.active_id
    path = nb.path
    nb.close()
    with sqlite3.connect(path) as conn:
        conn.execute('INSERT INTO files(path,data,size,mtime_ns) VALUES(?,?,?,?)',
                     (f'tabs/{tab}/originals/{part}', b'bad', 3, 99))
    with pytest.raises(ValueError, match='Unsafe notebook entry path'):
        Notebook.load(path)


def test_manifest_content_change_detected_when_timestamp_and_size_same(tmp_path):
    nb = Notebook.create(tmp_path, 'Timestamp')
    try:
        p = nb.project(nb.active_id)
        p.notes_html = 'ONE'
        p.save()
        nb.save()
        file = p.path / 'project.json'
        previous = file.stat()
        p.notes_html = 'TWO'
        p.save()
        # Emulate a filesystem with coarse timestamps.
        assert file.stat().st_size == previous.st_size
        os.utime(file, ns=(previous.st_mtime_ns, previous.st_mtime_ns))
        assert nb.save() is True
        with sqlite3.connect(nb.path) as conn:
            raw = conn.execute('SELECT data FROM files WHERE path=?',
                (f'tabs/{nb.active_id}/project.json',)).fetchone()[0]
        assert json.loads(raw)['notes_html'] == 'TWO'
    finally:
        nb.close()
