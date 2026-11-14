"""Non-GUI checks for two inexpensive review fixes."""
import json
import pytest
from yomunote.project import Project
from yomunote.notebook import Notebook


def test_non_object_project_manifest_reports_useful_error(tmp_path):
    folder = tmp_path / 'bad-project'
    folder.mkdir()
    (folder / 'project.json').write_text('[]', encoding='utf-8')
    with pytest.raises(ValueError, match='JSON object'):
        Project.load(folder)


def test_missing_tab_title_is_a_value_error_not_key_error():
    meta = {
        'format': 'yomu-notebook',
        'version': 5,
        'tabs': [{'id': 'a'*32}],
        'active_id': 'a'*32,
        'id': 'b'*32,
        'name': 'Test',
    }
    with pytest.raises(ValueError, match='Invalid tab names'):
        Notebook._check_manifest(meta)
