"""Thumbnail aspect and preview pixel-ratio contract for v0.4.1."""
from math import isclose
from yomunote.layout_geometry import fit_inside, is_near_native_pixel_ratio


def test_landscape_stays_landscape_and_centres_both_axes():
    x, y, w, h = fit_inside(1600, 900, 10, 20, 180, 200)
    assert isclose(w / h, 1600 / 900)
    assert isclose(x + w / 2, 100)
    assert isclose(y + h / 2, 120)
    assert 10 <= x and x + w <= 190
    assert 20 <= y and y + h <= 220


def test_portrait_and_square_keep_original_ratios():
    for size in [(700, 1100), (1000, 1000), (1000, 350)]:
        x, y, w, h = fit_inside(*size, 0, 0, 210, 245)
        assert isclose(w / h, size[0] / size[1])
        assert isclose(x + w / 2, 105)
        assert isclose(y + h / 2, 122.5)


def test_empty_raster_never_drawn():
    assert fit_inside(0, 50, 0, 0, 150, 200)[2:] == (0, 0)


def test_native_ratio_suppresses_redundant_smoothing_only_near_one_to_one():
    assert is_near_native_pixel_ratio(1.0)
    assert is_near_native_pixel_ratio(0.995)
    assert not is_near_native_pixel_ratio(0.9)
    assert not is_near_native_pixel_ratio(1.25)


def test_cached_landscape_and_portrait_page_images_keep_source_ratios(tmp_path):
    """Responsive cache JPEGs are not forcibly made portrait or landscape."""
    from PIL import Image
    from yomunote.project import Project
    from yomunote.importers import image_for_page
    project = Project.create(tmp_path / 'projects', 'Aspect samples')
    for i, dimensions in enumerate(((1600, 600), (500, 1100))):
        source = project.path / 'originals' / f'shape-{i}.png'
        Image.new('RGB', dimensions, '#ffffff').save(source)
        page = {'id': f'page{i}', 'kind': 'image', 'source': 'originals/'+source.name,
                'render_source': 'originals/'+source.name, 'title': f'Page {i}'}
        cache = image_for_page(project, page, thumbnail=True, thumb_width=320)
        with Image.open(cache) as rendered:
            ratio = rendered.width / rendered.height
            expected = dimensions[0] / dimensions[1]
            assert abs(ratio - expected) < 0.012
            assert rendered.width <= 320
            assert rendered.height <= round(320 * 1.4)
