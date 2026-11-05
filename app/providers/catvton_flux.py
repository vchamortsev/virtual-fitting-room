"""Локальный CatVTON-FLUX: одежда и человек склеиваются в один холст, FLUX Fill дорисовывает примерку.

Лицензия FLUX.1 [dev] и весов LoRA — некоммерческая. Для витрины магазина этот движок
нужно включать явно. Код пайплайна не копируется из репозитория CatVTON.
"""

import importlib.util
import logging
import os

from PIL import Image

from app.config import Settings
from app.core.images import cover_resize
from app.providers.base import ModelCard, TryOnInput, TryOnProvider
from app.providers.masking import CLOTHES_LABELS, binarize_mask, dilate_mask, mask_coverage

log = logging.getLogger(__name__)

PROMPT = (
    "The pair of images highlights a clothing and its styling on a model, high resolution, 4K, 8K; "
    "[IMAGE1] Detailed product shot of a clothing. "
    "[IMAGE2] The same cloth is worn by a model in a lifestyle setting."
)


class CatVtonFluxProvider(TryOnProvider):
    def __init__(self, settings: Settings):
        self.settings = settings
        self._pipe = None
        self._processor = None
        self._segmenter = None

    def probe(self) -> ModelCard:
        if not self.settings.enable_catvton_flux:
            return self._card(
                False,
                "Выключена. Лицензия FLUX.1 [dev] некоммерческая, для магазина оставьте FASHN. "
                "Чтобы включить локально: ENABLE_CATVTON_FLUX=true.",
            )
        if importlib.util.find_spec("diffusers") is None or importlib.util.find_spec("torch") is None:
            return self._card(False, "Нужны torch и diffusers. См. requirements-catvton.txt.")
        import torch

        if not torch.cuda.is_available():
            return self._card(False, "Нужна видеокарта NVIDIA. На CPU FLUX не запускается.")
        detail = (
            "Локальный запуск. Первая примерка скачает FLUX Fill и LoRA — это десятки гигабайт. "
            "Для магазина на продакшене нужна отдельная коммерческая лицензия Black Forest Labs."
        )
        if not (os.getenv("HF_TOKEN") or os.getenv("HUGGING_FACE_HUB_TOKEN")):
            detail += " Если вход в Hugging Face ещё не выполнен, задайте HF_TOKEN."
        return self._card(True, detail)

    def generate(self, payload: TryOnInput, on_progress=None) -> Image.Image:
        card = self.probe()
        if not card.available:
            raise RuntimeError(card.detail)

        import torch

        width = self.settings.catvton_width
        height = self.settings.catvton_height
        person = cover_resize(payload.person, (width, height))
        garment = cover_resize(payload.garment, (width, height))
        mask = self._mask_for(person, payload)

        canvas = Image.new("RGB", (width * 2, height))
        canvas.paste(garment, (0, 0))
        canvas.paste(person, (width, 0))
        mask_canvas = Image.new("L", (width * 2, height), 0)
        mask_canvas.paste(mask, (width, 0))

        steps = payload.num_timesteps if payload.num_timesteps is not None else 30
        guidance = payload.guidance_scale if payload.guidance_scale is not None else 30.0
        steps = min(50, max(10, steps))
        guidance = min(50.0, max(1.0, guidance))
        generator = torch.Generator(device="cpu").manual_seed(payload.seed)

        pipe = self._load_pipe()
        result = pipe(
            prompt=PROMPT,
            image=canvas,
            mask_image=mask_canvas,
            height=height,
            width=width * 2,
            guidance_scale=guidance,
            num_inference_steps=steps,
            max_sequence_length=512,
            generator=generator,
        ).images[0]
        return result.crop((width, 0, width * 2, height))

    def _mask_for(self, person: Image.Image, payload: TryOnInput) -> Image.Image:
        if payload.mask is not None:
            mask = binarize_mask(payload.mask.resize(person.size, Image.Resampling.NEAREST))
        else:
            mask = self._auto_mask(person, payload.category)
        if mask_coverage(mask) < 0.01:
            raise RuntimeError(
                "Маска почти пустая. Загрузите маску, где белым отмечена одежда, которую нужно заменить."
            )
        return mask

    def _auto_mask(self, person: Image.Image, category: str) -> Image.Image:
        if importlib.util.find_spec("transformers") is None:
            raise RuntimeError(
                "Автомаска просит пакет transformers. Либо установите его, либо пришлите mask_image."
            )
        import numpy as np
        import torch
        from transformers import AutoModelForSemanticSegmentation, SegformerImageProcessor

        if self._segmenter is None:
            repo = self.settings.segformer_repo
            log.info("Загружаю сегментацию одежды %s", repo)
            self._processor = SegformerImageProcessor.from_pretrained(repo)
            self._segmenter = AutoModelForSemanticSegmentation.from_pretrained(repo)
            self._segmenter.eval()

        inputs = self._processor(images=person, return_tensors="pt")
        with torch.no_grad():
            logits = self._segmenter(**inputs).logits
        upsampled = torch.nn.functional.interpolate(
            logits,
            size=person.size[::-1],
            mode="bilinear",
            align_corners=False,
        )
        labels = upsampled.argmax(dim=1)[0].cpu().numpy()
        selected = np.isin(labels, list(CLOTHES_LABELS[category]))
        mask = Image.fromarray(selected.astype("uint8") * 255, mode="L")
        return dilate_mask(mask, radius=8)

    def _load_pipe(self):
        if self._pipe is not None:
            return self._pipe
        import torch
        from diffusers import FluxFillPipeline, FluxTransformer2DModel

        dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
        log.info("Загружаю CatVTON-FLUX. Первый запуск скачивает большой объём весов.")
        self._pipe = _load_flux_fill(
            dtype=dtype,
            base_repo=self.settings.catvton_base_repo,
            fill_repo=self.settings.catvton_fill_repo,
            lora_repo=self.settings.catvton_lora_repo,
            lora_weight=self.settings.catvton_lora_weight,
        )
        if self.settings.catvton_offload:
            self._pipe.enable_model_cpu_offload()
            if hasattr(self._pipe, "enable_attention_slicing"):
                self._pipe.enable_attention_slicing()
        else:
            self._pipe.to("cuda")
        if hasattr(self._pipe, "vae") and hasattr(self._pipe.vae, "enable_tiling"):
            self._pipe.vae.enable_tiling()
        return self._pipe

    def _card(self, available: bool, detail: str) -> ModelCard:
        return ModelCard(
            id="catvton-flux",
            title="CatVTON-FLUX",
            available=available,
            local=True,
            commercial_use=False,
            license="FLUX.1 [dev] Non-Commercial + CC BY-NC у весов LoRA",
            vram="24 ГБ с offload, комфортно от 40 ГБ",
            detail=detail,
        )


