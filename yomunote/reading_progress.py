"""Per-page reading completion for a notebook tab.

A page ID is stable while its page moves through folders.  Therefore the
read flag belongs to the *page*, not its group or its row number.

There are no Qt objects here.  Groups and progress bars merely display
values calculated from these IDs; changing a view cannot change the data.
"""
from __future__ import annotations

from math import ceil


def validated_read_ids(value, page_ids):
    """Read a saved list without allowing duplicates or unknown page IDs.

    This must be a list in the notebook manifest, not a string or dict.
    Invalid values cannot silently mark arbitrary new pages as completed.
    """
    if not isinstance(value, list) or len(value) > 20_000:
        raise ValueError('Invalid reading-progress list.')
    if any(not isinstance(pid, str) for pid in value):
        raise ValueError('Invalid reading-progress page ID.')
    if len(value) != len(set(value)) or not set(value).issubset(set(page_ids)):
        raise ValueError('Reading progress refers to unknown pages.')
    return list(value)


def descendants(nodes):
    """Return every page ID under folders, including nested children."""
    for node in nodes:
        if node['type'] == 'page':
            yield node['page_id']
        else:
            yield from descendants(node['children'])


def group_counts(group, completed_ids):
    """Return (read, total) without storing a possibly stale group flag."""
    pages = list(descendants(group['children']))
    return sum(pid in completed_ids for pid in pages), len(pages)


def percentage(done, total):
    """Round upwards as requested, but do not call empty groups complete."""
    return ceil(100 * done / total) if total else 0


def set_read_status(existing, live_page_ids, targets, checked):
    """Return a *new* set after validating each requested page ID.

    The owner records this single operation in one per-tab Undo step.
    """
    live = set(live_page_ids)
    wanted = set(targets)
    if not wanted.issubset(live):
        raise ValueError('A page is no longer present in this tab.')
    # Preserve temporary, deleted-page flags in memory for session Undo.
    # Project.save() filters them out of the persistent manifest.
    old = set(existing)
    return old | wanted if checked else old - wanted


def notebook_totals(projects):
    """Count each current page once across the notebook's open tabs."""
    done = total = 0
    for project in projects:
        ids = {page['id'] for page in project.pages}
        total += len(ids)
        done += len(ids & set(project.read_page_ids))
    return done, total
