"""Plan Smart Import group placement before changing the live GUI.

The old flat page list remains the only authority on page order.  We
construct a *candidate* tree entirely in memory, validate its page IDs,
and return it for one tab-local Undoable commit.

If anything is wrong, the old list and its folders remain untouched.
"""
from __future__ import annotations

from copy import deepcopy

from .import_structure import section_tree

from .page_groups import (
    add_group, flat_tree, flatten, get_group, group_pages,
    move_pages_to_group, move_pages_to_root, page_node, validate,
)


def plan_import(tree, old_ids, batches, *, position, group_id=None,
                smart=False, single_group_label='',
                group_mode='per_file', sections_by_file=None,
                strict_target=True, collapse_new_groups=True):
    """Plan a group hierarchy for batches of (source name, page IDs).

    Smart Import makes one new group per file.  Ordinary Import inserts
    directly into the selected group, or ungrouped at the root.

    Page IDs in each batch are in their source order, and a source must
    contribute at least one page.  Importing the same source twice gets
    different page IDs, not duplicate page objects.

    Return (valid tree, was the chosen parent group available).
    Missing explicit targets are errors, never automatic root fallback.
    """
    original = deepcopy(tree) if tree is not None else flat_tree(old_ids)
    validate(original, old_ids)
    new_ids = []
    for name, ids in batches:
        if not isinstance(name, str) or not ids:
            raise ValueError('Imported documents must contain pages.')
        new_ids.extend(ids)
    if (len(new_ids) != len(set(new_ids)) or
            set(new_ids).intersection(old_ids)):
        raise ValueError('An imported page ID was duplicated.')

    # Add new page references at the root, *not* inside a group that
    # happens to surround the requested flat insertion position.
    original.extend(page_node(pid) for pid in new_ids)
    result = move_pages_to_root(original, new_ids, position_hint=position)
    target_available = group_id is None or get_group(result, group_id) is not None
    destination = group_id if target_available else None

    if group_id is not None and not target_available and strict_target:
        raise ValueError('The selected destination group no longer exists. Choose a destination again.')
    if smart and group_mode not in ('per_file', 'combined', 'none'):
        raise ValueError('Unknown smart-group arrangement.')
    # The review dialog supplies validated *proposals*, not new page IDs.
    # If no review was requested, preserve v0.7.1's existing flat grouping.
    if sections_by_file is None:
        sections_by_file = [[] for _ in batches]
    if len(sections_by_file) != len(batches):
        raise ValueError('Document structure count does not match source files.')
    proposed = [section_tree(ids, sections, collapsed=smart and collapse_new_groups)
                for (_name, ids), sections in zip(batches, sections_by_file)]

    if smart and group_mode == 'combined':
        title = (single_group_label.strip()[:120] or
                 ('Imported documents' if len(batches) > 1 else batches[0][0][:120])
                 or 'Imported documents')
        if destination:
            result, new_group_id = add_group(
                result, title, parent_id=destination)
            result = move_pages_to_group(result, new_ids, new_group_id)
        else:
            result, new_group_id = group_pages(result, new_ids, title)
        get_group(result, new_group_id)['collapsed'] = bool(collapse_new_groups)
        if any(sections_by_file):
            get_group(result, new_group_id)['children'] = [
                node for batch_nodes in proposed for node in batch_nodes]
    elif smart and group_mode == 'per_file':
        for batch_index, (name, ids) in enumerate(batches):
            label = (single_group_label if single_group_label and
                     len(batches) == 1 else name)
            label = label[:120].strip() or 'Imported document'
            if destination:
                result, new_group_id = add_group(
                    result, label, parent_id=destination)
                result = move_pages_to_group(result, ids, new_group_id)
            else:
                result, new_group_id = group_pages(result, ids, label)
            get_group(result, new_group_id)['collapsed'] = bool(collapse_new_groups)
            if sections_by_file[batch_index]:
                get_group(result, new_group_id)['children'] = proposed[batch_index]
    elif smart and group_mode == 'none':
        if destination:
            result = move_pages_to_group(result, new_ids, destination)
    elif destination:
        result = move_pages_to_group(result, new_ids, destination)

    validate(result, list(old_ids) + new_ids)
    return result, target_available
