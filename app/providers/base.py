"""Контракт движка примерки."""

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import asdict, dataclass

from PIL import Image


@dataclass
class TryOnInput:
    person: Image.Image
    garment: Image.Image
    category: str
    garment_photo_type: str
    seed: int
    num_timesteps: int | None
    guidance_scale: float | None
    segmentation_free: bool
    mask: Image.Image | None


@dataclass(frozen=True)
class ModelCard:
    id: str
    title: str
    available: bool
    local: bool
    commercial_use: bool
    license: str
    vram: str
    detail: str

    def as_dict(self) -> dict:
        return asdict(self)


class TryOnProvider(ABC):
    @abstractmethod
    def probe(self) -> ModelCard:
        """Дешёвая проверка: пакеты и файлы, без загрузки весов в память."""

    @abstractmethod
    def generate(
        self,
        payload: TryOnInput,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> Image.Image:
        """Одно изображение человека в новой одежде.

        on_progress(step, steps) вызывается до расчёта с step=0 и после каждого шага.
        """
