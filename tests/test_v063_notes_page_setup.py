"""Document defaults and legacy project compatibility without a Qt installation."""
import json
from pathlib import Path

import pytest
from yomunote.notes_layout import NotesPageSetup, pt_to_px, fitted_margins
from yomunote.project import Project


def test_calculated_defaults():
    setup = NotesPageSetup()
    assert (setup.top_pt, setup.bottom_pt, setup.left_pt, setup.right_pt) == (72,)*4
    assert setup.line_spacing == 1.15
    assert setup.after_for_font(13) == 8
    assert setup.after_for_font(26) == 16
    assert setup.list_step_pt == 18
    assert setup.list_first_text_pt == 36


def test_page_setup_validate_save_roundtrip():
    setup = NotesPageSetup(top_pt=35, bottom_pt=84, left_pt=90, right_pt=54,
                           line_spacing=1.5, paragraph_after_pt=10.5)
    assert NotesPageSetup.from_dict(setup.as_dict()) == setup
    with pytest.raises(ValueError):
        NotesPageSetup.from_dict({'left_pt': -5})
    with pytest.raises((ValueError, TypeError)):
        NotesPageSetup.from_dict({'top_pt': 'a lot'})
    with pytest.raises(ValueError):
        NotesPageSetup.from_dict({'unexpected': 7})


def test_responsive_margins_preserve_saved_measurement():
    settings = NotesPageSetup()
    full = fitted_margins(settings, 96, 800)
    narrow = fitted_margins(settings, 96, 280)
    assert full == (96,96,96,96)
    assert abs(sum(narrow[2:]) - 132) < 0.01
    assert settings.left_pt == settings.right_pt == 72


def test_new_project_persists_notes_page_setup(tmp_path):
    project = Project.create(tmp_path, 'Study')
    saved = json.loads((project.path/'project.json').read_text())
    assert saved['notes_page_setup']['top_pt'] == 72
    loaded = Project.load(project.path)
    assert loaded.notes_page_setup == NotesPageSetup().as_dict()


def test_old_project_without_setup_remains_legacy(tmp_path):
    project = Project.create(tmp_path, 'Legacy notes')
    manifest = project.path/'project.json'
    data = json.loads(manifest.read_text())
    data.pop('notes_page_setup')
    manifest.write_text(json.dumps(data))
    loaded = Project.load(project.path)
    assert loaded.notes_page_setup is None
    loaded.save()
    assert json.loads(manifest.read_text())['notes_page_setup'] is None
