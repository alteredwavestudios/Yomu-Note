"""Migration tests: future builds must preserve v0.2 data & original files."""
import json
import tempfile
import unittest
from pathlib import Path
from yomunote.project import Project, FORMAT_VERSION


class MigrationTests(unittest.TestCase):
    def test_v2_migrates_with_backup_and_reloads_annotations(self):
        with tempfile.TemporaryDirectory() as folder:
            project = Project.create(Path(folder), 'Old project')
            manifest = project.path/'project.json'
            raw = json.loads(manifest.read_text(encoding='utf-8'))
            raw['version'] = 2
            raw.pop('annotations', None)
            raw['notes_html'] = '<p>Old notes with <b>formatting</b>.</p>'
            manifest.write_text(json.dumps(raw), encoding='utf-8')
            existing = Project.load(project.path)
            self.assertEqual(existing.loaded_version, 2)
            self.assertEqual(existing.notes_html, raw['notes_html'])
            existing.annotations['sample-page'] = [{
                'kind': 'highlight', 'x': .05, 'y': .10, 'w': .4,
                'h': .04, 'color': '#ffcf69',
            }]
            existing.save()
            self.assertTrue((existing.path / 'project.v2.backup.json').exists())
            self.assertEqual(json.loads(manifest.read_text())['version'], FORMAT_VERSION)
            again = Project.load(existing.path)
            self.assertEqual(again.notes_html, raw['notes_html'])
            self.assertEqual(again.annotations['sample-page'][0]['x'], .05)

    def test_v3_project_upgrades_with_backup_and_persists_colour(self):
        """A v0.3 project must keep its annotations and selected colour."""
        with tempfile.TemporaryDirectory() as folder:
            project = Project.create(Path(folder), 'Previous Yomu')
            manifest = project.path / 'project.json'
            data = json.loads(manifest.read_text(encoding='utf-8'))
            data['format'] = 'sumi-study'
            data['version'] = 3
            data.pop('highlight_color', None)
            data['notes_html'] = '<p>Keep <a href="sumi://page/old">↗</a></p>'
            manifest.write_text(json.dumps(data), encoding='utf-8')
            old = Project.load(project.path)
            self.assertEqual(old.loaded_version, 3)
            self.assertEqual(old.highlight_color, '#ffcf69')
            old.highlight_color = '#aabbcc'
            old.save()
            self.assertTrue((old.path/'project.v3.backup.json').exists())
            new = Project.load(old.path)
            self.assertEqual(new.loaded_version, FORMAT_VERSION)
            self.assertEqual(new.highlight_color, '#aabbcc')
            self.assertEqual(new.notes_html, data['notes_html'])
            self.assertEqual(json.loads(manifest.read_text())['format'], 'yomu-note')

    def test_new_project_has_yomunote_suffix(self):
        with tempfile.TemporaryDirectory() as folder:
            project = Project.create(Path(folder), 'Sakura study')
            self.assertEqual(project.path.suffix, '.yomunote')

    def test_bad_annotation_data_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            project = Project.create(Path(folder), 'Malicious data')
            manifest = project.path/'project.json'
            raw = json.loads(manifest.read_text())
            raw['annotations'] = {'page': [{'kind': 'highlight', 'x': -7, 'y': 0,
                                            'w': 1, 'h': 1, 'color': 'not-hex'}]}
            manifest.write_text(json.dumps(raw))
            with self.assertRaises(ValueError):
                Project.load(project.path)


if __name__ == '__main__':
    unittest.main()
