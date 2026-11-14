"""Tiny, Qt-independent geometry helpers for centred, aspect-safe painting.

The thumbnail *card* is a fixed rectangle, but the page's raster is never
stretched to that rectangle's aspect ratio. No image bytes or caches are made
by these functions.
"""
from __future__ import annotations


def fit_inside(source_width: float, source_height: float,
               box_x: float, box_y: float, box_width: float,
               box_height: float) -> tuple[float, float, float, float]:
    """Return (left, top, width, height) centred inside a bounding box.

    Both axes share ONE scale factor. Landscape slides, portrait pages and
    square diagrams thus keep the original aspect ratio even within a tall
    navigation card. Empty sizes return an empty rectangle.
    """
    if min(source_width, source_height, box_width, box_height) <= 0:
        return (box_x, box_y, 0.0, 0.0)
    factor = min(box_width / source_width, box_height / source_height)
    width, height = source_width * factor, source_height * factor
    return (box_x + (box_width - width) / 2,
            box_y + (box_height - height) / 2,
            width, height)


def is_near_native_pixel_ratio(ratio: float, tolerance: float = 0.012) -> bool:
    """True only when a prefiltered bitmap maps ~1:1 to display pixels.

    Qt's extra smooth interpolation in this case can soften an image that
    Pillow has *already* downsampled with Lanczos-3. For all other scales,
    keep smooth Qt interpolation so arbitrary zoom remains comfortable.
    """
    return abs(ratio - 1.0) <= tolerance
