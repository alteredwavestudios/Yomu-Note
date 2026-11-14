"""Page-group hierarchy for the v0.7 navigator.

A page and a group are different things:

* Project.pages is the existing, flat reading order.  The PDF engine,
  annotations, page shortcuts, and source files still use that list.
* This module stores ONLY names, nested folders, and stable page IDs.
  A folder NEVER contains a second copy of a page or source PDF.

No Qt imports appear here.  Keeping data logic separate from widgets
lets us test notebook safety without having a desktop running.
"""
from __future__ import annotations

from copy import deepcopy
from uuid import uuid4

MAX_DEPTH = 12
MAX_GROUPS = 10_000


def page_node(page_id: str) -> dict:
    """Make a reference to a page without duplicating its data."""
    return {'type': 'page', 'page_id': page_id}


def group_node(name: str, children=None, *, group_id=None,
               collapsed=False) -> dict:
    """Create a folder.  All descendants have one position in reading order."""
    name = str(name).strip()
    if not 1 <= len(name) <= 120:
        raise ValueError('A group name must contain 1–120 characters.')
    return {'type': 'group', 'id': group_id or uuid4().hex,
            'name': name, 'collapsed': bool(collapsed),
            'children': list(children or [])}


def flat_tree(page_ids) -> list[dict]:
    """Old notebooks have no groups: show each page at the top level."""
    return [page_node(pid) for pid in page_ids]


def flatten(tree) -> list[str]:
    """Return EVERY page, even when its group is collapsed."""
    found = []
    for node in tree:
        if node['type'] == 'page':
            found.append(node['page_id'])
        else:
            found.extend(flatten(node['children']))
    return found


def validate(tree, page_ids) -> None:
    """Reject missing/duplicate pages, cycles and malicious nesting.

    Validation happens BEFORE a drag is committed or a notebook is saved.
    If an invalid drag is attempted, the old data remains unchanged.
    """
    ids = list(page_ids)
    if len(ids) != len(set(ids)):
        raise ValueError('A page ID appears twice in this notebook.')
    if not isinstance(tree, list):
        raise ValueError('Page groups must be a list.')
    seen_pages, seen_groups = set(), set()
    groups = 0

    def walk(items, depth):
        nonlocal groups
        if depth > MAX_DEPTH or not isinstance(items, list):
            raise ValueError('Too many nested page groups.')
        for node in items:
            if not isinstance(node, dict):
                raise ValueError('Invalid page navigator item.')
            kind = node.get('type')
            if kind == 'page':
                pid = node.get('page_id')
                if not isinstance(pid, str) or pid in seen_pages:
                    raise ValueError('Duplicate or invalid grouped page ID.')
                seen_pages.add(pid)
            elif kind == 'group':
                groups += 1
                gid = node.get('id')
                name = node.get('name')
                if (groups > MAX_GROUPS or not isinstance(gid, str)
                        or len(gid) != 32
                        or any(c not in '0123456789abcdef' for c in gid)
                        or gid in seen_groups
                        or not isinstance(name, str)
                        or not 1 <= len(name.strip()) <= 120
                        or type(node.get('collapsed')) is not bool):
                    raise ValueError('Invalid page group.')
                seen_groups.add(gid)
                walk(node.get('children'), depth + 1)
            else:
                raise ValueError('Unknown page navigator item type.')

    walk(tree, 0)
    if seen_pages != set(ids):
        raise ValueError('The group tree must reference every live page once.')


def get_group(tree, group_id):
    """Find one group by stable ID; None means it no longer exists."""
    for node in tree:
        if node['type'] == 'group':
            if node['id'] == group_id:
                return node
            found = get_group(node['children'], group_id)
            if found is not None:
                return found
    return None


def find_parent(tree, node_id):
    """Return (siblings, index) so an item can be moved safely."""
    for i, node in enumerate(tree):
        if ((node['type'] == 'page' and node['page_id'] == node_id)
                or (node['type'] == 'group' and node['id'] == node_id)):
            return tree, i
        if node['type'] == 'group':
            found = find_parent(node['children'], node_id)
            if found:
                return found
    return None


def add_group(tree, name, *, parent_id=None, index=None):
    """Return a NEW tree with a newly created folder."""
    result = deepcopy(tree)
    parent = get_group(result, parent_id) if parent_id else None
    if parent_id and parent is None:
        raise ValueError('The parent group does not exist.')
    siblings = parent['children'] if parent else result
    at = len(siblings) if index is None else max(0, min(index, len(siblings)))
    folder = group_node(name)
    siblings.insert(at, folder)
    return result, folder['id']


