"""Disposable, viewport-only image resampling used by the PDF canvas.

This module does not open source documents, create caches or retain images.
For magnification Yomu uses bicubic on a bounded crop of the already
resident page preview. Shrinking PDFs remains the existing Lanczos pathway
in importers.py and retains all of its strict disk/RAM limits.
"""
from __future__ import annotations

from PIL import Image

MAX_UPSCALE_SOURCE_PIXELS = 2_500_000
MAX_UPSCALE_OUTPUT_PIXELS = 2_250_000


def bicubic_rgb_crop(pixels: bytes, width: int, height: int,
                     stride: int, output_width: int, output_height: int) -> bytes:
    """Return only RGB bytes; caller constructs the QImage on the GUI thread.

    A bounded source crop, output cap, and lack of disk writes keep this safe
    even if a user zooms to 1500%. No PySide or graphics-thread objects enter
    the worker thread. This is purely a display refinement, never a PDF render.
    """
    if not (0 < width * height <= MAX_UPSCALE_SOURCE_PIXELS
            and 0 < output_width * output_height <= MAX_UPSCALE_OUTPUT_PIXELS
            and stride >= width * 3 and height * stride <= len(pixels)):
        raise ValueError('Viewport crop exceeds Yomu display memory limits.')
    source = Image.frombytes('RGB', (width, height), pixels,
                             'raw', 'RGB', stride, 1)
    scaled = source.resize((output_width, output_height), Image.Resampling.BICUBIC)
    return scaled.tobytes()
