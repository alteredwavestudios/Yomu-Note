"""Yomu Note v5 notebook container: one portable, incremental SQLite file.

Each tab uses an ordinary v4 Project in a temporary working directory. PDF
raster caches never enter the container or its backup snapshots. Only altered
source files/manifests are written to SQLite on each debounce save, so saving
huge PDFs does NOT require re-zipping the entire notebook.

The on-disk format is deliberately distinct from legacy v2-v4 .yominote
DIRECTORIES. Opening a legacy directory creates a new v5 FILE alongside it;
legacy sources are never overwritten or deleted.
"""
from __future__ import annotations

import json
import hashlib
import re
import copy
import os
import shutil
import sqlite3
import tempfile
from contextlib import closing
import uuid
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .project import Project, safe_name, unique_project_path, short_id

NOTEBOOK_VERSION = 5
MAGIC_FORMAT = 'yomu-notebook'
MAX_TABS = 256
MAX_ASSET_BYTES = 1024 * 1024 * 1024
BACKUP_STORAGE_SAFETY_BYTES = 2 * 1024 * 1024 * 1024
# Untrusted notebook files may lie about record counts/sizes. These are
# generous upper limits on the TEMPORARY extraction workspace, not limits on
# how much free space a user may have on their computer. They prevent a
# deliberately crafted notebook from filling a disk with millions of entries.
MAX_LOADED_FILES = 200_000
MAX_LOADED_BYTES = 32 * 1024 * 1024 * 1024
MAX_MANIFEST_BYTES = 32 * 1024 * 1024

# These names are reserved by Windows, even with a file extension.
# We reject them on every OS so notebooks stay portable.
_WINDOWS_RESERVED = re.compile(
    r'^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?$',
    re.IGNORECASE,
)


def _safe_file_segment(part: str) -> bool:
    """Check one path component before creating a file.

    A component is just the text between two '/' characters.
    ':' is dangerous on Windows because it can name a drive
    or an alternate data stream, not an ordinary file.
    """
    return (
        part not in ('', '.', '..')
        and not any(ord(char) < 32 for char in part)
        and not any(char in part for char in '<>:"|?*')
        and not part.endswith((' ', '.'))
        and not _WINDOWS_RESERVED.fullmatch(part)
    )



def _safe_tab_id(value):
    """Accept only a 32-character lowercase hexadecimal tab identifier."""
    return (isinstance(value, str) and len(value) == 32 and
            all(c in '0123456789abcdef' for c in value))


def _safe_relative(value, allowed_ids):
    """Accept ONLY a tab manifest or an asset within a tab's allowed roots."""
    if not isinstance(value, str) or not value or '\\' in value or '\x00' in value:
        raise ValueError('Unsafe notebook entry path.')
    parts = value.split('/')
    if (len(parts) < 3 or parts[0] != 'tabs' or parts[1] not in allowed_ids
            or not all(_safe_file_segment(part) for part in parts)):
        raise ValueError('Unsafe notebook entry path.')
    if len(parts) == 3:
        valid = parts[2] in ('project.json', 'project.v2.backup.json', 'project.v3.backup.json')
    else:
        valid = parts[2] in ('originals', 'pages')
    if not valid:
        raise ValueError('Unsafe notebook entry path.')
    return Path(*parts)


def default_backup_folder():
    """User-writable per-app data, NOT admin-protected Program Files/Common Files."""
    import sys
    if sys.platform == 'win32':
        base = os.environ.get('LOCALAPPDATA') or str(Path.home() / 'AppData' / 'Local')
        return Path(base) / 'Yomu Note' / 'Backups'
    if sys.platform == 'darwin':
        return Path.home() / 'Library' / 'Application Support' / 'Yomu Note' / 'Backups'
    return Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local' / 'share'))) / 'Yomu Note' / 'Backups'


