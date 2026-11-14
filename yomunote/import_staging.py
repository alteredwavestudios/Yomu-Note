"""Remove *only* uncommitted Smart Import assets after cancellation/failure.

The legacy importer copies source files to originals/ before indexing them.
The review dialog is displayed after indexing but before Project.pages changes.
This cleanup prevents cancelled imports from leaking source PDFs or thumbnails.
"""
from __future__ import annotations

from .pdfium_guard import PDFIUM_LOCK


def cleanup_uncommitted(project, batches):
    """Remove temporary import files only when they were never committed.

    Existing originals and files referenced by Undo are not expendable.
    A cleanup routine must NEVER guess which files a user meant to keep.
    """
    existing = {ref for page in project.pages
                for ref in (page.get('source'), page.get('render_source'))
                if ref is not None}
    pending_ids = set()
    pending_paths = set()
    for _name, pages in batches:
        for page in pages:
            pending_ids.add(page['id'])
            for ref in (page.get('source'), page.get('render_source')):
                if ref and ref not in existing and ref.startswith('originals/'):
                    pending_paths.add(ref)
    # Wait for the currently active PDFium renderer to release file handles
    # before deleting staged originals. RLock matches importers.py's lock.
    with PDFIUM_LOCK:
        for ref in pending_paths:
            try:
                project.asset_path(ref).unlink(missing_ok=True)
            except (OSError, ValueError):
                pass
        for folder in ('thumbs', 'thumbs-responsive', 'previews', 'previews-hi',
                       'previews-adaptive'):
            cache_dir = project.path / 'cache' / folder
            if cache_dir.is_dir():
                for page_id in pending_ids:
                    for path in cache_dir.glob(page_id + '*.jpg'):
                        try:
                            path.unlink(missing_ok=True)
                        except OSError:
                            pass
