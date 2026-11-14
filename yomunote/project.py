"""Versioned, portable Yomu Note project files with restricted asset paths.

Version 4 reads v2/v3 Sumi Study manifests and migrates them on save. Version 1 is unsupported.
"""
from __future__ import annotations
import json
import os
import re
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .vector_marks import valid_stroke, valid_shape, valid_highlight
from .notes_layout import NotesPageSetup
from .page_groups import validate as validate_page_groups, flat_tree, reconcile
from .reading_progress import validated_read_ids

FORMAT_VERSION = 4
PANEL_KEYS = ('pages', 'preview', 'notes')


def valid_panel_order(value) -> bool:
    """Reject malformed saved layouts without compromising older projects."""
    return (isinstance(value, list) and len(value) == 3
            and all(isinstance(key, str) for key in value)
            and set(value) == set(PANEL_KEYS))


def short_id() -> str:
    return uuid.uuid4().hex


def safe_name(name: str) -> str:
    """Make a readable cross-platform filename from user-entered text."""
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', '_', name.strip())
    return name.strip(' .')[:90] or 'Untitled'


def unique_project_path(parent: Path, name: str) -> Path:
    """Add a numeric suffix instead of overwriting an existing notebook."""
    base = safe_name(name)
    proposed = parent / f'{base}.yomunote'
    number = 2
    while proposed.exists():
        proposed = parent / f'{base} {number}.yomunote'
        number += 1
    return proposed


def validate_relpath(value: str) -> Path:
    """Keep referenced media INSIDE a project, including on Windows.

    Example: ``originals/reading.pdf`` is okay; ``../passwords.txt`` is not.
    Windows has additional reserved names and alternate-stream syntax; reject
    those on Mac/Linux too, so portable notebooks remain safe everywhere.
    """
    if not isinstance(value, str) or not value or '\\' in value:
        raise ValueError('Invalid project asset path.')
    path = Path(value)
    # Windows treats ':' as an alternate stream/drive separator.
    # Reserved device names are unsafe even with an extension.
    reserved = re.compile(
        r'^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?$',
        re.IGNORECASE,
    )
    if (path.is_absolute() or '..' in path.parts or
            any(part in ('', '.') or any(char in part for char in '<>:"|?*') or
                part.endswith((' ', '.')) or reserved.fullmatch(part)
                for part in path.parts)):
        raise ValueError('Unsafe project asset path.')
    if path.parts[0] not in ('originals', 'pages', 'cache'):
        raise ValueError('Project asset must be inside originals/, pages/ or cache/.')
    return path


def validated_note_pages(value, active_id, legacy_html, legacy_scroll, legacy_setup):
    """Validate named note pages without rewriting any rich-text HTML.

    A missing field is the pre-v0.7.4 single-document format; it becomes one
    normal notes page at load. This is intentionally independent of the page
    navigator and stable PDF page IDs.
    """
    if value is None:
        first_id = short_id()
        return ([{'id': first_id, 'title': 'Notes 1',
                  'html': legacy_html, 'scroll': legacy_scroll,
                  'page_setup': legacy_setup}], first_id)
    if not isinstance(value, list) or not 1 <= len(value) <= 128:
        raise ValueError('Invalid note page list (maximum 128 pages per tab).')
    clean, seen = [], set()
    for entry in value:
        if not isinstance(entry, dict):
            raise ValueError('Invalid note page entry.')
        identifier = entry.get('id')
        title = entry.get('title')
        html = entry.get('html')
        scroll = entry.get('scroll', 0)
        setup = entry.get('page_setup')
        if (not isinstance(identifier, str) or not re.fullmatch(r'[0-9a-f]{32}', identifier)
                or identifier in seen):
            raise ValueError('Invalid or duplicate note page ID.')
        if not isinstance(title, str) or not 1 <= len(title.strip()) <= 100:
            raise ValueError('Invalid note page title.')
        if not isinstance(html, str):
            raise ValueError('Invalid note page content.')
        if type(scroll) is not int or not 0 <= scroll <= 10_000_000:
            scroll = 0
        if setup is not None:
            setup = NotesPageSetup.from_dict(setup).as_dict()
        clean.append({'id': identifier, 'title': title,
                      'html': html, 'scroll': scroll,
                      'page_setup': setup})
        seen.add(identifier)
    if active_id not in seen:
        active_id = clean[0]['id']
    return clean, active_id


