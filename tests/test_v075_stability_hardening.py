"""v0.7.5 limited stability fixes: platform-safe paths and bounded bookkeeping."""
from pathlib import Path
import pytest

from yomunote.notebook import _safe_relative, _safe_file_segment
from yomunote.project import validate_relpath
from yomunote import importers

TAB_ID = 'a' * 32

@pytest.mark.parametrize('bad', ['foo?.pdf','foo*.pdf','foo<bar.pdf','foo>bar.pdf',
                                  'foo"bar.pdf','foo|bar.pdf','CON.txt','foo:stream','bad.'])
def test_windows_unsafe_paths_are_rejected_on_every_platform(bad):
    assert not _safe_file_segment(bad)
    with pytest.raises(ValueError):
        validate_relpath('originals/' + bad)
    with pytest.raises(ValueError):
        _safe_relative('tabs/' + TAB_ID + '/originals/' + bad, {TAB_ID})

def test_existing_valid_asset_paths_are_unchanged():
    assert validate_relpath('originals/abc_123.pdf') == Path('originals/abc_123.pdf')
    assert _safe_relative('tabs/' + TAB_ID + '/originals/abc_123.pdf', {TAB_ID})

def test_cache_folder_bookkeeping_has_a_hard_bound():
    assert importers._CACHE_WRITE_TRACKING_LIMIT <= 1024
    assert len(importers._CACHE_WRITES) <= importers._CACHE_WRITE_TRACKING_LIMIT


def test_streamed_asset_truncation_rolls_back_sqlite_transaction(tmp_path, monkeypatch):
    """A short source read must not commit a corrupt/incomplete notebook."""
    import io
    import os
    import sqlite3
    from yomunote.notebook import Notebook
    from yomunote.project import short_id

    nb = Notebook.create(tmp_path, 'Stream Safety')
    try:
        project = nb.project(nb.active_id)
        rel = 'originals/sample.pdf'
        asset = project.asset_path(rel)
        asset.write_bytes(b'A' * 4096)
        project.pages.append({
            'id': short_id(), 'title': 'Sample', 'source': rel,
            'render_source': rel, 'source_page': 1, 'kind': 'pdf',
        })
        project.save()
        assert nb.save()
        with sqlite3.connect(nb.path) as db:
            before = db.execute('SELECT data FROM files WHERE path=?',
                                (f'tabs/{nb.active_id}/{rel}',)).fetchone()[0]
        assert before == b'A' * 4096

        # Force a detectable mtime change even on coarse-resolution disks.
        saved_mtime_ns = asset.stat().st_mtime_ns
        asset.write_bytes(b'B' * 4096)
        changed_stat = asset.stat()
        os.utime(asset, ns=(changed_stat.st_atime_ns, saved_mtime_ns + 2_000_000_000))
        assert asset.stat().st_mtime_ns != saved_mtime_ns
        # Windows 8.3 paths and macOS /var -> /private/var aliases may differ.
        asset_real_path = asset.resolve()
        native_open = Path.open

        def short_read(self, mode='r', *args, **kwargs):
            if mode == 'rb' and self.resolve() == asset_real_path:
                return io.BytesIO(b'B' * 64)
            return native_open(self, mode, *args, **kwargs)

        with monkeypatch.context() as patch:
            patch.setattr(Path, 'open', short_read)
            with pytest.raises(IOError, match='truncated during save'):
                nb.save()
        with sqlite3.connect(nb.path) as db:
            after = db.execute('SELECT data FROM files WHERE path=?',
                               (f'tabs/{nb.active_id}/{rel}',)).fetchone()[0]
        assert after == before
    finally:
        nb.close()


def test_clean_share_copy_excludes_historic_migration_notes(tmp_path):
    """Private old manifest text must never ride along in a clean share export."""
    import sqlite3
    from yomunote.notebook import Notebook

    nb = Notebook.create(tmp_path, 'Share Private')
    try:
        backup_path = f'tabs/{nb.active_id}/project.v3.backup.json'
        secret = b'{"notes_html":"HISTORIC PRIVATE NOTES"}'
        with sqlite3.connect(nb.path) as db:
            db.execute('INSERT INTO files(path,data,size,mtime_ns) VALUES(?,?,?,?)',
                       (backup_path, secret, len(secret), 0))
        cleaned = tmp_path / 'Safe Share.yomunote'
        Notebook.create_clean_share_copy(nb.path, cleaned)
        with sqlite3.connect(cleaned) as db:
            assert db.execute('SELECT COUNT(*) FROM files WHERE path=?',
                              (backup_path,)).fetchone()[0] == 0
        with sqlite3.connect(nb.path) as db:
            assert db.execute('SELECT data FROM files WHERE path=?',
                              (backup_path,)).fetchone()[0] == secret
        # VACUUM must also remove the old contents from unused database pages.
        assert b'HISTORIC PRIVATE NOTES' not in cleaned.read_bytes()
    finally:
        nb.close()
