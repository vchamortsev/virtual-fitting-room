"""Маска области одежды для CatVTON-FLUX.

Индексы совпадают с моделью mattmdjaga/segformer_b2_clothes:
4 верх, 5 юбка, 6 брюки, 7 платье, 12–13 ноги, 14–15 руки.
"""

from PIL import Image, ImageFilter

CLOTHES_LABELS: dict[str, frozenset[int]] = {
    "tops": frozenset({4, 14, 15}),
    "bottoms": frozenset({5, 6, 12, 13}),
    "one-pieces": frozenset({4, 5, 6, 7, 14, 15}),
}


def binarize_mask(mask: Image.Image) -> Image.Image:
    return mask.convert("L").point(lambda value: 255 if value >= 127 else 0)


def dilate_mask(mask: Image.Image, radius: int = 8) -> Image.Image:
    size = max(1, radius) * 2 + 1
    return mask.convert("L").filter(ImageFilter.MaxFilter(size))


def mask_coverage(mask: Image.Image) -> float:
    histogram = mask.convert("L").histogram()
    total = sum(histogram) or 1
    white = sum(histogram[128:])
    return white / total
