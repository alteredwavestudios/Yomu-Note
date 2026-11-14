"""Safe, offline sharing of whole tabs between v5 Yomu Note notebooks.

This module is intentionally Qt-free: all SQL/JSON checks and large asset copies
can be run by a worker without creating QWidget/QPixmap objects. Source notebooks
are opened READ-ONLY; only *selected* tabs are copied. No legacy manifest backups,
deleted assets or raster caches cross into a shared notebook.

The receiving Notebook has three distinct states:
  1. staged temporary files (not in the notebook or Undo history);
  2. committed tabs (SQLite and the visible tab list agree);
  3. undone tabs (SQLite no longer exports them, workspace retains their files
     until the notebook is closed so Redo can restore even edited documents).
"""
from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import uuid

from . import __version__
from .notebook import (Notebook, MAX_ASSET_BYTES, MAX_TABS, MAGIC_FORMAT,
                       NOTEBOOK_VERSION, _safe_relative)
from .project import Project, FORMAT_VERSION, validate_relpath, short_id, safe_name

MAX_TRANSFER_BYTES = 4 * 1024 * 1024 * 1024  # guard against huge untrusted shares
MAX_FILES = 100_000
MANIFEST_MAX = 32 * 1024 * 1024
CHUNK = 1024 * 1024


@dataclass(frozen=True)
class SharedTab:
    """One row in the import dialog's read-only summary.

    ``frozen=True`` prevents accidentally changing inspected source data.
    This is only metadata: PDF contents are copied later in stage_import().
    """
    id: str
    title: str
    pages: int
    notes_pages: int
    bytes: int


def _connect_readonly(source: Path):
    """Connect to a shared notebook without ever creating/changing it.

    Normally ``sqlite3.connect`` creates a new database if a file is missing;
    URI ``mode=ro`` prevents that dangerous surprise on typoed filenames.
    """
    path = Path(source).expanduser().resolve()
    if not path.is_file() or path.suffix.lower() not in ('.yomunote', '.yominote'):
        raise ValueError('Choose a supported .yomunote notebook file.')
    # The SQLite URI, not a normal connect(), is essential: accidentally
    # creating a new file instead of reading the share must be impossible.
    return sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)


def _manifest(conn):
    """Read the notebook's table of contents, with a size check FIRST.

    SQL ``length`` can inspect a very large value without first returning
    its contents to Python. This matters because shared files are untrusted.
    """
    try:
        metadata_size = conn.execute(
            'SELECT length(value) FROM meta WHERE key=?', ('manifest',)
        ).fetchone()
        if not metadata_size or type(metadata_size[0]) is not int or not 0 < metadata_size[0] <= MANIFEST_MAX:
            raise ValueError('Shared notebook has no valid manifest.')
        row = conn.execute('SELECT value FROM meta WHERE key=?', ('manifest',)).fetchone()
        if not row or not isinstance(row[0], str) or len(row[0]) > MANIFEST_MAX:
            raise ValueError('Shared notebook has no valid manifest.')
        meta = json.loads(row[0])
        Notebook._check_manifest(meta)
        return meta
    except (sqlite3.DatabaseError, json.JSONDecodeError, TypeError) as exc:
        raise ValueError('Shared notebook has an invalid manifest.') from exc