class Notebook:
    """Own one portable study notebook and its temporary editing workspace.

    Beginner's picture: ``self.path`` is the SQLite file the user saves;
    ``self.workspace`` is a temporary folder of editable tab projects.
    ``self.tabs`` is the ordered list shown across the top of the window.
    Calling ``save`` reconciles live project files into the SQLite database.
    Closing removes the temporary workspace, not the user's notebook file.
    """
    def __init__(self, path: Path, name: str, tabs: list[dict], active_id: str,
                 identifier: str, temporary: tempfile.TemporaryDirectory):
        self.path = Path(path).resolve()
        self.name = name
        self.tabs = tabs
        self.active_id = active_id
        self.identifier = identifier
        self._temporary = temporary
        self.workspace = Path(temporary.name)
        self._saved_stats = {}
        self._saved_manifest_hashes = {}
        self.recovery_warnings = []
        self._saved_manifest = None
        self.backup_dirty = False
        self._closed = False

    @classmethod
    def _new_workspace(cls, path, name, tabs, active_id, identifier):
        temporary = tempfile.TemporaryDirectory(prefix='yomu-notebook-')
        return cls(path, name, tabs, active_id, identifier, temporary)

    @classmethod
    def create(cls, parent: Path, name: str):
        parent = Path(parent).expanduser()
        parent.mkdir(parents=True, exist_ok=True)
        path = unique_project_path(parent, name)
        identifier = uuid.uuid4().hex
        tabid = uuid.uuid4().hex
        tab = {'id': tabid, 'title': 'My Notes'}
        nb = cls._new_workspace(path, safe_name(name), [tab], tabid, identifier)
        nb._prepare_project(tabid, tab['title'])
        nb.save()
        return nb

    def _prepare_project(self, tabid, title):
        directory = self.workspace / 'tabs' / tabid
        for name in ('originals', 'pages', 'cache/thumbs', 'cache/previews'):
            (directory / name).mkdir(parents=True, exist_ok=True)
        project = Project(path=directory, name=title)
        project.save()
        return project

    @classmethod
    def load(cls, path: Path, *, recover_cosmetic: bool = False):
        path = Path(path).expanduser().resolve()
        if path.is_dir():
            return cls.migrate_legacy(path)
        if not path.is_file():
            raise ValueError('Choose an existing Yomu Note notebook file.')
        if path.suffix.lower() not in ('.yomunote', '.yominote'):
            raise ValueError('Choose a .yomunote notebook (or older .yominote file).')
        try:
            with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as conn:
                # Check the metadata size in SQLite, BEFORE fetching a
                # potentially enormous string into Python memory.
                size_row = conn.execute(
                    'SELECT length(value) FROM meta WHERE key=?', ('manifest',)
                ).fetchone()
                if (not size_row or type(size_row[0]) is not int
                        or not 0 < size_row[0] <= MAX_MANIFEST_BYTES):
                    raise ValueError('Notebook has no valid manifest or it is too large.')
                row = conn.execute('SELECT value FROM meta WHERE key=?', ('manifest',)).fetchone()
                if row is None or not isinstance(row[0], str):
                    raise ValueError('Notebook has no manifest.')
                meta = json.loads(row[0])
                cls._check_manifest(meta)
                nb = cls._new_workspace(path, meta['name'], meta['tabs'],
                                        meta['active_id'], meta['id'])
                nb._saved_manifest = json.dumps(meta, sort_keys=True, ensure_ascii=False)
                try:
                    # SQLite BLOBs stay on disk while we check the index.
                    # This is a fast guard against hostile files claiming an
                    # enormous number of files or total extraction size.
                    inventory = conn.execute(
                        'SELECT count(*),sum(size),sum(length(data)) FROM files'
                    ).fetchone()
                    file_count, stated_bytes, actual_bytes = inventory
                    if (file_count > MAX_LOADED_FILES or stated_bytes is None
                            or actual_bytes is None or stated_bytes < 0
                            or actual_bytes < 0 or stated_bytes > MAX_LOADED_BYTES
                            or actual_bytes > MAX_LOADED_BYTES
                            or stated_bytes != actual_bytes):
                        raise ValueError('Notebook exceeds safe extraction limits or has invalid asset sizes.')
                    ids = {t['id'] for t in meta['tabs']}
                    # Read blobs in 1 MiB chunks. A user may import a 1 GB
                    # source PDF; never allocate the entire file in RAM.
                    for rowid, rel, size, mtime in conn.execute(
                            'SELECT rowid, path, size, mtime_ns FROM files'):
                        local = _safe_relative(rel, ids)
                        if type(size) is not int or not 0 <= size <= MAX_ASSET_BYTES:
                            raise ValueError('Invalid notebook entry size.')
                        # A malicious timestamp can be negative, nonnumeric,
                        # or beyond what Windows/macOS can represent.
                        if type(mtime) is not int or not 0 <= mtime <= 9_223_372_036_854_775_807:
                            raise ValueError('Invalid notebook entry timestamp.')
                        # Resolve before writing to prevent path traversal.
                        # This also rejects any unexpected symlink escape.
                        dest = (nb.workspace / local).resolve()
                        if not dest.is_relative_to(nb.workspace.resolve()):
                            raise ValueError('Unsafe notebook entry path.')
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        with conn.blobopen('files', 'data', rowid, readonly=True) as blob, dest.open('wb') as out:
                            if len(blob) != size:
                                raise ValueError('Corrupted notebook asset length.')
                            while True:
                                chunk = blob.read(1024 * 1024)
                                if not chunk:
                                    break
                                out.write(chunk)
                        os.utime(dest, ns=(int(mtime), int(mtime)))
                        nb._saved_stats[rel] = (int(mtime), size)
                        if local.name.endswith('.json'):
                            nb._saved_manifest_hashes[rel] = hashlib.sha256(
                                dest.read_bytes()).hexdigest()
                    for tab in meta['tabs']:
                        project = Project.load(
                            nb.workspace / 'tabs' / tab['id'],
                            recover_cosmetic=recover_cosmetic,
                            recovery_warnings=nb.recovery_warnings,
                        )
                        if recover_cosmetic and nb.recovery_warnings:
                            # The ORIGINAL notebook file is never altered.
                            # Recovery is only allowed on a separate copy.
                            project.save()
                    if recover_cosmetic and nb.recovery_warnings:
                        nb.save()
                    nb.upgrade_legacy_extension()
                    return nb
                except Exception:
                    nb.close()
                    raise
        except sqlite3.DatabaseError as exc:
            raise ValueError('This file is not a supported Yomu Note notebook.') from exc

    @staticmethod
    def _check_manifest(meta):
        if not isinstance(meta, dict) or meta.get('format') != MAGIC_FORMAT or meta.get('version') != NOTEBOOK_VERSION:
            raise ValueError('Unsupported notebook container format.')
        tabs = meta.get('tabs')
        if not isinstance(tabs, list) or not 1 <= len(tabs) <= MAX_TABS:
            raise ValueError('Invalid number of notebook tabs.')
        ids = [t.get('id') for t in tabs if isinstance(t, dict)]
        if len(ids) != len(tabs) or not all(_safe_tab_id(x) for x in ids) or len(set(ids)) != len(ids):
            raise ValueError('Invalid tab identifiers.')
        if any(not isinstance(t.get('title'), str) or not 1 <= len(t['title']) <= 100 for t in tabs):
            raise ValueError('Invalid tab names.')
        if meta.get('active_id') not in ids or not _safe_tab_id(meta.get('id')):
            raise ValueError('Invalid notebook identifiers.')
        if not isinstance(meta.get('name'), str) or len(meta['name']) > 240:
            raise ValueError('Invalid notebook name.')

    @classmethod
    def migrate_legacy(cls, folder: Path):
        """Safe COPY of v2-v4 folder; never touch the user's original folder."""
        original = Project.load(folder)
        nb = cls.create(folder.parent, original.name)
        tabid = nb.tabs[0]['id']
        target = nb.workspace / 'tabs' / tabid
        for base in ('originals', 'pages'):
            source = original.path / base
            if not source.exists():
                continue
            for entry in source.rglob('*'):
                if entry.is_symlink():
                    nb.close()
                    raise ValueError('Refusing to import a symlink from a legacy project.')
                if entry.is_file():
                    dest = target / base / entry.relative_to(source)
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(entry, dest)
        shutil.copy2(original.path / 'project.json', target / 'project.json')
        restored = Project.load(target)
        nb.tabs[0]['title'] = restored.name
        nb.name = original.name
        nb.save()
        return nb

    def project(self, tabid: str):
        if tabid not in {t['id'] for t in self.tabs}:
            raise KeyError('Tab does not exist.')
        return Project.load(self.workspace / 'tabs' / tabid)

    def add_tab(self, title: str = 'New Tab'):
        if len(self.tabs) >= MAX_TABS:
            raise ValueError('This notebook has reached its tab limit.')
        title = title.strip()[:100]
        if not title:
            raise ValueError('Tab name cannot be empty.')
        tabid = uuid.uuid4().hex
        self._prepare_project(tabid, title)
        self.tabs.append({'id': tabid, 'title': title})
        self.active_id = tabid
        return tabid

    def rename_tab(self, tabid: str, title: str):
        title = title.strip()[:100]
        if not title:
            raise ValueError('Tab name cannot be empty.')
        tab = next(t for t in self.tabs if t['id'] == tabid)
        tab['title'] = title
        project = self.project(tabid)
        project.name = title
        project.save()

    def delete_tab(self, tabid: str):
        if len(self.tabs) <= 1:
            raise ValueError('A notebook must have at least one tab.')
        index = next(i for i, tab in enumerate(self.tabs) if tab['id'] == tabid)
        tab = self.tabs.pop(index)
        if self.active_id == tabid:
            self.active_id = self.tabs[min(index, len(self.tabs)-1)]['id']
        # Tab files stay in temporary workspace for in-session Undo; they do
        # NOT go into the saved notebook after this edit.
        return index, tab

    def restore_tab(self, index: int, tab: dict):
        if tab['id'] in {t['id'] for t in self.tabs}:
            raise ValueError('Tab is already in notebook.')
        self.tabs.insert(max(0, min(index, len(self.tabs))), dict(tab))
        self.active_id = tab['id']

    def move_tab(self, source: int, destination: int):
        item = self.tabs.pop(source)
        self.tabs.insert(destination, item)

    def transfer_pages(self, source_id: str, target_id: str,
                       page_ids: list[str], move: bool = False):
        """Copy/move pages between internal tabs without touching cache files.

        Source files are copied only ONCE per distinct original path, even if
        the user drags multiple pages from the same 300-page PDF. Each tab
        retains independent annotations and its own source directory.
        """
        if source_id == target_id:
            raise ValueError('Choose another tab as the destination.')
        source = self.project(source_id)
        target = self.project(target_id)
        selected = [p for p in source.pages if p['id'] in set(page_ids)]
        if not selected:
            return 0
        mapping = {}
        new_pages = []
        for original in selected:
            item = copy.deepcopy(original)
            old_id = item['id']
            item['id'] = short_id()
            for field in ('source', 'render_source', 'file'):
                old_relative = item.get(field)
                if not old_relative:
                    continue
                if old_relative not in mapping:
                    rel = Path(old_relative)
                    if rel.parts[0] not in ('originals', 'pages'):
                        raise ValueError('Cannot transfer a cached file as a page source.')
                    # Destination paths must be safe even for legacy PDFs with
                    # unusually long original filenames.
                    new_relative = (
                        f'{rel.parts[0]}/{short_id()}{rel.suffix.lower()}')
                    origin = source.asset_path(old_relative)
                    if not origin.is_file() or origin.is_symlink():
                        raise ValueError('Source document is missing or unsafe.')
                    destination = target.asset_path(new_relative)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(origin, destination)
                    mapping[old_relative] = new_relative
                item[field] = mapping[old_relative]
            if old_id in source.annotations:
                target.annotations[item['id']] = copy.deepcopy(source.annotations[old_id])
            # Moving a page preserves completion. Copying creates a new
            # unread page, even if the original was already finished.
            if move and old_id in source.read_page_ids:
                target.read_page_ids.append(item['id'])
            new_pages.append(item)
        target.pages.extend(new_pages)
        target.selected_page = new_pages[0]['id']
        target.save()
        if move:
            moved_ids = {p['id'] for p in selected}
            source.pages = [p for p in source.pages if p['id'] not in moved_ids]
            for pid in moved_ids:
                source.annotations.pop(pid, None)
            source.read_page_ids = [pid for pid in source.read_page_ids
                                    if pid not in moved_ids]
            if source.selected_page in moved_ids:
                source.selected_page = source.pages[0]['id'] if source.pages else None
            source.save()
            # Keep transferred originals in the temporary workspace.
            # Earlier Undo entries may still point to these files.
            # _files() excludes them from the saved notebook when no
            # living page references them, preventing private leftovers.
            # Fully undoable cross-tab moves require a future history change.
        return len(new_pages)

    def _manifest(self):
        # App release is informational; the integer 'version' is the stable
        # on-disk format version used for backward compatibility.
        return {'format': MAGIC_FORMAT, 'version': NOTEBOOK_VERSION,
                'app_version': __version__,
                'id': self.identifier, 'name': self.name,
                'tabs': self.tabs, 'active_id': self.active_id}

    def _files(self):
        """Yield only materials that living pages still reference.

        A removed page may still need its original file for
        Undo in this session. We keep that file on disk in
        the temporary workspace, but do NOT save it inside
        the portable notebook after the page is removed.

        This distinction is important for private documents.
        """
        ids = {t['id'] for t in self.tabs}
        for tabid in ids:
            base = self.workspace / 'tabs' / tabid
            project = Project.load(base)
            # Before packaging, remove old annotations for deleted pages.
            # Standalone legacy Project.save() stays backward-compatible.
            live_page_ids = {page['id'] for page in project.pages}
            if set(project.annotations) - live_page_ids:
                project.save(prune_orphan_annotations=True)
            referenced = {
                value for page in project.pages
                for field in ('source', 'render_source', 'file')
                if (value := page.get(field))
            }
            for directory in ('originals', 'pages'):
                if not (base / directory).exists():
                    continue
                for item in (base / directory).rglob('*'):
                    if item.is_symlink():
                        raise ValueError('Symbolic links cannot be stored in notebooks.')
                    if item.is_file():
                        asset = item.relative_to(base).as_posix()
                        if asset not in referenced:
                            continue
                        relative = item.relative_to(self.workspace).as_posix()
                        _safe_relative(relative, ids)
                        yield relative, item
            for name in ('project.json', 'project.v2.backup.json', 'project.v3.backup.json'):
                item = base / name
                if item.exists():
                    if item.is_symlink():
                        raise ValueError('Symbolic links cannot be stored in notebooks.')
                    yield item.relative_to(self.workspace).as_posix(), item

    def upgrade_legacy_extension(self):
        """Make a separate .yomunote copy; never rename/delete the old file.

        This is a filename migration, NOT a schema conversion. We first copy
        the complete SQLite database to a temporary sibling with bounded RAM,
        then atomically install the new filename and switch this session to it.
        It is safe to open an old copy again; we never overwrite new files.
        """
        if self.path.suffix.lower() != '.yominote':
            return False
        old = self.path
        suffix = 1
        destination = old.with_suffix('.yomunote')
        while destination.exists():
            suffix += 1
            destination = old.with_name(f'{old.stem} ({suffix}).yomunote')
        temporary = destination.with_name(destination.name + '.' + uuid.uuid4().hex + '.tmp')
        try:
            with old.open('rb') as source, temporary.open('xb') as out:
                shutil.copyfileobj(source, out, length=1024 * 1024)
                out.flush()
                os.fsync(out.fileno())
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
        self.path = destination
        self.backup_dirty = True
        return True

    def save(self):
        """Durable incremental commit. No PDF/page raster cache files are saved."""
        if self._closed:
            raise RuntimeError('Notebook has been closed.')
        self.upgrade_legacy_extension()
        meta = self._manifest()
        self._check_manifest(meta)
        serial = json.dumps(meta, ensure_ascii=False, sort_keys=True)
        present = set()
        changed = serial != self._saved_manifest
        new_stats = dict(self._saved_stats)
        new_hashes = dict(self._saved_manifest_hashes)
        # Use a transaction so the manifest and every changed file appear
        # together; do not mutate our tracking state until commit succeeds.
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute('PRAGMA synchronous=FULL')
            # Overwrite freed SQLite cells instead of retaining the
            # raw bytes of documents that users have deleted.
            conn.execute('PRAGMA secure_delete=ON')
            with conn:
                conn.execute('CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
                conn.execute('CREATE TABLE IF NOT EXISTS files (path TEXT PRIMARY KEY, data BLOB NOT NULL, size INTEGER NOT NULL, mtime_ns INTEGER NOT NULL)')
                for relative, item in self._files():
                    present.add(relative)
                    stat = item.stat()
                    size = stat.st_size
                    if size > MAX_ASSET_BYTES:
                        raise ValueError('A notebook file is larger than the 1 GB safety limit.')
                    record = (stat.st_mtime_ns, size)
                    is_manifest = item.suffix == '.json'
                    # Timestamps can have coarse resolution on USB disks.
                    # Hash small JSON metadata to catch same-size edits.
                    digest = (hashlib.sha256(item.read_bytes()).hexdigest()
                              if is_manifest else None)
                    if record == self._saved_stats.get(relative) and (
                            not is_manifest or
                            digest == self._saved_manifest_hashes.get(relative)):
                        continue
                    # sqlite3.blobopen writes in bounded chunks. The old
                    # read_bytes() path would temporarily allocate up to 1 GB.
                    conn.execute('INSERT OR REPLACE INTO files(path,data,size,mtime_ns) '
                                 'VALUES(?,zeroblob(?),?,?)',
                                 (relative, size, size, stat.st_mtime_ns))
                    row = conn.execute('SELECT rowid FROM files WHERE path=?', (relative,)).fetchone()
                    if row is None:
                        raise IOError('Could not allocate SQLite file entry.')
                    bytes_written = 0
                    with conn.blobopen('files', 'data', row[0]) as blob, item.open('rb') as original:
                        while bytes_written < size:
                            chunk = original.read(min(1024 * 1024, size - bytes_written))
                            if not chunk:
                                raise IOError('An imported file was truncated during save; try again.')
                            blob.write(chunk)
                            bytes_written += len(chunk)
                        # A file that grows during the copy must not be stored
                        # as a valid-looking truncated SQLite asset.
                        if original.read(1):
                            raise IOError('An imported file grew during save; try again.')
                    after = item.stat()
                    if after.st_size != size or after.st_mtime_ns != stat.st_mtime_ns:
                        raise IOError('An imported file changed during save; try again.')
                    new_stats[relative] = record
                    if is_manifest:
                        new_hashes[relative] = digest
                    changed = True
                removed = set(self._saved_stats) - present
                for rel in removed:
                    conn.execute('DELETE FROM files WHERE path=?', (rel,))
                    new_stats.pop(rel, None)
                    new_hashes.pop(rel, None)
                    changed = True
                if changed:
                    conn.execute('INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)', ('manifest', serial))
        self._saved_stats = new_stats
        self._saved_manifest_hashes = new_hashes
        self._saved_manifest = serial
        if changed:
            self.backup_dirty = True
        return changed

    def backup(self, directory: Path | None = None, limit: int = 30):
        """Create a consistent snapshot, retaining at most limit per notebook."""
        directory = Path(directory or default_backup_folder()).expanduser()
        directory.mkdir(parents=True, exist_ok=True)
        limit = max(1, min(int(limit), 100))
        if not self.backup_dirty:
            return None
        self.save()
        prefix = f'{self.identifier}_'
        stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')
        output = directory / f'{prefix}{stamp}.yomunote'
        temp = output.with_suffix('.tmp')
        try:
            with closing(sqlite3.connect(self.path)) as source, closing(sqlite3.connect(temp)) as destination:
                source.backup(destination)
            os.replace(temp, output)
        finally:
            temp.unlink(missing_ok=True)
        # The name can change without breaking backup rotation.
        # Also include legacy snapshots prefixed with the old name.
        previous = sorted(
            (p for p in directory.iterdir()
             if p.suffix.lower() in ('.yomunote', '.yominote')
             and (p.name.startswith(prefix)
                  or f'_{self.identifier}_' in p.name)),
            key=lambda p: p.stat().st_mtime_ns,
        )
        # Respect both the user's count AND a conservative 2 GiB total cap.
        # Keep at least the most recent snapshot even for a large notebook.
        while len(previous) > 1 and (len(previous) > limit or
              sum(p.stat().st_size for p in previous) > BACKUP_STORAGE_SAFETY_BYTES):
            previous.pop(0).unlink()
        self.backup_dirty = False
        return output

    @staticmethod
    def restore_copy(source: Path, destination: Path):
        """Never overwrite the live notebook, even if user selected its path."""
        source = Path(source).expanduser().resolve()
        destination = Path(destination).expanduser().resolve()
        if destination.exists():
            raise FileExistsError('Choose a NEW file name to restore a backup safely.')
        with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as conn:
            row = conn.execute('SELECT value FROM meta WHERE key=?', ('manifest',)).fetchone()
            if not row:
                raise ValueError('Not a Yomu notebook backup.')
            Notebook._check_manifest(json.loads(row[0]))
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            with source.open('rb') as input_file, destination.open('xb') as output_file:
                shutil.copyfileobj(input_file, output_file, length=1024 * 1024)
            # This restored/copied notebook is independent of the original,
            # including its rotating backup history and displayed name.
            with closing(sqlite3.connect(destination)) as conn:
                with conn:
                    row = conn.execute('SELECT value FROM meta WHERE key=?', ('manifest',)).fetchone()
                    meta = json.loads(row[0])
                    meta['id'] = uuid.uuid4().hex
                    meta['name'] = safe_name(destination.stem)
                    conn.execute('UPDATE meta SET value=? WHERE key=?',
                                 (json.dumps(meta, ensure_ascii=False, sort_keys=True), 'manifest'))
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        return destination

    @staticmethod
    def create_clean_share_copy(source: Path, destination: Path):
        """Create a compact copy with no deleted SQLite pages.

        Removing a document from a database does not always
        shrink the database file immediately. SQLite's VACUUM
        operation rebuilds the database using only *live* rows.

        VACUUM INTO writes this clean database to a NEW file.
        It does not modify the notebook the user is editing.

        Internal legacy project-manifest backups are removed from this
        *share copy* because they can contain historic deleted note text.
        Separate automatic recovery backups are not modified.
        """
        source = Path(source).expanduser().resolve()
        destination = Path(destination).expanduser().resolve()
        if source == destination or destination.exists():
            raise FileExistsError('Choose a NEW file name for the cleaned copy.')
        if destination.suffix.lower() != '.yomunote':
            raise ValueError('Cleaned copies must have a .yomunote extension.')
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            # A read-only connection gets a consistent snapshot while
            # the user can continue working in the original notebook.
            with closing(sqlite3.connect(
                    source.as_uri() + '?mode=ro', uri=True)) as conn:
                conn.execute('VACUUM INTO ?', (str(destination),))
            # The copy gets its own identity for independent backups.
            with closing(sqlite3.connect(destination)) as conn:
                with conn:
                    row = conn.execute(
                        'SELECT value FROM meta WHERE key=?',
                        ('manifest',),
                    ).fetchone()
                    if not row:
                        raise ValueError('Cleaned notebook has no manifest.')
                    meta = json.loads(row[0])
                    Notebook._check_manifest(meta)
                    meta['id'] = uuid.uuid4().hex
                    meta['name'] = safe_name(destination.stem)
                    conn.execute(
                        'UPDATE meta SET value=? WHERE key=?',
                        (json.dumps(meta, sort_keys=True,
                                    ensure_ascii=False), 'manifest'),
                    )
                    # Older migrations can leave backup manifests with note
                    # text that has since been removed from live pages.
                    # Keep them in the ORIGINAL/recovery backups, but never
                    # disclose them in a deliberately cleaned share copy.
                    conn.execute("DELETE FROM files WHERE path LIKE ? OR path LIKE ?",
                                 ('tabs/%/project.v2.backup.json',
                                  'tabs/%/project.v3.backup.json'))
                # A DELETE alone can leave historic bytes in SQLite free pages;
                # rebuild only the newly created share copy to erase them.
                conn.execute('VACUUM')
            return destination
        except Exception:
            destination.unlink(missing_ok=True)
            raise

    @classmethod
    def recover_copy(cls, source: Path):
        """Recover cosmetic metadata damage into a NEW notebook.

        The user's original file is never overwritten.
        Any invalid annotations are omitted ONLY from this
        recovered copy. The original remains available for
        later inspection or more advanced repair tools.

        Structural corruption and unsafe paths still fail.
        """
        source = Path(source).expanduser().resolve()
        number = 1
        while True:
            suffix = ' Recovered' if number == 1 else f' Recovered {number}'
            output = source.with_name(source.stem + suffix + '.yomunote')
            if not output.exists():
                break
            number += 1
        cls.restore_copy(source, output)
        try:
            return cls.load(output, recover_cosmetic=True)
        except Exception:
            # Never leave behind a misleading partial recovered file.
            output.unlink(missing_ok=True)
            raise

    def close(self):
        if not self._closed:
            self._temporary.cleanup()
            self._closed = True
