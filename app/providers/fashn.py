"""Локальный FASHN VTON v1.5. Веса около 2 ГБ, примерка около 8 ГБ видеопамяти."""

import importlib.util
import logging
from pathlib import Path

from app.config import Settings
from app.providers.base import ModelCard, TryOnInput, TryOnProvider
from app.providers.device import pick_device

log = logging.getLogger(__name__)

_REQUIRED = (
    "model.safetensors",
    "dwpose/yolox_l.onnx",
    "dwpose/dw-ll_ucoco_384.onnx",
)


class FashnProvider(TryOnProvider):
    def __init__(self, settings: Settings):
        self.settings = settings
        self._pipeline = None

    def probe(self) -> ModelCard:
        missing = [
            name
            for name in _REQUIRED
            if not (self.settings.fashn_weights_dir / name).is_file()
        ]
        package = importlib.util.find_spec("fashn_vton") is not None
        if missing or not package:
            parts = []
            if not package:
                parts.append("Не установлен пакет fashn_vton")
            if missing:
                parts.append("Нет файлов: " + ", ".join(missing))
            return self._card(False, ". ".join(parts) + ". Команды установки есть в README.")
        return self._card(
            True,
            "Локальная модель, устройство "
            + pick_device(self.settings.fashn_device)
            + ". Первая примерка ещё скачает парсер человека (~244 МБ), если его нет в кэше.",
        )

    def generate(self, payload: TryOnInput, on_progress=None) -> Image.Image:
        card = self.probe()
        if not card.available:
            raise RuntimeError(card.detail)
        pipeline = self._load()
        steps = payload.num_timesteps if payload.num_timesteps is not None else 30
        guidance = payload.guidance_scale if payload.guidance_scale is not None else 1.5
        steps = min(60, max(10, steps))
        guidance = min(5.0, max(1.0, guidance))
        result = run_with_step_progress(
            pipeline,
            steps,
            on_progress,
            person_image=payload.person,
            garment_image=payload.garment,
            category=payload.category,
            garment_photo_type=payload.garment_photo_type,
            num_samples=1,
            num_timesteps=steps,
            guidance_scale=guidance,
            seed=payload.seed,
            segmentation_free=payload.segmentation_free,
        )
        if not result.images:
            raise RuntimeError("FASHN VTON не вернул изображение.")
        return result.images[0]

    def _load(self):
        if self._pipeline is not None:
            return self._pipeline
        from fashn_vton import TryOnPipeline

        weights = Path(self.settings.fashn_weights_dir)
        device = pick_device(self.settings.fashn_device)
        if device == "xpu":
            _load_tryon_in_bf16_on_xpu()
        log.info("Загружаю FASHN VTON из %s на %s", weights, device)
        self._pipeline = TryOnPipeline(weights_dir=str(weights), device=device)
        return self._pipeline

    def _card(self, available: bool, detail: str) -> ModelCard:
        return ModelCard(
            id="fashn-vton-1.5",
            title="FASHN VTON 1.5",
            available=available,
            local=True,
            commercial_use=True,
            license="Apache-2.0 (парсер человека — лицензия NVIDIA SegFormer, проверьте её)",
            vram="около 8 ГБ, на CPU работает медленно",
            detail=detail,
        )


def run_with_step_progress(pipeline, steps: int, on_progress, **kwargs):
    """Считает шаги через tqdm, которым пайплайн оборачивает цикл сэмплирования."""

    import fashn_vton.pipeline as pipe

    original = pipe.tqdm

    def tqdm_with_progress(iterable, *args, total=None, **tqdm_kwargs):
        done = 0
        for item in iterable:
            yield item
            done += 1
            if on_progress is not None:
                on_progress(done, total or steps)

    pipe.tqdm = tqdm_with_progress
    try:
        if on_progress is not None:
            on_progress(0, steps)
        return pipeline(**kwargs)
    finally:
        pipe.tqdm = original


def _load_tryon_in_bf16_on_xpu() -> None:
    """Официальный пайплайн включает bf16 только для CUDA. На Intel Arc без этого модель тяжелее."""

    import torch
    from fashn_vton.pipeline import TryOnPipeline

    if getattr(TryOnPipeline, "_xpu_bf16", False):
        return
    if not getattr(torch.xpu, "is_bf16_supported", lambda: False)():
        return
    original = TryOnPipeline._setup_tryon_model

    def setup(pipeline):
        if pipeline.device.type == "xpu":
            pipeline.inference_dtype = torch.bfloat16
            pipeline.logger.info("Using dtype: %s", pipeline.inference_dtype)
        return original(pipeline)

    TryOnPipeline._setup_tryon_model = setup
    TryOnPipeline._xpu_bf16 = True
