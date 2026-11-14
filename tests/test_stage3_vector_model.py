"""Stage 3 model tests; intentionally runnable without Qt or Windows."""
import json
from pathlib import Path

import pytest

from yomunote.history import CallbackAction, UnifiedHistory
from yomunote.project import Project
from yomunote.vector_marks import (make_stroke, translated_stroke, valid_stroke,
                                   MAX_STROKE_POINTS)


def test_strokes_are_normalized_and_keep_identity_when_moved():
    mark = make_stroke([(0.2, 0.4), (0.6, 0.8)], '#c74879', .003)
    assert valid_stroke(mark)
    moved = translated_stroke(mark, .7, .6)
    assert moved['id'] == mark['id']
    assert moved['points'][0] == pytest.approx([.6, .6])
    assert moved['points'][1] == pytest.approx([1., 1.])
    assert mark['points'] == [[.2, .4], [.6, .8]]


def test_move_clamps_whole_path_both_directions():
    mark = make_stroke([(.05, .1), (.2, .3)], '#abcdef', .002)
    back = translated_stroke(mark, -4, -4)
    assert back['points'][0] == [0., 0.]
    assert back['points'][1] == pytest.approx([.15, .2])


def test_stroke_limits_reject_invalid_and_nonfinite_values():
    mark = make_stroke([(.2, .2), (.3, .3)], '#123456', .003)
    for update in ({'color': 'blue'}, {'width': 0}, {'points': [[0, 0]]},
                   {'points': [[0, 0], [float('nan'), .5]]},
                   {'points': [[0, 0], [2, .2]]},
                   {'points': [[0, 0]] * (MAX_STROKE_POINTS + 1)}):
        invalid = {**mark, **update}
        assert not valid_stroke(invalid)


def test_saved_vector_marks_coexist_with_legacy_highlights(tmp_path):
    project = Project.create(tmp_path, 'Vectors')
    project.pages = [{'id': 'p1', 'title': 'Page', 'kind': 'blank'}]
    stroke = make_stroke([(.1, .1), (.8, .9)], '#d74685', .003)
    highlight = {'kind': 'highlight', 'x': .1, 'y': .2, 'w': .3,
                 'h': .4, 'color': '#ffcf69'}
    project.annotations = {'p1': [highlight, stroke]}
    project.save()
    loaded = Project.load(project.path)
    assert loaded.annotations['p1'] == [highlight, stroke]
    assert loaded.loaded_version == project.loaded_version


def test_invalid_stroke_is_rejected_on_loading_not_drawn(tmp_path):
    project = Project.create(tmp_path, 'Invalid')
    project.save()
    path = project.path / 'project.json'
    data = json.loads(path.read_text())
    data['annotations'] = {'p1': [{'kind': 'stroke', 'id': 'evil',
                                   'points': [[-1., 0.], [.9, .2]],
                                   'color': '#ffcf69', 'width': .002}]}
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='Invalid vector stroke'):
        Project.load(project.path)


def test_notebook_delete_is_undoable_from_different_active_tabs():
    sequence = iter(range(1, 1000)).__next__
    tab_a = UnifiedHistory(sequence_provider=sequence)
    tab_b = UnifiedHistory(sequence_provider=sequence)
    global_tabs = UnifiedHistory(sequence_provider=sequence)
    model = {'a': 0, 'b': 0, 'deleted': False}
    tab_a.perform(CallbackAction('Edit A', lambda: model.__setitem__('a', 0),
                                 lambda: model.__setitem__('a', 1)))
    tab_b.perform(CallbackAction('Edit B', lambda: model.__setitem__('b', 0),
                                 lambda: model.__setitem__('b', 1)))
    global_tabs.perform(CallbackAction('Delete Tab',
                                       lambda: model.__setitem__('deleted', False),
                                       lambda: model.__setitem__('deleted', True)))
    # Switching from A to B must not hide the tab deletion Undo entry.
    target = max((tab_b, global_tabs), key=lambda h: h.next_undo_sequence)
    assert target is global_tabs
    target.undo()
    assert model == {'a': 1, 'b': 1, 'deleted': False}
    assert tab_a.next_undo_label == 'Edit A'
    assert tab_b.next_undo_label == 'Edit B'
    assert global_tabs.can_redo
    assert min((tab_b, global_tabs), key=lambda h: h.next_redo_sequence) is global_tabs
    global_tabs.redo()
    assert model['deleted'] is True
