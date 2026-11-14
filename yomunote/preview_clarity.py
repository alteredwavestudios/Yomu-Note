"""Memory-only contrast-aware *luma* sharpening for small previews.

We sharpen Y (brightness) only, leaving JPEG chroma unchanged. Pillow's
UnsharpMask threshold rejects low-contrast changes in smooth photographs and
backgrounds. Applied once *after* Lanczos/JPEG for settled low zooms; never
writes a cache or alters the original document, highlights or thumbnails.
"""
from pathlib import Path
from PIL import Image, ImageFilter

MAX_CLARITY_PIXELS = 1_500_000  # at most ~4.5MB final RGB before Qt copying
MODES = ('off', 'gentle', 'crisp')


def sharpen_cached_preview(path: Path, mode: str):
    """Return (width, height, RGB bytes) or None if the work is too big."""
    if mode not in ('gentle', 'crisp'):
        return None
    with Image.open(path) as source:
        w, h = source.size
        if w < 2 or h < 2 or w * h > MAX_CLARITY_PIXELS:
            return None
        colour = source.convert('YCbCr')
    y, cb, cr = colour.split()
    # Gentle defaults avoid bright halos; Crisp is an explicit opt-in.
    radius, strength, threshold = ((0.65, 62, 4) if mode == 'gentle'
                                    else (0.8, 105, 3))
    clearer = y.filter(ImageFilter.UnsharpMask(radius=radius, percent=strength,
                                                threshold=threshold))
    rgb = Image.merge('YCbCr', (clearer, cb, cr)).convert('RGB')
    return w, h, rgb.tobytes()