def _project_data(conn, tabid):
    """Read ONE tab's JSON only after checking its real BLOB byte length.

    ``size`` is a claim made by the notebook file, not trustworthy evidence.
    Checking ``length(data)`` also protects against a dishonest size field.
    """
    rel = f'tabs/{tabid}/project.json'
    try:
        sizes = conn.execute('SELECT size,length(data) FROM files WHERE path=?', (rel,)).fetchone()
        if (not sizes or type(sizes[0]) is not int or type(sizes[1]) is not int
                or not 0 < sizes[0] <= MANIFEST_MAX or sizes[0] != sizes[1]):
            raise ValueError('A shared tab is missing its project metadata.')
        row = conn.execute('SELECT data,size FROM files WHERE path=?', (rel,)).fetchone()
        if not row or type(row[1]) is not int or not 0 < row[1] <= MANIFEST_MAX:
            raise ValueError('A shared tab is missing its project metadata.')
        if not isinstance(row[0], bytes) or len(row[0]) != row[1]:
            raise ValueError('Shared project metadata is damaged.')
        data = json.loads(row[0].decode('utf-8'))
        if not isinstance(data, dict) or not isinstance(data.get('pages'), list):
            raise ValueError('Invalid shared project metadata.')
        if len(data['pages']) > 20_000:
            raise ValueError('A shared tab has too many pages.')
        return data
    except (sqlite3.DatabaseError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError('Could not read shared tab metadata.') from exc


def _referenced_assets(data, tabid):
    """Build an allowlist from LIVE page references, never from stored orphans."""
    assets = {f'tabs/{tabid}/project.json'}
    for page in data['pages']:
        if not isinstance(page, dict):
            raise ValueError('Invalid shared page entry.')
        for field in ('source', 'render_source', 'file'):
            value = page.get(field)
            if not value:
                continue
            rel = validate_relpath(value)
            if rel.parts[0] not in ('originals', 'pages'):
                raise ValueError('Shared page refers to an unsupported asset folder.')
            combined = f'tabs/{tabid}/{rel.as_posix()}'
            _safe_relative(combined, {tabid})
            assets.add(combined)
    return assets


def _selected_manifest(conn, tab_ids):
    """Return selected source tabs in their actual notebook-bar order."""
    meta = _manifest(conn)
    by_id = {tab['id']: tab for tab in meta['tabs']}
    if not isinstance(tab_ids, (tuple, list)) or not tab_ids or len(set(tab_ids)) != len(tab_ids):
        raise ValueError('Select at least one unique tab.')
    if any(not isinstance(tid, str) or tid not in by_id for tid in tab_ids):
        raise ValueError('A selected tab is not in this notebook.')
    # Preserve ORIGINAL source order, irrespective of order clicked in the UI.
    return meta, [tab for tab in meta['tabs'] if tab['id'] in set(tab_ids)]


def _check_transfer_inventory(conn, selected):
    """Validate the complete batch BEFORE creating/copying large files.

    The notebook's own ``size`` values may be falsified. Comparing them to
    SQLite's actual BLOB lengths closes that loophole and prevents a late
    disk-space surprise when the transfer was already mostly complete.
    Referenced assets are sets, so 100 PDF pages sharing one PDF count once.
    """
    paths = set()
    total_bytes = 0
    for tab in selected:
        project_data = _project_data(conn, tab['id'])
        for rel in _referenced_assets(project_data, tab['id']):
            if rel in paths:
                continue
            row = conn.execute(
                'SELECT size,length(data) FROM files WHERE path=?', (rel,)
            ).fetchone()
            if (not row or type(row[0]) is not int or type(row[1]) is not int
                    or not 0 <= row[0] <= MAX_ASSET_BYTES or row[0] != row[1]):
                raise ValueError('Shared notebook is missing required asset or its stored size is invalid.')
            paths.add(rel)
            total_bytes += row[0]
            if total_bytes > MAX_TRANSFER_BYTES or len(paths) > MAX_FILES:
                raise ValueError('Notebook exchange exceeds safe size or file-count limits.')
    return paths


def inspect_notebook(source: Path) -> list[SharedTab]:
    """Read the tab catalogue without extracting media or opening PDF renderers."""
    try:
        with closing(_connect_readonly(source)) as conn:
            meta = _manifest(conn)
            tabs = []
            for tab in meta['tabs']:
                tid = tab['id']
                data = _project_data(conn, tid)
                paths = _referenced_assets(data, tid)
                total = 0
                for rel in paths:
                    row = conn.execute('SELECT size FROM files WHERE path=?', (rel,)).fetchone()
                    if row is None or type(row[0]) is not int or not 0 <= row[0] <= MAX_ASSET_BYTES:
                        raise ValueError(f'Missing or invalid file in tab: {tab["title"]}')
                    total += row[0]
                    if total > MAX_TRANSFER_BYTES:
                        raise ValueError('Selected tab exceeds the 4 GB sharing safety limit.')
                note_pages = data.get('note_pages')
                count = len(note_pages) if isinstance(note_pages, list) else 1
                tabs.append(SharedTab(tid, tab['title'], len(data['pages']), count, total))
            return tabs
    except sqlite3.DatabaseError as exc:
        raise ValueError('Could not read this notebook. It may be damaged.') from exc


def _stream_row(conn, rel, dest, cancel=None):
    """Copy one verified blob with bounded RAM; do not trust its row name."""
    row = conn.execute('SELECT rowid,size,mtime_ns FROM files WHERE path=?', (rel,)).fetchone()
    if not row or type(row[1]) is not int or not 0 <= row[1] <= MAX_ASSET_BYTES:
        raise ValueError(f'Shared notebook is missing required asset: {rel}')
    rowid, size, mtime = row
    dest.parent.mkdir(parents=True, exist_ok=True)
    with conn.blobopen('files', 'data', rowid, readonly=True) as blob, dest.open('xb') as out:
        if len(blob) != size:
            raise ValueError(f'Shared asset length is invalid: {rel}')
        remaining = size
        while remaining:
            if cancel is not None and cancel.is_set():
                raise RuntimeError('Tab transfer cancelled.')
            chunk = blob.read(min(CHUNK, remaining))
            if not chunk:
                raise ValueError(f'Shared asset is truncated: {rel}')
            out.write(chunk)
            remaining -= len(chunk)
        out.flush()
    # File timestamps may be negative or absurd in untrusted notebooks.
    if type(mtime) is int and 0 <= mtime <= 9_223_372_036_854_775_807:
        os.utime(dest, ns=(mtime, mtime))
    return size


def _independent_title(title, used):
    """Resolve duplicate visible names without ever merging tab contents.

    A classmate's Week 3 and your Week 3 may be completely different notes.
    Their internal IDs remain independent; this only changes the label.
    """
    if title not in used:
        used.add(title)
        return title
    stem = title[:87].rstrip()
    proposed = stem + ' (Imported)'
    n = 2
    while proposed in used:
        proposed = f'{stem[:80]} (Imported {n})'
        n += 1
    used.add(proposed)
    return proposed


def stage_import(source: Path, tab_ids: list[str], workspace: Path,
                 existing_titles=(), cancel=None) -> tuple[Path, list[dict]]:
    """Copy selected live assets into an uncommitted staging folder.

    Caller OWNS the returned staging directory and must delete it after commit
    or cancellation. No destination Notebook state is changed here.
    """
    workspace = Path(workspace).resolve()
    if not workspace.is_dir():
        raise ValueError('The destination notebook workspace no longer exists.')
    stage = Path(tempfile.mkdtemp(prefix='.tab-exchange-', dir=workspace))
    entries = []
    used = set(existing_titles)
    total = 0
    count = 0
    try:
        with closing(_connect_readonly(source)) as conn:
            # A snapshot keeps the source internally consistent across a long
            # transfer, even if another app tries to save it simultaneously.
            conn.execute('BEGIN')
            _meta, selected = _selected_manifest(conn, tab_ids)
            if len(selected) > MAX_TABS:
                raise ValueError('Too many selected tabs.')
            # Fail before creating any large staged files if the entire batch
            # is too big, has missing assets, or lies about its BLOB sizes.
            _check_transfer_inventory(conn, selected)
            for tab in selected:
                if cancel is not None and cancel.is_set():
                    raise RuntimeError('Tab transfer cancelled.')
                old_id = tab['id']
                new_id = uuid.uuid4().hex
                new_title = _independent_title(tab['title'], used)
                data = _project_data(conn, old_id)
                assets = _referenced_assets(data, old_id)
                base = stage / 'tabs' / new_id
                for rel in sorted(assets):
                    local = _safe_relative(rel, {old_id})
                    output = base.joinpath(*local.parts[2:])
                    total += _stream_row(conn, rel, output, cancel)
                    count += 1
                    if total > MAX_TRANSFER_BYTES or count > MAX_FILES:
                        raise ValueError('Notebook exchange exceeds safe size or file-count limits.')
                project = Project.load(base)  # validate notes, groups and annotations
                # All live page sources must actually have arrived.
                for item in project.pages:
                    for field in ('source', 'render_source', 'file'):
                        if item.get(field) and not project.asset_path(item[field]).is_file():
                            raise ValueError('The shared tab has a missing original document.')
                # Give the independent copy a new project identity as well as a
                # new container tab ID. Keep every page/mark/note ID unchanged.
                project.identifier = short_id()
                project.name = new_title
                project.loaded_version = FORMAT_VERSION
                project.save(prune_orphan_annotations=True)
                entries.append({'id': new_id, 'title': new_title})
            conn.rollback()
        return stage, entries
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def commit_import(notebook: Notebook, stage: Path, entries: list[dict]):
    """All-or-nothing filesystem+SQLite commit; call on owning UI thread.

    SQLite writes are transactional. If they fail, restore the original tab
    manifest and remove staged tab folders so a retry is safe.
    """
    if notebook._closed:
        raise RuntimeError('Destination notebook has been closed.')
    if not entries or len(entries) + len(notebook.tabs) > MAX_TABS:
        raise ValueError('Cannot import: destination tab limit would be exceeded.')
    if any(t['id'] in {x['id'] for x in notebook.tabs} for t in entries):
        raise ValueError('Imported tab identity collision.')
    before_tabs = [dict(t) for t in notebook.tabs]
    before_active = notebook.active_id
    moved = []
    try:
        # A duplicated tab name may have appeared while staging was running;
        # rename the staged project before the commit rather than overwriting.
        used = {t['title'] for t in notebook.tabs}
        for entry in entries:
            title = _independent_title(entry['title'], used)
            if title != entry['title']:
                source_dir = Path(stage) / 'tabs' / entry['id']
                p = Project.load(source_dir)
                p.name = title
                p.save(prune_orphan_annotations=True)
                entry['title'] = title
            src = Path(stage) / 'tabs' / entry['id']
            dest = notebook.workspace / 'tabs' / entry['id']
            if dest.exists() or not src.is_dir():
                raise ValueError('Staged tab is missing or already exists.')
            src.rename(dest)  # same workspace volume; no re-copy of PDFs
            moved.append(dest)
        notebook.tabs.extend(dict(e) for e in entries)
        notebook.active_id = entries[-1]['id']
        notebook.save()
    except Exception:
        notebook.tabs = before_tabs
        notebook.active_id = before_active
        # The database transaction has already rolled back if a save failed.
        for dest in reversed(moved):
            try:
                dest.rename(Path(stage) / 'tabs' / dest.name)
            except OSError:
                # If a file is locked on Windows, leave it OUTSIDE the live
                # manifest; the caller can inspect or retry cleanup.
                pass
        raise
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    return [dict(e) for e in entries]


def set_batch_present(notebook: Notebook, entries: list[dict], present: bool,
                      restore_index: int | None = None):
    """Atomically show/hide one imported batch for Undo/Redo.

    Undo does not delete source assets from the workspace. Redo therefore
    restores whatever edits the user made before undoing the batch.
    """
    before = [dict(t) for t in notebook.tabs]
    active_before = notebook.active_id
    ids = {t['id'] for t in entries}
    if present:
        if ids & {t['id'] for t in notebook.tabs}:
            raise ValueError('Cannot redo: an imported tab is already present.')
        if len(notebook.tabs) + len(entries) > MAX_TABS:
            raise ValueError('Cannot redo: tab limit exceeded.')
        index = len(notebook.tabs) if restore_index is None else min(max(0, restore_index), len(notebook.tabs))
        notebook.tabs[index:index] = [dict(t) for t in entries]
        notebook.active_id = entries[-1]['id']
    else:
        if not ids.issubset({t['id'] for t in notebook.tabs}):
            raise ValueError('Cannot undo: imported tabs are missing.')
        if len(notebook.tabs) <= len(entries):
            raise ValueError('A notebook must keep at least one tab.')
        notebook.tabs = [t for t in notebook.tabs if t['id'] not in ids]
        if notebook.active_id in ids:
            notebook.active_id = next((t['id'] for t in before if t['id'] not in ids), notebook.tabs[0]['id'])
    try:
        notebook.save()
    except Exception:
        notebook.tabs = before
        notebook.active_id = active_before
        raise


def export_tabs(source: Path, destination: Path, tab_ids: list[str], cancel=None):
    """Stream selected live assets into a new standalone privacy-clean notebook.

    Exports only the current on-disk snapshot. The UI must save all visible
    tabs BEFORE launching this function in its background worker.
    """
    source = Path(source).expanduser().resolve()
    destination = Path(destination).expanduser().resolve()
    if source == destination or destination.exists():
        raise FileExistsError('Choose a NEW file name for the exported notebook.')
    if destination.suffix.lower() != '.yomunote':
        raise ValueError('Export file must use the .yomunote extension.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name('.' + destination.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with closing(_connect_readonly(source)) as src:
            src.execute('BEGIN')
            meta, selected = _selected_manifest(src, tab_ids)
            # Inspect every referenced asset before creating the exported
            # database. Never rely on the untrusted "size" column alone.
            assets = _check_transfer_inventory(src, selected)
            total = 0
            with closing(sqlite3.connect(temporary)) as dest:
                dest.execute('PRAGMA synchronous=FULL')
                with dest:
                    dest.execute('CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
                    dest.execute('CREATE TABLE files (path TEXT PRIMARY KEY, data BLOB NOT NULL, size INTEGER NOT NULL, mtime_ns INTEGER NOT NULL)')
                    manifest = {'format': MAGIC_FORMAT, 'version': NOTEBOOK_VERSION,
                                'app_version': __version__, 'id': uuid.uuid4().hex,
                                'name': safe_name(destination.stem),
                                'tabs': [dict(t) for t in selected],
                                'active_id': selected[0]['id']}
                    Notebook._check_manifest(manifest)
                    dest.execute('INSERT INTO meta(key,value) VALUES(?,?)',
                                 ('manifest', json.dumps(manifest, ensure_ascii=False, sort_keys=True)))
                    for rel in sorted(assets):
                        if cancel is not None and cancel.is_set():
                            raise RuntimeError('Tab export cancelled.')
                        _safe_relative(rel, {t['id'] for t in selected})
                        row = src.execute('SELECT rowid,size,mtime_ns FROM files WHERE path=?', (rel,)).fetchone()
                        if not row or type(row[1]) is not int or not 0 <= row[1] <= MAX_ASSET_BYTES:
                            raise ValueError('Selected tab is missing a referenced asset.')
                        rid, size, mtime = row
                        total += size
                        if total > MAX_TRANSFER_BYTES:
                            raise ValueError('The tab export exceeds the 4 GB safety limit.')
                        dest.execute('INSERT INTO files(path,data,size,mtime_ns) VALUES(?,zeroblob(?),?,?)',
                                     (rel, size, size, int(mtime)))
                        out_id = dest.execute('SELECT rowid FROM files WHERE path=?', (rel,)).fetchone()[0]
                        with src.blobopen('files', 'data', rid, readonly=True) as inp, dest.blobopen('files', 'data', out_id) as out:
                            if len(inp) != size:
                                raise ValueError('Source asset length changed during export.')
                            remaining = size
                            while remaining:
                                if cancel is not None and cancel.is_set():
                                    raise RuntimeError('Tab export cancelled.')
                                part = inp.read(min(CHUNK, remaining))
                                if not part:
                                    raise ValueError('Source asset truncated during export.')
                                out.write(part)
                                remaining -= len(part)
                # PRAGMA returns result rows. Merely calling execute() does
                # NOT check whether SQLite found any corruption.
                integrity = dest.execute('PRAGMA quick_check').fetchone()
                if integrity != ('ok',):
                    raise ValueError('The exported notebook failed its SQLite integrity check.')
            src.rollback()
        if cancel is not None and cancel.is_set():
            raise RuntimeError('Tab export cancelled.')
        # Atomically create a NEW destination. os.replace() would overwrite a
        # filename another process created after our initial existence check.
        # A hard link creates the name exclusively and costs no extra PDF copy.
        try:
            os.link(temporary, destination)
        except FileExistsError:
            raise FileExistsError('Export target already exists; original preserved.')
        except OSError:
            # ExFAT/network volumes may not support hard links. Exclusive 'xb'
            # still prevents overwrite; use bounded streaming in that case.
            if destination.exists():
                raise FileExistsError('Export target already exists; original preserved.')
            created = False
            try:
                # 'xb' is exclusive. Only clean up if WE successfully created
                # the file; otherwise a simultaneous user's file is theirs.
                with destination.open('xb') as new_file:
                    created = True
                    with temporary.open('rb') as existing:
                        shutil.copyfileobj(existing, new_file, CHUNK)
                    new_file.flush()
                    os.fsync(new_file.fileno())
            except Exception:
                if created:
                    destination.unlink(missing_ok=True)
                raise
        return destination
    except sqlite3.DatabaseError as exc:
        raise ValueError('The source notebook is damaged or incomplete.') from exc
    finally:
        temporary.unlink(missing_ok=True)
