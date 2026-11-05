from PIL import Image

from app.core.images import cover_resize
from app.providers.masking import binarize_mask, dilate_mask, mask_coverage


def test_cover_resize_keeps_exact_frame():
    image = Image.new("RGB", (100, 400), (1, 2, 3))
    framed = cover_resize(image, (80, 80))
    assert framed.size == (80, 80)


def test_dilate_grows_a_small_mark():
    mask = Image.new("L", (21, 21), 0)
    mask.putpixel((10, 10), 255)
    grown = dilate_mask(mask, radius=2)
    assert mask_coverage(grown) > mask_coverage(mask)
    assert binarize_mask(grown).getpixel((10, 10)) == 255
