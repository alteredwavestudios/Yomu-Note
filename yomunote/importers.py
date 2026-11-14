"""Offline on-demand import; large PDFs are indexed, not fully rasterised.

Only the original source document and per-page metadata are saved at import.
Page render and thumbnail generation happen in background jobs on demand.
"""
from __future__ import annotations
import math
import os
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path
from collections.abc import Callable

from PIL import Image, ImageOps

from .project import Project, safe_name, short_id
from .pdfium_guard import PDFIUM_LOCK

IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp', '.gif', '.webp'}
OFFICE_EXTS = {'.doc', '.docx', '.odt', '.rtf', '.ppt', '.pptx', '.odp', '.xls', '.xlsx', '.ods', '.txt'}
ALL_EXTS = IMAGE_EXTS | OFFICE_EXTS | {'.pdf', '.epub'}
MAX_PAGES_PER_DOCUMENT = 20000
MAX_RENDER_PIXELS = 12_000_000
PREVIEW_DISK_BUDGET = 64 * 1024 * 1024
THUMB_DISK_BUDGET = 32 * 1024 * 1024
HIGH_DISK_BUDGET = 64 * 1024 * 1024
# Extra on-demand small previews share a strictly bounded 8 MiB DISK cache.
# No extra pages are prefetched and no additional Qt pixmaps remain in RAM.
# v0.3.4d: at most three small, zoom-matched preview files, never unlimited
# 10%/25%/etc. tiers.  All caches are disposable and omitted from copies.
ADAPTIVE_PREVIEW_DISK_BUDGET = 12 * 1024 * 1024
ADAPTIVE_PREVIEW_FILE_LIMIT = 3
# Width-aware thumbnails are rendered only for visible rows and are kept in
# a separate tiny disk cache, NOT precomputed across the project.
LARGE_THUMB_DISK_BUDGET = 8 * 1024 * 1024
LARGE_THUMB_FILE_LIMIT = 20
LARGE_THUMB_MAX_WIDTH = 420
ADAPTIVE_PREVIEW_MIN_LEVEL = .10
Image.MAX_IMAGE_PIXELS = 50_000_000  # Pillow rejects extreme decompression bombs
_CACHE_WRITES: dict[str, int] = {}
_CACHE_WRITE_TRACKING_LIMIT = 512  # Tracking cache folders must not grow forever across notebooks.
_CACHE_WRITE_LOCK = threading.Lock()  # Qt workers can complete renders concurrently.
_RENDER_LOCK = PDFIUM_LOCK  # One shared PDFium lock for previews, indexing, and OCR.


class ImportFailure(Exception):
    pass


def find_office() -> str | None:
    """Locate the user's Office converter; Yomu Note ships no LibreOffice."""
    for name in ('soffice', 'libreoffice'):
        found = shutil.which(name)
        if found:
            return found
    mac = Path('/Applications/LibreOffice.app/Contents/MacOS/soffice')
    return str(mac) if mac.exists() else None


def find_calibre() -> str | None:
    """Locate the optional local ebook-convert program for EPUB imports."""
    found = shutil.which('ebook-convert')
    if found:
        return found
    mac = Path('/Applications/calibre.app/Contents/MacOS/ebook-convert')
    return str(mac) if mac.exists() else None


def _run_command(command: list[str], label: str) -> None:
    """Start a converter safely using an argument LIST, not a shell string.

    ``shell=False`` is subprocess.run's default. Keeping each filename as its
    own argument prevents spaces and punctuation becoming shell commands.
    The 300-second timeout stops a wedged converter running indefinitely.
    """
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=300,
                                stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ImportFailure(f'{label} could not finish: {exc}') from exc
    if result.returncode:
        raise ImportFailure(f'{label} failed: {(result.stderr or result.stdout)[-650:]}')


