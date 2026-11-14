"""Persist six movable panel arrangements in old and new project formats."""
from itertools import permutations
from pathlib import Path
import json
from tempfile import TemporaryDirectory
import pytest

from yomunote.project import Project, PANEL_KEYS, valid_panel_order


def test_all_six_layouts_are_portable_and_keep_their_widths():
    with TemporaryDirectory() as tmp:
        project = Project.create(Path(tmp), 'Workspace')
        for order in permutations(PANEL_KEYS):
            project.panel_order = list(order)
            project.splitter_sizes = [180, 530, 460]
            project.save()
            loaded = Project.load(project.path)
            assert loaded.panel_order == list(order)
            assert loaded.splitter_sizes == [180, 530, 460]
            assert loaded.loaded_version == 4


def test_old_v4_manifest_defaults_to_classic_layout():
    with TemporaryDirectory() as tmp:
        project = Project.create(Path(tmp), 'Legacy')
        manifest = project.path / 'project.json'
        data = json.loads(manifest.read_text())
        del data['panel_order']
        manifest.write_text(json.dumps(data))
        restored = Project.load(project.path)
        assert restored.panel_order == ['pages', 'preview', 'notes']


@pytest.mark.parametrize('bad', [None, [], ['pages', 'pages', 'notes'],
                                  ['pages', 'preview', 'unknown'],
                                  ['notes', 'preview'], 'pages,preview,notes'])
def test_reject_malformed_workspace_layout(bad):
    assert not valid_panel_order(bad)
    with TemporaryDirectory() as tmp:
        project = Project.create(Path(tmp), 'Invalid')
        data = json.loads((project.path / 'project.json').read_text())
        data['panel_order'] = bad
        (project.path / 'project.json').write_text(json.dumps(data))
        with pytest.raises(ValueError, match='panel order'):
            Project.load(project.path)