def rename_group(tree, group_id, new_name):
    result = deepcopy(tree)
    target = get_group(result, group_id)
    if target is None:
        raise ValueError('Group no longer exists.')
    name = str(new_name).strip()
    if not 1 <= len(name) <= 120:
        raise ValueError('A group name must contain 1–120 characters.')
    target['name'] = name
    return result


def set_collapsed(tree, group_id, collapsed):
    result = deepcopy(tree)
    target = get_group(result, group_id)
    if target is not None:
        target['collapsed'] = bool(collapsed)
    return result


def ungroup(tree, group_id):
    """Remove the folder, but leave every page and subgroup in place."""
    result = deepcopy(tree)
    found = find_parent(result, group_id)
    if not found:
        raise ValueError('Group no longer exists.')
    siblings, index = found
    node = siblings.pop(index)
    if node['type'] != 'group':
        raise ValueError('Only folders can be ungrouped.')
    siblings[index:index] = node['children']
    return result


def remove_group_and_pages(tree, group_id):
    """Return the new tree AND the pages removed by the operation."""
    result = deepcopy(tree)
    found = find_parent(result, group_id)
    if not found:
        raise ValueError('Group no longer exists.')
    siblings, index = found
    node = siblings.pop(index)
    if node['type'] != 'group':
        raise ValueError('Only folders can be removed this way.')
    return result, flatten([node])


def group_pages(tree, page_ids, name, *, parent_id=None):
    """Wrap a contiguous run of page references into a new group.

    Only adjacent pages in the SAME folder can be grouped together.
    This keeps the reading order intact and avoids hidden page jumps.
    """
    result = deepcopy(tree)
    selected = list(page_ids)
    if not selected or len(selected) != len(set(selected)):
        raise ValueError('Select one or more pages to group.')
    parents = [find_parent(result, pid) for pid in selected]
    if any(p is None for p in parents):
        raise ValueError('Some selected pages no longer exist.')
    siblings = parents[0][0]
    if any(p[0] is not siblings for p in parents):
        raise ValueError('Selected pages must share one parent group.')
    positions = sorted(p[1] for p in parents)
    if positions != list(range(positions[0], positions[-1] + 1)):
        raise ValueError('Select adjacent pages without other items between them.')
    if any(siblings[i]['type'] != 'page' for i in positions):
        raise ValueError('Only adjacent pages can be grouped.')
    children = siblings[positions[0]:positions[-1] + 1]
    folder = group_node(name, children)
    siblings[positions[0]:positions[-1] + 1] = [folder]
    return result, folder['id']


def reconcile(tree, page_ids):
    """Adapt groups when legacy page operations change the flat list.

    Older thumbnail actions can insert, remove or reorder pages without
    knowing about groups.  We never discard page objects or duplicate
    page IDs.  A moved page may leave its former group if necessary.

    If a group is split by an old-style reorder, the later run gets a
    separate '(continued)' group.  This is intentional: one group must
    always describe a single contiguous span of the reading order.
    """
    desired = list(page_ids)
    if len(desired) != len(set(desired)):
        raise ValueError('Duplicate page ID.')
    if not tree:
        return flat_tree(desired)
    # Preserve exact hierarchy, empty folders and user-controlled order
    # when only the display is changing.  Rebuilding can move empty nodes.
    if flatten(tree) == desired:
        validate(tree, desired)
        return tree

    # Record each page's existing ancestor folders, including their names.
    paths = {}
    def record(items, ancestors):
        for node in items:
            if node['type'] == 'page':
                paths[node['page_id']] = ancestors
            else:
                record(node['children'], ancestors + [node])
    record(tree, [])

    # Recreate contiguous runs while retaining the original group IDs
    # for their first occurrence.  A completely empty group is kept too.
    used_groups = set()
    result = []
    open_nodes = []
    open_path = []
    for position, pid in enumerate(desired):
        path = paths.get(pid, [])
        if pid not in paths:
            # A new blank page inserted BETWEEN two pages in the same
            # group belongs to that group.  Inserting at the boundary
            # does not accidentally absorb it into either neighbour.
            previous = next((paths[x] for x in reversed(desired[:position])
                             if x in paths), None)
            following = next((paths[x] for x in desired[position + 1:]
                              if x in paths), None)
            if (previous is not None and following is not None and
                    [g['id'] for g in previous] ==
                    [g['id'] for g in following]):
                path = previous
        common = 0
        while (common < min(len(open_path), len(path))
               and open_path[common] == path[common]['id']):
            common += 1
        open_path = open_path[:common]
        open_nodes = open_nodes[:common]
        for group in path[common:]:
            reused = group['id'] not in used_groups
            folder = group_node(
                group['name'] if reused else group['name'] + ' (continued)',
                group_id=group['id'] if reused else uuid4().hex,
                collapsed=group['collapsed'] if reused else False,
            )
            used_groups.add(group['id'])
            siblings = open_nodes[-1]['children'] if open_nodes else result
            siblings.append(folder)
            open_nodes.append(folder)
            open_path.append(group['id'])
        siblings = open_nodes[-1]['children'] if open_nodes else result
        siblings.append(page_node(pid))

    # Empty named folders should not vanish just because their last page
    # was deleted.  Attach an empty folder at the top level if necessary.
    def preserve_empty(items):
        for node in items:
            if node['type'] == 'group':
                if not flatten([node]) and node['id'] not in used_groups:
                    result.append(deepcopy(node))
                    used_groups.add(node['id'])
                else:
                    preserve_empty(node['children'])
    preserve_empty(tree)
    validate(result, desired)
    return result


