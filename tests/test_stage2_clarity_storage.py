"""Tests for Stage 2 without requiring the optional Qt GUI runtime."""
from pathlib import Path
import json
from PIL import Image, ImageDraw
from yomunote.project import Project, FORMAT_VERSION
from yomunote.preview_clarity import sharpen_cached_preview, MAX_CLARITY_PIXELS


def test_scroll_roundtrip_without_format_migration(tmp_path):
    project = Project.create(tmp_path, 'Reading')
    assert project.loaded_version == FORMAT_VERSION
    assert project.notes_scroll == 0
    project.notes_scroll = 987
    project.save()
    loaded = Project.load(project.path)
    assert loaded.notes_scroll == 987
    assert loaded.loaded_version == FORMAT_VERSION
    manifest = project.path / 'project.json'
    data = json.loads(manifest.read_text())
    data.pop('notes_scroll')  # an older v4 project still opens
    manifest.write_text(json.dumps(data))
    assert Project.load(project.path).notes_scroll == 0
    data['notes_scroll'] = 'bad value'
    manifest.write_text(json.dumps(data))
    assert Project.load(project.path).notes_scroll == 0


def test_small_preview_sharpen_keeps_dimensions_and_no_disk_output(tmp_path):
    path = tmp_path / 'cached.jpg'
    image = Image.new('RGB', (500, 280), 'white')
    ImageDraw.Draw(image).text((20, 35), 'Small contrast-sensitive study text', fill=(45, 45, 45))
    image.save(path, quality=87)
    original_bytes = path.read_bytes()
    gentle = sharpen_cached_preview(path, 'gentle')
    crisp = sharpen_cached_preview(path, 'crisp')
    assert gentle[:2] == crisp[:2] == (500, 280)
    assert len(gentle[2]) == len(crisp[2]) == 500 * 280 * 3
    assert gentle[2] != crisp[2]
    assert path.read_bytes() == original_bytes
    assert list(tmp_path.iterdir()) == [path]
    assert sharpen_cached_preview(path, 'off') is None


def test_oversized_preview_skipped_without_loading_full_raster(tmp_path):
    path = tmp_path / 'large.jpg'
    Image.new('RGB', (1501, 1000), 'white').save(path, quality=87)
    assert 1501 * 1000 > MAX_CLARITY_PIXELS
    assert sharpen_cached_preview(path, 'gentle') is None