def _convert_to_pdf(source: Path, output_dir: Path) -> Path:
    """Convert an Office/EPUB file into a temporary PDF for page indexing.

    We preserve the original as a separate project asset. The converted PDF
    is a rendering helper, not a replacement for the document the user chose.
    """
    if source.suffix.lower() == '.epub':
        converter = find_calibre()
        if not converter:
            raise ImportFailure('EPUB import requires Calibre installed locally (ebook-convert).')
        pdf = output_dir / f'{short_id()}.pdf'
        _run_command([converter, str(source), str(pdf)], 'Calibre')
    else:
        converter = find_office()
        if not converter:
            raise ImportFailure('Office import requires LibreOffice installed locally.')
        profile = (output_dir / 'lo-profile').as_uri()
        _run_command([converter, f'-env:UserInstallation={profile}', '--headless',
                      '--convert-to', 'pdf', '--outdir', str(output_dir), str(source)], 'LibreOffice')
        pdf = output_dir / (source.stem + '.pdf')
    if not pdf.is_file() or not pdf.stat().st_size:
        raise ImportFailure('Converter returned without creating a PDF.')
    return pdf


def _index_pdf(source: Path, original_rel: str,
               render_rel: str, name: str) -> list[dict]:
    """Read PDF page count without racing another rendering thread.

    Even opening and closing a PDF uses PDFium, so the
    lock surrounds all of those operations, not just draws.
    """
    import pypdfium2 as pdfium

    with PDFIUM_LOCK:
        document = pdfium.PdfDocument(str(source))
        try:
            count = len(document)
            if count < 1 or count > MAX_PAGES_PER_DOCUMENT:
                raise ImportFailure(
                    f'PDF has {count} pages. '
                    f'Supported range: 1–{MAX_PAGES_PER_DOCUMENT}.')
            return [
                {
                    'id': short_id(),
                    'title': f'{name} · {i + 1}',
                    'source': original_rel,
                    'render_source': render_rel,
                    'source_page': i + 1,
                    'kind': 'pdf',
                }
                for i in range(count)
            ]
        finally:
            document.close()


def import_document(project: Project, source: Path,
                    notify: Callable[[str], None] | None = None) -> list[dict]:
    """Run in a background worker; no GUI objects are used here."""
    source = Path(source).expanduser().resolve()
    ext = source.suffix.lower()
    if not source.is_file() or ext not in ALL_EXTS:
        raise ImportFailure(f'Unsupported file: {source.name}')
    if source.stat().st_size > 1024 * 1024 * 1024:
        raise ImportFailure('Single-file import limit is 1 GB. Split the source first.')
    originals = project.path / 'originals'
    originals.mkdir(exist_ok=True, parents=True)
    # Use an ID plus a real extension.  Long academic filenames,
    # punctuation, Windows-reserved names and trailing dots are
    # descriptive metadata, never internal asset-path components.
    stored = f'originals/{short_id()}{ext}'
    saved = project.asset_path(stored)
    temporary = saved.with_name(saved.name + '.part')
    converted: Path | None = None
    if notify:
        notify(f'Indexing {source.name}…')
    try:
        shutil.copyfile(source, temporary)
        os.replace(temporary, saved)
        if ext in IMAGE_EXTS:
            # Pillow checks dimensions lazily; all detailed image decoding is deferred.
            with Image.open(saved) as pic:
                size = pic.size
                if not all(size) or size[0] * size[1] > 50_000_000:
                    raise ImportFailure('Image has invalid or unsafe dimensions (maximum 50 megapixels).')
            return [{'id': short_id(), 'title': source.stem,
                     'source': stored, 'render_source': stored,
                     'source_page': 1, 'kind': 'image',
                     'original_name': source.name}]
        if ext == '.pdf':
            pages = _index_pdf(saved, stored, stored, source.stem)
            for page in pages:
                page['original_name'] = source.name
            return pages
        with tempfile.TemporaryDirectory(prefix='sumi-convert-') as directory:
            pdf = _convert_to_pdf(saved, Path(directory))
            converted_rel = f'originals/{short_id()}_render.pdf'
            converted = project.asset_path(converted_rel)
            shutil.copyfile(pdf, converted)
            pages = _index_pdf(converted, stored, converted_rel, source.stem)
            for page in pages:
                page['original_name'] = source.name
            return pages
    except Exception:
        saved.unlink(missing_ok=True)
        temporary.unlink(missing_ok=True)
        if converted:
            converted.unlink(missing_ok=True)
        raise