def move_pages_to_group(tree, page_ids, group_id):
    """Move selected pages into an existing folder, preserving their order.

    This is a model operation.  The UI makes it one Undoable action.
    A group cannot be inserted into itself or copied accidentally.
    """
    result = deepcopy(tree)
    selected = list(dict.fromkeys(page_ids))
    if not selected:
        raise ValueError('Select pages to move.')
    for pid in selected:
        location = find_parent(result, pid)
        if location is None:
            raise ValueError('A selected page no longer exists.')
        siblings, index = location
        if siblings[index]['type'] != 'page':
            raise ValueError('Only pages may be moved this way.')
        siblings.pop(index)
    parent = get_group(result, group_id)
    if parent is None:
        raise ValueError('Destination group no longer exists.')
    parent['children'].extend(page_node(pid) for pid in selected)
    return result


def move_pages_to_root(tree, page_ids, position_hint=None):
    """Move existing page IDs out of folders and into the root.

    A page can appear only once in the hierarchy.  In particular,
    importing near a group's boundary must not silently make an
    unrelated document part of that group.

    ``position_hint`` is an index in the flat reading order.  A root
    entry cannot be inserted halfway through a folder, so we place
    the import beside the closest *whole* root entry instead.
    """
    result = deepcopy(tree)
    selected = list(dict.fromkeys(page_ids))
    if not selected:
        return result
    # Remove the page references where legacy reconciliation put them.
    for pid in selected:
        location = find_parent(result, pid)
        if location is None:
            raise ValueError('An imported page no longer exists.')
        siblings, index = location
        if siblings[index]['type'] != 'page':
            raise ValueError('Only pages can be moved to the root.')
        siblings.pop(index)
    # Root insertion is an explicit choice, even if the preferred
    # position happens to fall inside a pre-existing folder.
    if position_hint is None:
        insertion = len(result)
    else:
        target = max(0, int(position_hint))
        count = 0
        insertion = len(result)
        for index, node in enumerate(result):
            span = len(flatten([node]))
            if target <= count:
                insertion = index
                break
            if target <= count + span:
                insertion = index + 1
                break
            count += span
    result[insertion:insertion] = [page_node(pid) for pid in selected]
    return result


def move_group(tree, group_id, parent_id=None, index=None):
    """Move one *whole* group, including all its nested content.

    This works on a copy.  A failed move cannot damage the original
    hierarchy or the underlying PDF page list.  The owner's Undo action
    records the old and new tree and their corresponding flat page order.

    Index means the insertion slot among the destination's immediate
    children.  We remove the source BEFORE locating the destination to
    avoid stale indices after moving inside the same parent.
    """
    result = deepcopy(tree)
    source = find_parent(result, group_id)
    if source is None:
        raise ValueError('The group being dragged no longer exists.')
    siblings, old_index = source
    node = siblings[old_index]
    if node['type'] != 'group':
        raise ValueError('Only a complete folder can be moved as a group.')
    if parent_id == group_id:
        raise ValueError('A folder cannot contain itself.')

    def contains(node, target_id):
        if node['type'] != 'group':
            return False
        return any(child['type'] == 'group' and
                   (child['id'] == target_id or contains(child, target_id))
                   for child in node['children'])

    if parent_id is not None and contains(node, parent_id):
        raise ValueError('A folder cannot be dropped into a descendant.')
    siblings.pop(old_index)
    parent = get_group(result, parent_id) if parent_id is not None else None
    if parent_id is not None and parent is None:
        raise ValueError('The destination folder no longer exists.')
    destination = parent['children'] if parent is not None else result
    if index is None:
        at = len(destination)
    else:
        at = int(index)
        if destination is siblings and old_index < at:
            at -= 1
        at = min(max(at, 0), len(destination))
    destination.insert(at, node)
    validate(result, flatten(tree))
    return result
