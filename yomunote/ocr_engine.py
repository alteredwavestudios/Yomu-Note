"""Local, opt-in OCR for a page or user-selected rectangles.

The preview pixmap, annotations and notebook format are never used or modified.
The PDF source is cropped with the *same* PDFium engine as the normal preview,
but at an independent DPI. Render/recognition run only on a worker thread.
"""
from __future__ import annotations

import math
from pathlib import Path

from .pdfium_guard import PDFIUM_LOCK
import re
import subprocess
from .ocr_runtime import find_tesseract, tesseract_data_args
import sys
import tempfile
from typing import Callable, Iterable

from PIL import Image, ImageOps

OCR_DPI = (200, 300, 400, 600)
MAX_REGION_PIXELS = 14_000_000
MAX_REGIONS = 40


class OCRCancelled(Exception):
    """An intentional cancellation, not an OCR error."""


def normalise_rectangle(rect: Iterable[float]) -> tuple[float, float, float, float]:
    """A normalized (left, top, width, height) clipped to the original page."""
    x, y, w, h = (float(v) for v in rect)
    if not all(math.isfinite(v) for v in (x, y, w, h)):
        raise ValueError('Invalid OCR selection coordinates')
    left, right = sorted((x, x + w))
    top, bottom = sorted((y, y + h))
    left, right = max(0., left), min(1., right)
    top, bottom = max(0., top), min(1., bottom)
    if right <= left + .00001 or bottom <= top + .00001:
        raise ValueError('OCR selection has no area')
    return (left, top, right - left, bottom - top)


def reading_order(regions: Iterable[Iterable[float]], row_tolerance: float = .025) -> list[tuple[float, float, float, float]]:
    """Sort whole cut-out blocks by approximate rows, then left to right.

    A tiny y mismatch between adjacent columns should not make the right block
    appear after all left-column rows. OCR handles lines *inside* each block.
    A wide block that begins before columns starts a new reading row.
    """
    boxes = sorted((normalise_rectangle(r) for r in regions), key=lambda r: (r[1], r[0]))
    rows: list[list[tuple[float, float, float, float]]] = []
    anchors: list[float] = []
    for box in boxes:
        if rows and abs(box[1] - anchors[-1]) <= row_tolerance:
            rows[-1].append(box)
        else:
            rows.append([box])
            anchors.append(box[1])
    return [box for row in rows for box in sorted(row, key=lambda r: r[0])]


def installed_languages(executable: str) -> list[str]:
    """Read installed languages without contacting a service."""
    completed = subprocess.run(
        [executable, '--list-langs', *tesseract_data_args(executable)],
        capture_output=True, stdin=subprocess.DEVNULL,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        text=True, encoding='utf-8', errors='replace', timeout=12,
    )
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or 'Cannot list OCR languages').strip())
    values = (completed.stdout + '\n' + completed.stderr).splitlines()
    return sorted({v.strip() for v in values if re.fullmatch(r'[a-zA-Z_]{2,16}', v.strip())})


def _render_pdf_crop(source: Path, page_number: int, region, dpi: int):
    # Serialise the entire PDFium lifetime across OCR, thumbnails, and imports.
    with PDFIUM_LOCK:
        import pypdfium2 as pdfium
        document = pdfium.PdfDocument(str(source))
        try:
            page = document[int(page_number) - 1]
            try:
                width, height = page.get_size()
                if width <= 0 or height <= 0:
                    raise ValueError('Invalid source PDF dimensions')
                x, y, w, h = region
                # PDFium cropping is LEFT, BOTTOM, RIGHT, TOP, in page units.
                crop = (x*width, max(0., (1-y-h)*height),
                        max(0., (1-x-w)*width), y*height)
                points_w, points_h = w * width, h * height
                scale = dpi / 72.0
                # A genuine maximum working bitmap size prevents a whole long PDF
                # from exhausting RAM. Small selections still render at full DPI.
                scale = min(scale, math.sqrt(MAX_REGION_PIXELS / (points_w*points_h)))
                actual_dpi = max(70, round(72 * scale))
                bitmap = page.render(scale=scale, crop=crop, draw_annots=False)
                try:
                    image = bitmap.to_pil().convert('RGB')
                    image.info['ocr_dpi'] = actual_dpi
                finally:
                    bitmap.close()
                return image
            finally:
                page.close()
        finally:
            document.close()


def _render_image_crop(source: Path, region, dpi: int):
    with Image.open(source) as file:
        oriented = ImageOps.exif_transpose(file)
        x, y, w, h = region
        width, height = oriented.size
        left = max(0, min(width-1, int(x*width)))
        top = max(0, min(height-1, int(y*height)))
        right = max(left+1, min(width, math.ceil((x+w)*width)))
        bottom = max(top+1, min(height, math.ceil((y+h)*height)))
        # Source pixels contain all real detail. Only low-resolution print
        # scans benefit from modest upsampling; never artificially enlarge
        # camera/photo images just to claim a high DPI value.
        result = oriented.crop((left, top, right, bottom))
        # A transparent slide/PNG must OCR as ink on white, not black-on-black.
        if 'A' in result.getbands() or 'transparency' in result.info:
            rgba = result.convert('RGBA')
            background = Image.new('RGB', rgba.size, 'white')
            background.paste(rgba, mask=rgba.getchannel('A'))
            result = background
        else:
            result = result.convert('RGB')
    if result.width * result.height > MAX_REGION_PIXELS:
        ratio = math.sqrt(MAX_REGION_PIXELS / (result.width*result.height))
        size = (max(1, int(result.width*ratio)), max(1, int(result.height*ratio)))
        result = result.resize(size, Image.Resampling.LANCZOS)
    return result


