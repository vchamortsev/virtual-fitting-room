"""Чтение загруженных фото без EXIF и без путей, присланных клиентом."""

import io

from PIL import Image, ImageOps

Image.MAX_IMAGE_PIXELS = 24_000_000


class ImageError(ValueError):
    """Файл не подходит под контракт примерки."""


def open_image(data: bytes, *, max_bytes: int, max_side: int = 4096) -> Image.Image:
    if len(data) > max_bytes:
        raise ImageError(f"Файл больше {max_bytes // (1024 * 1024)} МБ.")
    if not data:
        raise ImageError("Пустой файл.")
    try:
        with Image.open(io.BytesIO(data)) as incoming:
            incoming.load()
            image = ImageOps.exif_transpose(incoming)
            image = image.convert("RGB")
    except ImageError:
        raise
    except Exception as exc:
        raise ImageError("Нужен файл JPEG, PNG или WebP.") from exc

    if min(image.size) < 64:
        raise ImageError("Сторона изображения должна быть хотя бы 64 пикселя.")
    if max(image.size) > max_side:
        image.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    return image


def open_mask(data: bytes, *, max_bytes: int) -> Image.Image:
    image = open_image(data, max_bytes=max_bytes)
    return image.convert("L")


def cover_resize(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Вписывает кадр в точный размер, обрезая края, а не сжимая пропорции."""

    target_w, target_h = size
    scale = max(target_w / image.width, target_h / image.height)
    resized = image.resize(
        (max(target_w, round(image.width * scale)), max(target_h, round(image.height * scale))),
        Image.Resampling.LANCZOS,
    )
    left = max(0, (resized.width - target_w) // 2)
    top = max(0, (resized.height - target_h) // 2)
    return resized.crop((left, top, left + target_w, top + target_h))


def save_jpeg(image: Image.Image, path) -> None:
    image.convert("RGB").save(path, format="JPEG", quality=92, optimize=True)


def save_png(image: Image.Image, path) -> None:
    image.save(path, format="PNG", optimize=True)
