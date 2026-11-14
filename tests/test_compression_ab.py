"""v0.4.2 compression diagnosis: lossless/JPEG comparison is non-persistent."""
from pathlib import Path
from PIL import Image, ImageDraw
import pytest

from yomunote.project import Project
from yomunote.importers import (
    image_for_page, lossless_preview_comparison,
    MAX_RENDER_PIXELS, ADAPTIVE_PREVIEW_DISK_BUDGET,
    ADAPTIVE_PREVIEW_FILE_LIMIT, LARGE_THUMB_DISK_BUDGET,
)


def test_lossless_comparison_matches_cached_jpeg_dimensions_but_does_not_write(tmp_path):
    project = Project.create(tmp_path, 'AB Test')
    source = project.path / 'originals' / 'sample.png'
    original = Image.new('RGB', (900, 1200), 'white')
    d = ImageDraw.Draw(original)
    for y in range(20, 1000, 11):
        d.text((42, y), 'A study note 1234 - fine text', fill=(17, 21, 27))
    original.save(source)
    page = {'id': 'abc', 'kind': 'image', 'render_source': 'originals/sample.png',
            'source': 'originals/sample.png', 'title': 'Sample'}
    cached = image_for_page(project, page, thumbnail=False, level=.15)
    folder = cached.parent
    before = {f.name: (f.stat().st_size, f.read_bytes()) for f in folder.iterdir()}
    w, h, rgb = lossless_preview_comparison(project, page, cached, level=.15)
    with Image.open(cached) as jpeg:
        assert (w, h) == jpeg.size
        jpeg_bytes = jpeg.convert('RGB').tobytes()
    assert len(rgb) == w * h * 3
    assert rgb != jpeg_bytes  # JPEG is lossy; source render is not JPEG-decoded
    assert {f.name: (f.stat().st_size, f.read_bytes()) for f in folder.iterdir()} == before
    assert not list(project.path.rglob('*.png')) or source.exists()


def test_compression_test_cannot_escape_cache_or_change_limits(tmp_path):
    project = Project.create(tmp_path, 'Guards')
    page = {'id': 'a', 'kind': 'blank'}
    preview = image_for_page(project, page, thumbnail=False, level=.15)
    with pytest.raises(ValueError):
        lossless_preview_comparison(project, page, tmp_path / 'bad.jpg', level=.15)
    with pytest.raises(ValueError):
        lossless_preview_comparison(project, page, preview, level=2.0)
    with pytest.raises(ValueError):
        lossless_preview_comparison(project, page, preview, level=.25)  # size mismatch
    assert MAX_RENDER_PIXELS == 12_000_000
    assert ADAPTIVE_PREVIEW_DISK_BUDGET == 12 * 1024 * 1024
    assert ADAPTIVE_PREVIEW_FILE_LIMIT == 3
    assert LARGE_THUMB_DISK_BUDGET == 8 * 1024 * 1024


def test_lossless_comparison_does_not_modify_normal_or_thumb_cache(tmp_path):
    project = Project.create(tmp_path, 'Clean')
    page = {'id': 'blank', 'kind': 'blank'}
    compressed = image_for_page(project, page, thumbnail=False, level=.1)
    w,h,data = lossless_preview_comparison(project,page,compressed,level=.1)
    assert (w,h) == (240,339)
    assert len(data) == w*h*3
    assert not list((project.path / 'cache/thumbs').glob('*.jpg'))
    assert not list((project.path / 'cache/previews').glob('*.jpg'))