def _load_flux_fill(*, dtype, base_repo: str, fill_repo: str, lora_repo: str, lora_weight: str):
    """Две схемы загрузки: так устроены разные версии diffusers."""

    from diffusers import FluxFillPipeline, FluxTransformer2DModel

    try:
        transformer = FluxTransformer2DModel.from_pretrained(fill_repo, torch_dtype=dtype)
        state = FluxFillPipeline.lora_state_dict(
            lora_repo,
            weight_name=lora_weight,
            return_alphas=True,
        )
        if isinstance(state, tuple):
            state_dict, network_alphas = state
        else:
            state_dict, network_alphas = state, None
        kwargs = {"state_dict": state_dict, "transformer": transformer}
        if network_alphas is not None:
            kwargs["network_alphas"] = network_alphas
        FluxFillPipeline.load_lora_into_transformer(**kwargs)
        return FluxFillPipeline.from_pretrained(
            base_repo,
            transformer=transformer,
            torch_dtype=dtype,
        )
    except Exception as first_error:
        log.warning("Схема LoRA + FLUX.1-dev не собралась: %s", first_error)
        try:
            pipe = FluxFillPipeline.from_pretrained(fill_repo, torch_dtype=dtype)
            pipe.load_lora_weights(lora_repo, weight_name=lora_weight)
            return pipe
        except Exception as second_error:
            raise RuntimeError(
                "Не удалось загрузить CatVTON-FLUX. Примите лицензию FLUX.1 на Hugging Face, "
                "войдите в аккаунт или задайте HF_TOKEN. "
                f"Первая ошибка: {first_error}. Запасная схема: {second_error}"
            ) from second_error