def blank_page(project: Project, label: str = 'Blank page') -> dict:
    return {'id': short_id(), 'title': label, 'source': None,
            'render_source': None, 'source_page': None, 'kind': 'blank'}


def _render_pil(project: Project, page: dict, thumbnail: bool, high: bool = False,
                level: float | None = None, thumb_width: int | None = None) -> Image.Image:
    kind = page.get('kind')
    if kind == 'blank':
        base_size = ((thumb_width, round(thumb_width * 1.4)) if thumb_width else (110, 156)) if thumbnail else ((3600, 5000) if high else (2400, 3394))
        if level is not None:
            base_size = tuple(max(1, round(dimension * level)) for dimension in base_size)
        return Image.new('RGB', base_size, 'white')
    if kind == 'image':
        with Image.open(project.asset_path(page['render_source'])) as source:
            # No full-size Qt pixmap is loaded; only one image is decoded per job.
            image = ImageOps.exif_transpose(source)
            max_size = ((thumb_width, round(thumb_width * 1.4)) if thumb_width else (150, 190)) if thumbnail else ((4100, 5000) if high else (3000, 4000))
            if level is not None:
                max_size = tuple(max(1, round(dimension * level)) for dimension in max_size)
            image.thumbnail(max_size, Image.Resampling.LANCZOS)
            image = image.convert('RGBA')
            background = Image.new('RGB', image.size, 'white')
            background.paste(image, mask=image.getchannel('A'))
            image.close()
            return background
    if kind == 'pdf':
        import pypdfium2 as pdfium
        pdf = pdfium.PdfDocument(str(project.asset_path(page['render_source'])))
        try:
            index = int(page['source_page']) - 1
            if not 0 <= index < len(pdf):
                raise ImportFailure('Page number is outside source document.')
            pdf_page = pdf[index]
            try:
                width, height = pdf_page.get_size()
                if width < 1 or height < 1:
                    raise ImportFailure('Invalid PDF page size.')
                scale = (min(2.0, thumb_width / width, (thumb_width * 1.40) / height,
                             math.sqrt(650_000 / (width * height))) if thumb_width else
                         min(0.45, 180 / width, 190 / height)) if thumbnail else min(
                    5.0 if high else 4.0,
                    (4200 if high else 3000) / width,
                    (5200 if high else 4000) / height,
                    math.sqrt((18_000_000 if high else MAX_RENDER_PIXELS) / (width * height)))
                target_size = None
                if thumb_width is not None:
                    # Enlarged thumbnails previously sampled PDFs at their
                    # *final* pixel width, leaving almost no antialiasing.
                    # Render only this requested thumbnail at 1.35x and
                    # shrink with explicit Pillow Lanczos-3 below. Clamp to
                    # the existing 650k working bitmap-pixel limit.
                    scale = min(scale * 1.35,
                                math.sqrt(650_000 / (width * height)))
                if level is not None:
                    # Render from the original PDF at the demanded *display*
                    # size, with a modest 1.25x super-sample and Lanczos
                    # reduction. Never go above the original 12 MP limit.
                    desired = scale * level
                    target_size = (max(1, round(width * desired)),
                                   max(1, round(height * desired)))
                    scale = min(desired * 1.25,
                                math.sqrt(MAX_RENDER_PIXELS / (width * height)))
                if scale <= 0:
                    raise ImportFailure('Invalid PDF rendering scale.')
                bitmap = pdf_page.render(scale=scale)
                try:
                    result = bitmap.to_pil().convert('RGB')
                finally:
                    bitmap.close()
                if target_size is not None:
                    result.thumbnail(target_size, Image.Resampling.LANCZOS)
                return result
            finally:
                pdf_page.close()
        finally:
            pdf.close()
    raise ImportFailure(f'Unknown page kind: {kind}')


