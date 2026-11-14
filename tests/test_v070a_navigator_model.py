"""Safe import destinations for grouped notebooks (no Qt needed)."""
from yomunote.page_groups import (
    add_group, flat_tree, flatten, group_pages, get_group,
    move_pages_to_group, move_pages_to_root, page_node, validate,
)


def fixture():
    tree, gid = group_pages(flat_tree(['a', 'b', 'c']), ['a', 'b'], 'Chapter')
    return tree, gid


def test_root_import_never_inherits_adjacent_group():
    tree, gid = fixture()
    # Legacy reconciliation might have put x between a and b.
    group = get_group(tree, gid)
    group['children'].insert(1, page_node('x'))
    result = move_pages_to_root(tree, ['x'], position_hint=1)
    validate(result, flatten(result))
    assert flatten(result) == ['a', 'b', 'x', 'c']
    assert flatten([get_group(result, gid)]) == ['a', 'b']
    assert result[1]['type'] == 'page'
    assert result[1]['page_id'] == 'x'


def test_import_to_explicit_selected_group():
    tree, gid = fixture()
    tree.append(page_node('x'))
    result = move_pages_to_group(tree, ['x'], gid)
    validate(result, flatten(result))
    assert flatten([get_group(result, gid)]) == ['a', 'b', 'x']
    assert flatten(result) == ['a', 'b', 'x', 'c']


def test_root_import_respects_group_boundary():
    tree, gid = fixture()
    tree.append(page_node('x'))
    result = move_pages_to_root(tree, ['x'], position_hint=0)
    validate(result, flatten(result))
    assert flatten(result) == ['x', 'a', 'b', 'c']
    assert get_group(result, gid)['children'] == get_group(tree, gid)['children']


def test_root_import_does_not_duplicate_pages_and_keeps_empty_group():
    tree, gid = fixture()
    tree, empty = add_group(tree, 'Future reading')
    tree.append(page_node('x'))
    result = move_pages_to_root(tree, ['x'], position_hint=2)
    assert flatten(result).count('x') == 1
    assert get_group(result, empty)['children'] == []
    validate(result, ['a', 'b', 'x', 'c'])


def test_no_groups_legacy_data_remains_flat():
    tree = flat_tree(['a', 'b', 'c', 'd'])
    result = move_pages_to_root(tree, ['d'], position_hint=1)
    assert flatten(result) == ['a', 'd', 'b', 'c']
    assert all(x['type'] == 'page' for x in result)
