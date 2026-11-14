"""Adaptive renders stay small, disposable, and separate from the normal cache."""
from pathlib import Path
from tempfile import TemporaryDirectory
from PIL import Image
import pytest

from yomunote.project import Project
from yomunote.importers import (
    import_document, image_for_page, ADAPTIVE_PREVIEW_DISK_BUDGET,
    ADAPTIVE_PREVIEW_FILE_LIMIT, LARGE_THUMB_DISK_BUDGET,
    LARGE_THUMB_FILE_LIMIT, clear_obsolete_preview_tiers,
)


def test_arbitrary_zoom_from_original_pdf_without_touching_normal_cache():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = root / 'page.pdf'
        Image.new('RGB', (800, 1100), 'white').save(source, 'PDF')
        project = Project.create(root, 'Zoom test')
        page = import_document(project, source)[0]

        tiny = image_for_page(project, page, thumbnail=False, level=0.10)
        arbitrary = image_for_page(project, page, thumbnail=False, level=0.37)
        assert tiny.is_file() and arbitrary.is_file() and tiny != arbitrary
        assert tiny.parent.resolve() == arbitrary.parent.resolve() == (project.path / 'cache' / 'previews-adaptive').resolve()
        with Image.open(tiny) as a, Image.open(arbitrary) as b:
            assert a.width < b.width and a.height < b.height
            assert a.width * a.height < 120_000
        assert not list((project.path / 'cache/thumbs').glob('*.jpg'))
        assert not list((project.path / 'cache/previews').glob('*.jpg'))
        assert not (project.path / 'cache/previews-hi').exists()

        base = image_for_page(project, page, thumbnail=False)
        assert base.parent.resolve() == (project.path / 'cache/previews').resolve()
        assert image_for_page(project, page, thumbnail=False, level=.37) == arbitrary
        copy = project.duplicate_to(root, 'Zoom copy')
        assert not (copy.path / 'cache').exists()


def test_zoom_disk_cache_has_both_strict_count_and_byte_limit():
    with TemporaryDirectory() as tmp:
        project = Project.create(Path(tmp), 'Zoom caps')
        page = {'id':'a', 'kind':'blank'}
        for level in [i/20 for i in range(2, 21)]:
            image_for_page(project, page, thumbnail=False, level=level)
        files = list((project.path / 'cache/previews-adaptive').glob('*.jpg'))
        assert len(files) <= ADAPTIVE_PREVIEW_FILE_LIMIT
        assert sum(p.stat().st_size for p in files) <= ADAPTIVE_PREVIEW_DISK_BUDGET
        assert not (project.path / 'cache/previews-hi').exists()


def test_responsive_thumbs_have_independent_caps_and_not_full_document_renders():
    with TemporaryDirectory() as tmp:
        project = Project.create(Path(tmp), 'Thumb caps')
        for index in range(28):
            page = {'id':f'page-{index}', 'kind':'blank'}
            thumb = image_for_page(project, page, thumbnail=True, thumb_width=320)
            with Image.open(thumb) as img:
                assert img.width <= 320 and img.height <= 448
        files = list((project.path / 'cache/thumbs-responsive').glob('*.jpg'))
        assert len(files) <= LARGE_THUMB_FILE_LIMIT
        assert sum(p.stat().st_size for p in files) <= LARGE_THUMB_DISK_BUDGET
        assert not list((project.path / 'cache/thumbs').glob('*.jpg'))
        assert not list((project.path / 'cache/previews').glob('*.jpg'))


@pytest.mark.parametrize('level', [0, -1, 1.01, 2, 10, float('nan'), float('inf')])
def test_reject_unbounded_or_invalid_preview_level(level):
    with TemporaryDirectory() as tmp:
        project = Project.create(Path(tmp), 'No cache')
        with pytest.raises(ValueError):
            image_for_page(project, {'id':'a', 'kind':'blank'}, thumbnail=False, level=level)
        assert not (project.path / 'cache/previews-adaptive').exists()


def test_reject_invalid_responsive_thumbnail_requests():
    with TemporaryDirectory() as tmp:
        project = Project.create(Path(tmp), 'No mixing')
        page = {'id':'a', 'kind':'blank'}
        with pytest.raises(ValueError):
            image_for_page(project, page, thumbnail=True, level=.10)
        with pytest.raises(ValueError):
            image_for_page(project, page, thumbnail=False, high=True, level=.10)
        with pytest.raises(ValueError):
            image_for_page(project, page, thumbnail=False, thumb_width=300)
        with pytest.raises(ValueError):
            image_for_page(project, page, thumbnail=True, thumb_width=5000)


def test_legacy_hd_and_fixed_tier_cleanup_touches_no_content():
    with TemporaryDirectory() as tmp:
        project = Project.create(Path(tmp), 'Old caches')
        source = project.path / 'originals' / 'keep.pdf'
        source.write_bytes(b'project original')
        for sub in ['previews-hi', 'previews-small', 'previews', 'thumbs']:
            folder = project.path / 'cache' / sub
            folder.mkdir(exist_ok=True, parents=True)
            (folder / 'derived.jpg').write_bytes(b'temporary')
        clear_obsolete_preview_tiers(project)
        assert not list((project.path / 'cache/previews-hi').glob('*.jpg'))
        assert not list((project.path / 'cache/previews-small').glob('*.jpg'))
        assert (project.path / 'cache/previews/derived.jpg').exists()
        assert (project.path / 'cache/thumbs/derived.jpg').exists()
        assert source.read_bytes() == b'project original'