def render_source_region(source: Path, kind: str, page_number: int | None,
                         region, dpi: int = 300) -> Image.Image:
    """Render only the marked rectangle from the original, *not* the preview."""
    if dpi not in OCR_DPI:
        raise ValueError('Unsupported OCR resolution')
    region = normalise_rectangle(region)
    if kind == 'pdf':
        image = _render_pdf_crop(Path(source), page_number, region, dpi)
    elif kind == 'image':
        image = _render_image_crop(Path(source), region, dpi)
    else:
        raise ValueError('OCR requires an imported PDF or image page')
    # Tesseract sometimes misreads a crop that touches the first/last glyph.
    # Pillow's expand() doesn't propagate Image.info, so carry the actual
    # capped DPI across explicitly before making the output PNG.
    padded = ImageOps.expand(image, border=12, fill='white')
    padded.info.update(image.info)
    image.close()
    return padded


def clean_ocr_text(raw: str, join_lines: bool = True) -> str:
    """Keep paragraphs but join visual line wraps for ordinary prose.

    Hyphenated line breaks remain unchanged: guessing whether a printed
    hyphen is semantic is dangerous when copying academic quotations.
    """
    value = raw.replace('\r\n', '\n').replace('\r', '\n')
    value = '\n'.join(line.strip() for line in value.split('\n')).strip()
    if not join_lines:
        return value
    paragraphs = re.split(r'\n\s*\n+', value)
    def join(p):
        # Keep bullets, tabular lines and intentional indented structures.
        if any(re.match(r'^\s*(?:[-•*]|\d+[.)])\s', line) for line in p.splitlines()):
            return p
        return ' '.join(line for line in p.splitlines() if line)
    return '\n\n'.join(join(p) for p in paragraphs if p)


def recognise_regions(project, page: dict, regions, *, dpi: int = 300,
                      language: str = 'eng', join_lines: bool = True,
                      cancel=None, progress: Callable[[int, int], None] | None = None) -> str:
    """Run sequential local OCR of all cut-outs and produce clipboard-ready text.

    Accept a snapshot of the page and coordinates before the worker starts.
    No QObjects, QPixmaps, or GUI-state access occurs here.
    """
    if not re.fullmatch(r'[a-zA-Z_+]{2,90}', language):
        raise ValueError('Invalid OCR language code')
    if not regions or len(regions) > MAX_REGIONS:
        raise ValueError(f'Choose between 1 and {MAX_REGIONS} text regions')
    ordered = reading_order(regions)
    kind = page.get('kind')
    if kind not in ('pdf', 'image'):
        raise ValueError('This page cannot be recognised; import a PDF or image first')
    # Validate the selection/page before looking for the optional OCR binary.
    # A blank page is invalid regardless of whether Tesseract is installed.
    executable = find_tesseract()
    if not executable:
        raise FileNotFoundError('No OCR engine found. The packaged app should include offline OCR; please reinstall Yomu Note. Source builds require Tesseract on the build computer.')
    source = project.asset_path(page['render_source'])
    number = page.get('source_page')
    results = []
    for index, region in enumerate(ordered):
        if cancel is not None and cancel.is_set():
            raise OCRCancelled()
        if progress:
            progress(index+1, len(ordered))
        image = render_source_region(source, kind, number, region, dpi)
        try:
            with tempfile.TemporaryDirectory(prefix='yomu-ocr-') as temp:
                input_path = Path(temp) / 'selection.png'
                effective_dpi = int(image.info.get('ocr_dpi', dpi))
                image.save(input_path, format='PNG', dpi=(effective_dpi,effective_dpi))
                command = [executable, str(input_path), 'stdout', '-l', language,
                           '--dpi', str(effective_dpi), '--psm', '3' if region[2] > .85 and region[3] > .85 else '6',
                           *tesseract_data_args(executable)]
                # Poll rather than run(): cancelling stops the child process,
                # even during a very large or difficult scan.
                process = subprocess.Popen(
                    command,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    # No stray black console window in Windows GUI builds.
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
                            )
                try:
                    import time
                    started = time.monotonic()
                    while True:
                        if cancel is not None and cancel.is_set():
                            raise OCRCancelled()
                        if time.monotonic() - started > 120:
                            raise TimeoutError('OCR took too long on one region')
                        try:
                            # Drain stdout/stderr *while* OCR runs. Waiting
                            # solely for poll() would deadlock if a large OCR
                            # result filled a subprocess pipe buffer.
                            output, errors = process.communicate(timeout=.15)
                            break
                        except subprocess.TimeoutExpired:
                            continue
                    if process.returncode:
                        raise RuntimeError(errors.decode('utf-8', 'replace').strip() or 'Tesseract failed')
                    recognised = clean_ocr_text(output.decode('utf-8', 'replace'), join_lines)
                    if recognised:
                        results.append(recognised)
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.communicate()
        finally:
            image.close()
    return '\n\n'.join(results)