def _trim_cache(folder: Path, budget: int, keep: Path) -> None:
    try:
        files = sorted((p for p in folder.glob('*.jpg') if p.is_file() and p != keep),
                       key=lambda p: p.stat().st_mtime, reverse=True)
        size = keep.stat().st_size if keep.exists() else 0
        for file in files:
            size += file.stat().st_size
            if size > budget:
                size -= file.stat().st_size
                file.unlink(missing_ok=True)
    except OSError:
        pass


def _trim_temporary_variants(folder: Path, budget: int, max_files: int, keep: Path) -> None:
    """Enforce BOTH byte and entry caps after EVERY generated preview.

    Keep the most recently used files first. They may always be regenerated,
    so no user data is lost when old variants are evicted.
    """
    files = sorted((p for p in folder.glob('*.jpg') if p.is_file()),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    total = 0
    for index, path in enumerate(files):
        size = path.stat().st_size
        if index >= max_files or (path != keep and total + size > budget):
            path.unlink(missing_ok=True)
        else:
            total += size


def image_for_page(project: Project, page: dict, thumbnail: bool, high: bool = False,
                   level: float | None = None, thumb_width: int | None = None) -> Path:
    """Render exactly one page, under the pre-existing serial decode lock.

    Optional zoom levels are deliberately restricted to 10%...100% of the
    original normal raster, rounded to 5% increments by the UI. Zooming above
    100% scales the normal raster in Qt: no super-sized preview is created.
    Enlarged navigator thumbs use separately bounded width buckets.
    """
    if level is not None:
        if (thumbnail or high or not math.isfinite(level)
                or not ADAPTIVE_PREVIEW_MIN_LEVEL <= level <= 1.0):
            raise ValueError('Adaptive preview level must be between 10% and 100%.')
    if thumb_width is not None:
        if (not thumbnail or level is not None or high or type(thumb_width) is not int
                or not 110 < thumb_width <= LARGE_THUMB_MAX_WIDTH):
            raise ValueError('Enlarged thumbnail width is invalid.')
    with _RENDER_LOCK:
        return _image_for_page_locked(project, page, thumbnail, high, level, thumb_width)


def _image_for_page_locked(project: Project, page: dict, thumbnail: bool, high: bool,
                           level: float | None = None, thumb_width: int | None = None) -> Path:
    """Never generate a full-document raster library; LRU eviction is strict."""
    if level is not None:
        folder_name = 'previews-adaptive'
        suffix = f'_{round(level * 100)}'
    elif thumb_width is not None:
        folder_name = 'thumbs-responsive'
        suffix = f'_{thumb_width}'
    else:
        folder_name = 'thumbs' if thumbnail else 'previews-hi' if high else 'previews'
        suffix = ''
    folder = project.path / 'cache' / folder_name
    folder.mkdir(parents=True, exist_ok=True)
    destination = project.asset_path(f'cache/{folder_name}/{page["id"]}{suffix}.jpg')
    if destination.is_file() and destination.stat().st_size:
        destination.touch()
        return destination
    image = _render_pil(project, page, thumbnail, high, level, thumb_width)
    if thumbnail:
        # Pillow LANCZOS is Lanczos-3 (a three-lobe windowed sinc filter).
        # Use original PDF/image pixels, never upscale a small old thumbnail.
        image.thumbnail((thumb_width, round(thumb_width * 1.40)) if thumb_width
                        else (110, 144), Image.Resampling.LANCZOS)
    temporary = destination.with_name(destination.name + '.part')
    try:
        # Responsive thumbnails contain tiny text; 4:2:0 colour subsampling
        # makes their edges muddy. Keep 4:4:4 and a modest quality increase.
        # The existing 8 MiB / 20-file eviction caps still apply.
        quality = 86 if thumb_width else 62 if thumbnail else 87
        image.save(temporary, 'JPEG', quality=quality,
                   subsampling=2 if thumbnail and not thumb_width else 0,
                   optimize=True)
        if level is not None:
            # Even one pathological noisy image cannot exceed the 12 MiB cap.
            # Limit transient output, never alter the original page/document.
            while temporary.stat().st_size > ADAPTIVE_PREVIEW_DISK_BUDGET:
                image.thumbnail((max(100, int(image.width * .78)),
                                 max(100, int(image.height * .78))), Image.Resampling.LANCZOS)
                image.save(temporary, 'JPEG', quality=84, subsampling=0, optimize=True)
        os.replace(temporary, destination)
        if level is not None:
            _trim_temporary_variants(folder, ADAPTIVE_PREVIEW_DISK_BUDGET,
                                     ADAPTIVE_PREVIEW_FILE_LIMIT, destination)
        elif thumb_width is not None:
            _trim_temporary_variants(folder, LARGE_THUMB_DISK_BUDGET,
                                     LARGE_THUMB_FILE_LIMIT, destination)
        else:
            key = str(folder)
            with _CACHE_WRITE_LOCK:
                if key not in _CACHE_WRITES and len(_CACHE_WRITES) >= _CACHE_WRITE_TRACKING_LIMIT:
                    # Dropping counters only causes an extra safe trim on the
                    # next write; it never evicts original documents.
                    _CACHE_WRITES.clear()
                count = _CACHE_WRITES[key] = _CACHE_WRITES.get(key, 0) + 1
            if count == 1 or count % 30 == 0:
                budget = THUMB_DISK_BUDGET if thumbnail else HIGH_DISK_BUDGET if high else PREVIEW_DISK_BUDGET
                _trim_cache(folder, budget, destination)
        return destination
    finally:
        image.close()
        temporary.unlink(missing_ok=True)


def lossless_preview_comparison(project: Project, page: dict, compressed_path: Path,
                                level: float | None = None) -> tuple[int, int, bytes]:
    """Return RGB pixels for a *diagnostic-only*, compression-free A/B test.

    Use the SAME PDF/source renderer, supersampling and Lanczos pipeline as the
    cached JPEG at ``compressed_path``. We check dimensions before comparison
    so a stale cached variant cannot misleadingly suggest a compression defect.

    No PNG, lossless cache or permanent file is created. The caller receives a
    single bounded RGB buffer (max 12 MP) and replaces the on-screen pixmap;
    the byte buffer is released after the GUI callback. Rendering is strictly
    serial with the existing PDF cache renderer. Not used for thumbnails.
    """
    if level is not None and (not math.isfinite(level)
                              or not ADAPTIVE_PREVIEW_MIN_LEVEL <= level <= 1.0):
        raise ValueError('Comparison zoom must be 10–100% of the normal raster.')
    compressed_path = Path(compressed_path).resolve()
    cache_dir = (project.path / 'cache').resolve()
    if not compressed_path.is_relative_to(cache_dir) or compressed_path.suffix.lower() != '.jpg':
        raise ValueError('Comparison must use an existing project preview JPEG.')
    with _RENDER_LOCK:
        # This reads JPEG *dimensions only*, not a second decoded page bitmap.
        with Image.open(compressed_path) as encoded:
            expected_size = encoded.size
        result = _render_pil(project, page, thumbnail=False, level=level)
        try:
            if result.size != expected_size:
                raise ValueError('Preview cache dimensions differ from the source render; '
                                 'comparison would be invalid. Rebuild this disposable cache.')
            if result.width * result.height > MAX_RENDER_PIXELS:
                raise ValueError('Comparison exceeds the existing 12 MP page-rendering cap.')
            return result.width, result.height, result.tobytes()
        finally:
            result.close()


def clear_obsolete_preview_tiers(project: Project) -> None:
    """One-time cleanup of 0.3.4c's obsolete, *derived only* raster tiers.

    Never touch sources, annotations, selected pages, or existing normal/thumb
    caches. Never traverse directory symlinks.
    """
    for name in ('previews-hi', 'previews-small'):
        folder = project.path / 'cache' / name
        if folder.is_symlink() or not folder.is_dir():
            continue
        for path in folder.glob('*.jpg'):
            if path.is_file() and not path.is_symlink():
                path.unlink(missing_ok=True)
