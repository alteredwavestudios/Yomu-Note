"""Stage 1 tests requiring only Pillow (no graphical display required)."""
from PIL import Image
import pytest

from yomunote.resampling import (
    bicubic_rgb_crop, MAX_UPSCALE_SOURCE_PIXELS, MAX_UPSCALE_OUTPUT_PIXELS,
)


def test_bicubic_enlarges_only_transient_rgb_crop():
    # A sharp line remains bounded and produces the requested output size.
    src = Image.new('RGB', (15, 17), 'white')
    for y in range(17):
        for x in range(7):
            src.putpixel((x, y), (0, 0, 0))
    output = bicubic_rgb_crop(src.tobytes(), 15, 17, 45, 39, 45)
    assert len(output) == 39 * 45 * 3
    enlarged = Image.frombytes('RGB', (39, 45), output)
    assert enlarged.getpixel((2, 20)) == (0, 0, 0)
    assert enlarged.getpixel((36, 20)) == (255, 255, 255)


def test_bicubic_respects_source_and_target_memory_caps():
    with pytest.raises(ValueError):
        bicubic_rgb_crop(b'123', 100, 100, 300, 200, 200)
    with pytest.raises(ValueError):
        bicubic_rgb_crop(b'', MAX_UPSCALE_SOURCE_PIXELS + 1, 1, 1, 3, 3)
    with pytest.raises(ValueError):
        bicubic_rgb_crop(b'', 1, 1, 3, MAX_UPSCALE_OUTPUT_PIXELS + 1, 1)


def test_bicubic_handles_padded_strides_without_shifting_rows():
    # QImage RGB888 rows are often padded to 4-byte alignment.
    row = bytes((10, 20, 30, 200, 210, 220, 0, 0))
    data = row * 2
    output = bicubic_rgb_crop(data, 2, 2, 8, 4, 4)
    assert len(output) == 4 * 4 * 3