@dataclass
class Project:
    """Model of ONE tab's documents, notes, groups and annotations.

    A Project is intentionally independent of Qt widgets: it stores Python
    dictionaries/lists and a path to its media. ``project.json`` serialises
    this model. A Notebook holds many such independent projects as tabs.
    """
    path: Path
    name: str
    pages: list[dict] = field(default_factory=list)
    # Group data contains only references to stable page IDs.
    # None tells us this notebook predates page groups (v0.7).
    page_groups: list[dict] | None = None
    read_page_ids: list[str] = field(default_factory=list)
    notes_html: str = ''
    # v0.7.4: optional named note documents. Legacy notes_html is mirrored
    # to the first document so pre-v0.7.4 notebooks still open without loss.
    note_pages: list[dict] | None = None
    active_note_id: str | None = None
    notes_scroll: int = 0  # QTextEdit scrollbar value; project-local view state
    notes_page_setup: dict | None = None  # None means preserve legacy 20px note layout
    selected_page: str | None = None
    splitter_sizes: list[int] = field(default_factory=lambda: [230, 650, 480])
    panel_order: list[str] = field(default_factory=lambda: list(PANEL_KEYS))
    identifier: str = field(default_factory=short_id)
    annotations: dict[str, list[dict]] = field(default_factory=dict)
    highlight_color: str = '#ffcf69'
    loaded_version: int = field(default=FORMAT_VERSION, repr=False)

    @classmethod
    def create(cls, parent: Path, name: str) -> 'Project':
        parent = Path(parent).expanduser()
        parent.mkdir(parents=True, exist_ok=True)
        path = unique_project_path(parent, name)
        path.mkdir()
        for folder in ('pages', 'originals', 'cache/thumbs', 'cache/previews'):
            (path / folder).mkdir(parents=True, exist_ok=True)
        project = cls(path=path, name=path.stem, notes_page_setup=NotesPageSetup().as_dict())
        project.save()
        return project

    @classmethod
    def load(cls, path: Path, *, recover_cosmetic: bool = False,
             recovery_warnings: list[str] | None = None) -> 'Project':
        path = Path(path).expanduser().resolve()
        manifest = path / 'project.json'
        if not manifest.is_file() or manifest.is_symlink():
            raise ValueError('Choose a legacy Yomu Note project folder containing project.json.')
        if manifest.stat().st_size > 32 * 1024 * 1024:
            raise ValueError('Project manifest is unexpectedly large.')
        data = json.loads(manifest.read_text(encoding='utf-8'))
        # JSON can contain a number or list at its root.
        # A notebook manifest must be a dictionary of named fields.
        # Give a helpful error instead of an AttributeError crash.
        if not isinstance(data, dict):
            raise ValueError('Project manifest must be a JSON object.')
        if data.get('format') not in ('sumi-study', 'yomu-note'):
            raise ValueError('This is not a supported Yomu Note project.')
        version = data.get('version')
        if version not in (2, 3, FORMAT_VERSION):
            raise ValueError(f'Project format v{version} is not supported. Supported versions: 2–{FORMAT_VERSION}.')
        annotations = data.get('annotations', {}) if version >= 3 else {}
        highlight_color = data.get('highlight_color', '#ffcf69')
        if not isinstance(highlight_color, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', highlight_color):
            if not recover_cosmetic:
                raise ValueError('Invalid project highlight colour.')
            highlight_color = '#ffcf69'
            if recovery_warnings is not None:
                recovery_warnings.append(f'{path.name}: reset invalid highlight colour')
        if not isinstance(annotations, dict) or len(annotations) > 20000:
            raise ValueError('Invalid annotations structure.')
        clean_annotations = {}
        for page_id, marks in annotations.items():
            if not isinstance(page_id, str) or not isinstance(marks, list) or len(marks) > 1000:
                raise ValueError('Invalid annotation list.')
            valid_marks = []
            for mark in marks:
                kind = mark.get('kind') if isinstance(mark, dict) else None
                valid = (valid_stroke(mark) if kind == 'stroke' else
                         valid_shape(mark) if kind == 'shape' else
                         valid_highlight(mark))
                if valid:
                    valid_marks.append(mark)
                elif recover_cosmetic:
                    # A damaged mark must not prevent opening healthy notes.
                    # Recovery happens in a COPY of the original notebook.
                    if recovery_warnings is not None:
                        recovery_warnings.append(
                            f'{path.name}: skipped invalid annotation on {page_id}')
                else:
                    raise ValueError(
                        'Invalid vector stroke.' if kind == 'stroke' else
                        'Invalid vector shape.' if kind == 'shape' else
                        'Invalid highlight annotation.')
            clean_annotations[page_id] = valid_marks
        annotations = clean_annotations
        pages = data.get('pages')
        if not isinstance(pages, list) or len(pages) > 20000:
            raise ValueError('Invalid project page list or too many pages (maximum 20,000).')
        seen_page_ids = set()
        for page in pages:
            if not isinstance(page, dict) or not isinstance(page.get('id'), str):
                raise ValueError('Invalid page entry.')
            if page['id'] in seen_page_ids:
                raise ValueError('Duplicate page identifiers.')
            seen_page_ids.add(page['id'])
            if not isinstance(page.get('title', ''), str):
                raise ValueError('Invalid page title.')
            source_page = page.get('source_page')
            if source_page is not None and (
                    type(source_page) is not int or not 1 <= source_page <= 20000):
                raise ValueError('Invalid source page number.')
            for field_name in ('source', 'render_source', 'file'):
                if page.get(field_name):
                    rel = validate_relpath(page[field_name])
                    target = (path / rel).resolve()
                    if not target.is_relative_to(path):
                        raise ValueError('Project asset points outside its project folder.')
        name = data.get('name', path.stem)
        notes_html = data.get('notes_html', '')
        notes_scroll = data.get('notes_scroll', 0)
        if type(notes_scroll) is not int or not 0 <= notes_scroll <= 10_000_000:
            notes_scroll = 0  # malformed/legacy view state must never block opening notes
        page_setup = data.get('notes_page_setup')
        if page_setup is not None:
            try:
                page_setup = NotesPageSetup.from_dict(page_setup).as_dict()
            except (ValueError, TypeError):
                if not recover_cosmetic:
                    raise
                page_setup = None
                if recovery_warnings is not None:
                    recovery_warnings.append(f'{path.name}: reset invalid page setup')
        # Notes-page migration is LOSSLESS: never extract plain text or
        # rebuild rich HTML. Existing HTML, links and layout metadata are
        # carried verbatim into the first named notes page.
        note_pages, active_note_id = validated_note_pages(
            data.get('note_pages'), data.get('active_note_id'),
            notes_html, notes_scroll, page_setup)
        if len(note_pages) == 1:
            # Old applications wrote these legacy fields directly. If a
            # notebook was edited with an older version, let those fields
            # win for its sole notes page rather than dropping those edits.
            note_pages[0].update(html=notes_html, scroll=notes_scroll,
                                 page_setup=page_setup)
        # Older notebooks have only the flat page list.  Build a safe
        # navigator without changing their PDF order or page IDs.
        hierarchy = data.get('page_groups', None)
        if hierarchy is None:
            hierarchy = flat_tree([page['id'] for page in pages])
        try:
            validate_page_groups(hierarchy, [page['id'] for page in pages])
        except ValueError:
            if not recover_cosmetic:
                raise
            hierarchy = flat_tree([page['id'] for page in pages])
            if recovery_warnings is not None:
                recovery_warnings.append(
                    f'{path.name}: reset damaged page group hierarchy')
        read_page_ids = data.get('read_page_ids', [])
        try:
            read_page_ids = validated_read_ids(
                read_page_ids, [page['id'] for page in pages])
        except ValueError:
            if not recover_cosmetic:
                raise
            read_page_ids = []
            if recovery_warnings is not None:
                recovery_warnings.append(
                    f'{path.name}: reset invalid reading progress')
        selected_page = data.get('selected_page')
        sizes = data.get('splitter_sizes', [230, 650, 480])
        order = data.get('panel_order', list(PANEL_KEYS))
        if not valid_panel_order(order):
            if not recover_cosmetic:
                raise ValueError('Invalid saved panel order.')
            order = list(PANEL_KEYS)
            if recovery_warnings is not None:
                recovery_warnings.append(f'{path.name}: reset invalid panel order')
        if not isinstance(name, str) or len(name) > 240:
            raise ValueError('Invalid project name.')
        if not isinstance(notes_html, str):
            raise ValueError('Invalid project notes.')
        if selected_page is not None and not isinstance(selected_page, str):
            raise ValueError('Invalid selected-page identifier.')
        if (not isinstance(sizes, list) or len(sizes) != 3
                or any(type(v) is not int or not 0 <= v <= 100000 for v in sizes)):
            if not recover_cosmetic:
                raise ValueError('Invalid saved column widths.')
            sizes = [230, 650, 480]
            if recovery_warnings is not None:
                recovery_warnings.append(f'{path.name}: reset invalid column widths')
        return cls(path=path, name=name or path.stem,
                   pages=pages, page_groups=hierarchy,
                   read_page_ids=read_page_ids,
                   notes_html=notes_html, note_pages=note_pages,
                   active_note_id=active_note_id, notes_scroll=notes_scroll,
                   notes_page_setup=page_setup,
                   selected_page=selected_page,
                   splitter_sizes=sizes, panel_order=list(order),
                   identifier=data.get('id') if isinstance(data.get('id'), str) else short_id(),
                   annotations=annotations, highlight_color=highlight_color, loaded_version=version)

    def save(self, *, prune_orphan_annotations: bool = False) -> None:
        if not valid_panel_order(self.panel_order):
            raise ValueError('Invalid saved panel order.')
        self.path.mkdir(parents=True, exist_ok=True)
        # Verify every live page is represented exactly once before saving.
        # Keep the existing project format number: this is an optional
        # navigator field which older readers can safely ignore.
        if self.page_groups is None:
            self.page_groups = flat_tree([page['id'] for page in self.pages])
        self.page_groups = reconcile(
            self.page_groups, [page['id'] for page in self.pages])
        validate_page_groups(
            self.page_groups, [page['id'] for page in self.pages])
        if self.notes_page_setup is not None:
            NotesPageSetup.from_dict(self.notes_page_setup)
        self.note_pages, self.active_note_id = validated_note_pages(
            self.note_pages, self.active_note_id,
            self.notes_html, self.notes_scroll, self.notes_page_setup)
        if len(self.note_pages) == 1:
            # Keep the long-standing Project.notes_* public fields writable
            # when code/tests use the old single-document API.
            self.note_pages[0].update(
                html=self.notes_html, scroll=self.notes_scroll,
                page_setup=self.notes_page_setup)
        # Preserve the legacy v0.7.3 field as the FIRST page, not whichever
        # notes page happens to be active. Old readers will still see notes.
        first_note = self.note_pages[0]
        self.notes_html = first_note['html']
        self.notes_scroll = first_note['scroll']
        self.notes_page_setup = first_note['page_setup']
        data = {
            'format': 'yomu-note', 'version': FORMAT_VERSION,
            'app_version': __version__,  # app release, not project schema
            'id': self.identifier, 'name': self.name, 'pages': self.pages,
            'page_groups': self.page_groups,
            # Session Undo may still reference removed pages.  Save only
            # completion flags belonging to current, live pages.
            'read_page_ids': sorted(
                set(self.read_page_ids) & {p['id'] for p in self.pages}),
            # Undo may still refer to removed pages in memory. Only
            # annotations on LIVING pages belong in the saved file.
            'annotations': (
                {page_id: marks for page_id, marks in self.annotations.items()
                 if page_id in {page['id'] for page in self.pages}}
                if prune_orphan_annotations else self.annotations
            ),
            'highlight_color': self.highlight_color,
            'notes_html': self.notes_html, 'notes_scroll': self.notes_scroll,
            'note_pages': self.note_pages, 'active_note_id': self.active_note_id,
            'notes_page_setup': self.notes_page_setup,
            'selected_page': self.selected_page,
            'splitter_sizes': self.splitter_sizes, 'panel_order': list(self.panel_order),
            'updated_at': datetime.now(timezone.utc).isoformat(),
        }
        payload = json.dumps(data, ensure_ascii=False, indent=2)
        if len(payload.encode('utf-8')) > 32 * 1024 * 1024:
            raise ValueError('Project metadata is over 32 MB. Export or split your notes before saving.')
        if self.loaded_version < FORMAT_VERSION:
            old = self.path / 'project.json'
            backup = self.path / f'project.v{self.loaded_version}.backup.json'
            if old.is_file() and not backup.exists():
                shutil.copy2(old, backup)
        temporary = self.path / f'project.{short_id()}.tmp'
        try:
            temporary.write_text(payload, encoding='utf-8')
            os.replace(temporary, self.path / 'project.json')
            self.loaded_version = FORMAT_VERSION
        finally:
            temporary.unlink(missing_ok=True)

    def asset_path(self, relative: str) -> Path:
        rel = validate_relpath(relative)
        base = self.path.resolve()
        final = (base / rel).resolve()
        if not final.is_relative_to(base):
            raise ValueError('Project asset escapes the project folder.')
        return final

    def page_by_id(self, page_id: str) -> dict | None:
        return next((p for p in self.pages if p['id'] == page_id), None)

    def duplicate_to(self, parent: Path, name: str) -> 'Project':
        target = unique_project_path(Path(parent), name)
        # Cached page renders don't need to be copied; originals & metadata are enough.
        # Do not follow symlinks supplied by a modified/untrusted project.
        # copytree's default follows links, which could copy unrelated private
        # files outside the project into a new portable copy.
        for item in self.path.rglob('*'):
            if 'cache' in item.relative_to(self.path).parts[:1]:
                continue
            if item.is_symlink():
                raise ValueError('This project contains a symbolic link. Remove it before copying.')
        shutil.copytree(self.path, target, ignore=shutil.ignore_patterns('cache'), symlinks=True)
        copy = Project.load(target)
        copy.name = target.stem
        copy.identifier = short_id()
        copy.save()
        return copy
