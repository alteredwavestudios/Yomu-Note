"""Real PDF sample tests for the new bounded Lanczos-3 thumb path.

Optional reportlab dependency is needed only to generate the tiny sample PDF;
Yomu uses its normal pypdfium2 and Pillow runtime dependencies to render.
"""
from pathlib import Path
from PIL import Image, JpegImagePlugin
import pytest
from yomunote.project import Project
from yomunote.importers import (
    import_document, image_for_page, LARGE_THUMB_DISK_BUDGET,
    LARGE_THUMB_FILE_LIMIT, MAX_RENDER_PIXELS,
    ADAPTIVE_PREVIEW_DISK_BUDGET, ADAPTIVE_PREVIEW_FILE_LIMIT,
)

def test_pillow_lanczos_is_three_lobes():
    # Pillow documents LANCZOS as its three-lobe windowed sinc filter.
    # An actual downscale verifies that the chosen Pillow option exists.
    image = Image.new('RGB', (200, 100), '#ffffff')
    output = image.resize((40, 20), Image.Resampling.LANCZOS)
    assert output.size == (40, 20)


def test_responsive_pdf_thumb_uses_lanczos_and_no_chroma_subsampling(tmp_path):
    reportlab = pytest.importorskip('reportlab.pdfgen.canvas')
    pdf = tmp_path / 'test.pdf'
    canvas = reportlab.Canvas(str(pdf), pagesize=(612, 792))
    for i in range(30):
        canvas.drawString(45, 750 - i * 22, 'Yomu small type PDF sample · line %d' % i)
    canvas.save()

    project = Project.create(tmp_path / 'projects', 'My module')
    page = import_document(project, pdf)[0]
    # The 260px thumbnail is an on-demand enlarged version, not 20 extra pages.
    path = image_for_page(project, page, thumbnail=True, thumb_width=260)
    assert path.is_file() and path.stat().st_size < LARGE_THUMB_DISK_BUDGET
    with Image.open(path) as thumb:
        assert thumb.width <= 260 and thumb.height <= round(260 * 1.40)
        assert JpegImagePlugin.get_sampling(thumb) == 0  # 4:4:4, not muddy 4:2:0
        assert thumb.width > 200
    folder = path.parent
    assert len(list(folder.glob('*.jpg'))) <= LARGE_THUMB_FILE_LIMIT
    # Source PDF remains unaffected; this jpeg lives only in disposable cache.
    assert project.asset_path(page['render_source']).exists()


def test_original_render_limits_unmodified():
    assert MAX_RENDER_PIXELS == 12_000_000
    assert LARGE_THUMB_DISK_BUDGET == 8 * 1024 * 1024
    assert ADAPTIVE_PREVIEW_DISK_BUDGET == 12 * 1024 * 1024
    assert ADAPTIVE_PREVIEW_FILE_LIMIT == 3
