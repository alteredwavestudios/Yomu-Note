"""Version-label hotfix: app releases must not alter saved format numbers."""
import json
import sqlite3
from pathlib import Path

from yomunote import __version__
from yomunote.notebook import Notebook, NOTEBOOK_VERSION
from yomunote.project import Project, FORMAT_VERSION


def notebook_manifest(path):
    with sqlite3.connect(path) as conn:
        return json.loads(conn.execute(
            "SELECT value FROM meta WHERE key='manifest'").fetchone()[0])


def test_new_notebook_and_projects_record_application_release(tmp_path):
    assert __version__ == '0.8.1b'
    notebook = Notebook.create(tmp_path, 'Versioned notebook')
    try:
        meta = notebook_manifest(notebook.path)
        assert meta['app_version'] == __version__
        assert meta['version'] == NOTEBOOK_VERSION == 5
        project_data = json.loads((notebook.workspace / 'tabs' /
                                   notebook.active_id / 'project.json').read_text())
        assert project_data['app_version'] == __version__
        assert project_data['version'] == FORMAT_VERSION == 4
        assert notebook.save() is False  # no metadata churn after the first save
    finally:
        notebook.close()


def test_old_notebook_without_app_tag_opens_and_is_tagged_on_save(tmp_path):
    notebook = Notebook.create(tmp_path, 'Older notebook')
    path = notebook.path
    notebook.close()
    with sqlite3.connect(path) as conn:
        manifest = notebook_manifest(path)
        manifest.pop('app_version')
        conn.execute("UPDATE meta SET value=? WHERE key='manifest'",
                     (json.dumps(manifest),))
    reopened = Notebook.load(path)
    try:
        assert reopened.save() is True  # re-tag even with no content changes
        assert notebook_manifest(path)['app_version'] == __version__
        assert reopened.save() is False
    finally:
        reopened.close()


def test_standalone_older_project_keeps_format_and_gets_current_tag(tmp_path):
    project = Project.create(tmp_path, 'Legacy standalone')
    manifest_path = project.path / 'project.json'
    manifest = json.loads(manifest_path.read_text())
    manifest.pop('app_version')
    manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
    old = Project.load(project.path)
    old.save()
    updated = json.loads(manifest_path.read_text())
    assert updated['app_version'] == __version__
    assert updated['version'] == FORMAT_VERSION
    assert Project.load(project.path).name == project.name


def test_about_reads_shared_version_instead_of_hardcoding(tmp_path):
    source = (Path(__file__).resolve().parents[1] / 'yomunote' / 'window.py').read_text()
    assert "f'Yomu Note  ·  v{__version__}'" in source
    assert "Yomu Note  ·  v0.6.3" not in source
