"""Черновик без нейросети: тот же контракт, чтобы магазин мог отладить интеграцию."""

from PIL import Image, ImageDraw

from app.core.images import cover_resize
from app.providers.base import ModelCard, TryOnInput, TryOnProvider

MOCK_WARNING = (
    "Это черновая картинка без нейросети. Она проверяет интеграцию. "
    "Для примерки установите веса fashn-vton-1.5."
)


class MockProvider(TryOnProvider):
    def probe(self) -> ModelCard:
        return ModelCard(
            id="mock",
            title="Черновик интеграции",
            available=True,
            local=True,
            commercial_use=True,
            license="код сервиса",
            vram="не нужна",
            detail=MOCK_WARNING,
        )

    def generate(self, payload: TryOnInput, on_progress=None) -> Image.Image:
        canvas = Image.new("RGB", (768, 1024), (244, 240, 234))
        person = cover_resize(payload.person, (768, 900))
        canvas.paste(person, (0, 0))
        thumb = cover_resize(payload.garment, (168, 210))
        frame = Image.new("RGB", (176, 218), (255, 252, 248))
        frame.paste(thumb, (4, 4))
        canvas.paste(frame, (568, 700))
        draw = ImageDraw.Draw(canvas)
        draw.rectangle((0, 980, 768, 1024), fill=(140, 58, 47))
        draw.text((24, 992), "MOCK PREVIEW", fill=(255, 248, 244))
        return canvas
