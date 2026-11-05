"""HTTP-контракт для бэкенда магазина."""

import asyncio
import time
import uuid

from fastapi import APIRouter, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.core.garment_page import PageFetchError, garment_from_url
from app.offer import PLAN_IDS, public_offer
from app.core.images import ImageError, open_image, open_mask, save_jpeg, save_png
from app.core.security import RateLimitError, check_webhook, key_is_valid, owner_id, read_presented_key
from app.core.store import Job, iso, utcnow
from app.domain import CATEGORIES, PHOTO_TYPES
from app.providers.mock import MOCK_WARNING

router = APIRouter()


class ModelView(BaseModel):
    id: str
    title: str
    available: bool
    local: bool
    commercial_use: bool
    license: str
    vram: str
    detail: str


class ModelsResponse(BaseModel):
    default: str
    models: list[ModelView]


class JobView(BaseModel):
    id: str
    status: str
    model: str
    category: str
    garment_photo_type: str
    error: str | None = None
    warning: str | None = None
    created_at: str
    updated_at: str
    result_url: str | None = None
    step: int | None = None
    steps: int | None = None
    eta_seconds: int | None = None


class HealthResponse(BaseModel):
    status: str
    default_model: str
    models: list[ModelView]


class LeadIn(BaseModel):
    shop: str
    contact: str
    plan: str
    note: str = ""


class LeadOut(BaseModel):
    id: int
    status: str


def _state(request: Request):
    return request.app.state


def _require_owner(request: Request) -> str:
    settings = _state(request).settings
    presented = read_presented_key(
        request.headers.get("x-api-key"),
        request.headers.get("authorization"),
    )
    if not key_is_valid(presented, settings.parsed_api_keys):
        raise HTTPException(status_code=401, detail="Нужен ключ магазина: заголовок X-API-Key.")
    return owner_id(presented)


def _job_view(job: Job, base_url: str, runner=None) -> JobView:
    result_url = None
    if job.status == "succeeded":
        path = f"/v1/try-on/{job.id}/result"
        result_url = f"{base_url.rstrip('/')}{path}" if base_url else path
    warning = MOCK_WARNING if job.model == "mock" else None
    progress = runner.progress_of(job.id) if runner is not None and job.status == "running" else None
    return JobView(
        id=job.id,
        status=job.status,
        model=job.model,
        category=job.category,
        garment_photo_type=job.garment_photo_type,
        error=job.error,
        warning=warning,
        created_at=job.created_at,
        updated_at=job.updated_at,
        result_url=result_url,
        step=None if progress is None else progress["step"],
        steps=None if progress is None else progress["steps"],
        eta_seconds=None if progress is None else progress["eta_seconds"],
    )


def _own_job(request: Request, job_id: str) -> Job:
    identity = _require_owner(request)
    if not job_id.startswith("job_") or len(job_id) > 48:
        raise HTTPException(status_code=404, detail="Задание не найдено.")
    job = _state(request).store.get(job_id)
    if job is None or job.owner_id != identity:
        raise HTTPException(status_code=404, detail="Задание не найдено.")
    return job


def _parse_bool(value: str | None, default: bool) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@router.get("/v1/offer")
def offer() -> dict:
    return public_offer()


@router.post("/v1/leads", response_model=LeadOut, status_code=201)
def create_lead(payload: LeadIn, request: Request) -> LeadOut:
    try:
        _state(request).lead_limiter.hit(request.client.host if request.client else "local")
    except RateLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    shop = payload.shop.strip()
    contact = payload.contact.strip()
    note = payload.note.strip()
    if not 2 <= len(shop) <= 80:
        raise HTTPException(status_code=422, detail="Укажите название магазина.")
    if not 5 <= len(contact) <= 120:
        raise HTTPException(status_code=422, detail="Укажите телефон или почту.")
    if payload.plan not in PLAN_IDS:
        raise HTTPException(status_code=422, detail="Выберите модель оплаты.")
    if len(note) > 500:
        raise HTTPException(status_code=422, detail="Комментарий длиннее 500 знаков.")
    lead = _state(request).leads.add(shop, contact, payload.plan, note)
    return LeadOut(id=lead.id, status="accepted")


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    registry = _state(request).registry
    return HealthResponse(
        status="ok",
        default_model=registry.default_id(),
        models=[ModelView(**card.as_dict()) for card in registry.cards()],
    )


@router.get("/v1/models", response_model=ModelsResponse)
def models(request: Request) -> ModelsResponse:
    _require_owner(request)
    registry = _state(request).registry
    return ModelsResponse(
        default=registry.default_id(),
        models=[ModelView(**card.as_dict()) for card in registry.cards()],
    )


@router.post("/v1/try-on", response_model=JobView)
async def create_tryon(
    request: Request,
    response: Response,
    person_image: UploadFile = File(...),
    garment_image: UploadFile | None = File(default=None),
    garment_url: str = Form(""),
    mask_image: UploadFile | None = File(default=None),
    category: str = Form("tops"),
    garment_photo_type: str = Form("model"),
    model: str = Form(""),
    seed: int = Form(42),
    num_timesteps: int | None = Form(default=None),
    guidance_scale: float | None = Form(default=None),
    segmentation_free: str | None = Form(default=None),
    webhook_url: str | None = Form(default=None),
    wait_seconds: int = Form(0),
) -> JobView:
    identity = _require_owner(request)
    state = _state(request)
    settings = state.settings
    try:
        state.limiter.hit(identity)
    except RateLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc

    if category not in CATEGORIES:
        raise HTTPException(status_code=422, detail="category: tops, bottoms или one-pieces.")
    if garment_photo_type not in PHOTO_TYPES:
        raise HTTPException(status_code=422, detail="garment_photo_type: model или flat-lay.")
    if not 0 <= seed <= 2_147_483_647:
        raise HTTPException(status_code=422, detail="seed должен быть от 0 до 2147483647.")
    if num_timesteps is not None and not 10 <= num_timesteps <= 60:
        raise HTTPException(status_code=422, detail="num_timesteps должен быть от 10 до 60.")
    if guidance_scale is not None and not 0 <= guidance_scale <= 50:
        raise HTTPException(status_code=422, detail="guidance_scale должен быть от 0 до 50.")
    wait_seconds = min(120, max(0, wait_seconds))

    try:
        webhook = check_webhook(webhook_url)
        model_id = state.registry.resolve(model or None)
        state.registry.require_available(model_id)
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    try:
        person = open_image(await _read_upload(person_image), max_bytes=settings.max_upload_bytes)
        garment = await _garment_from_request(garment_image, garment_url, settings.max_upload_bytes)
        mask = None
        if mask_image is not None and mask_image.filename:
            raw_mask = await _read_upload(mask_image)
            if raw_mask:
                mask = open_mask(raw_mask, max_bytes=settings.max_upload_bytes)
    except (ImageError, PageFetchError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    job_id = "job_" + uuid.uuid4().hex
    folder = state.runner.job_dir(job_id)
    folder.mkdir(parents=True, exist_ok=False)
    save_jpeg(person, folder / "person.jpg")
    save_jpeg(garment, folder / "garment.jpg")
    if mask is not None:
        save_png(mask, folder / "mask.png")

    now = iso(utcnow())
    job = Job(
        id=job_id,
        owner_id=identity,
        status="queued",
        model=model_id,
        category=category,
        garment_photo_type=garment_photo_type,
        seed=seed,
        num_timesteps=num_timesteps,
        guidance_scale=guidance_scale,
        segmentation_free=_parse_bool(segmentation_free, True),
        webhook_url=webhook,
        error=None,
        created_at=now,
        updated_at=now,
        started_at=None,
        finished_at=None,
    )
    state.store.create(job)
    state.runner.submit(job_id)

    if wait_seconds:
        deadline = time.monotonic() + wait_seconds
        while time.monotonic() < deadline:
            current = state.store.get(job_id)
            if current and current.status in {"succeeded", "failed"}:
                return _job_view(current, settings.public_base_url, state.runner)
            await asyncio.sleep(0.05)
    current = state.store.get(job_id) or job
    if current.status in {"queued", "running"}:
        response.status_code = 202
    return _job_view(current, settings.public_base_url, state.runner)


@router.get("/v1/try-on/{job_id}", response_model=JobView)
def get_tryon(job_id: str, request: Request) -> JobView:
    job = _own_job(request, job_id)
    state = _state(request)
    return _job_view(job, state.settings.public_base_url, state.runner)


@router.get("/v1/try-on/{job_id}/result")
def get_result(job_id: str, request: Request) -> FileResponse:
    job = _own_job(request, job_id)
    if job.status != "succeeded":
        raise HTTPException(status_code=409, detail="Результат ещё не готов.")
    path = _state(request).runner.result_path(job_id)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Файл результата удалён.")
    return FileResponse(path, media_type="image/png", filename="tryon.png")


async def _garment_from_request(upload: UploadFile | None, garment_url: str, max_bytes: int):
    raw = b""
    if upload is not None and upload.filename:
        raw = await _read_upload(upload)
    if raw:
        return open_image(raw, max_bytes=max_bytes)
    if garment_url.strip():
        return await asyncio.to_thread(garment_from_url, garment_url, max_image_bytes=max_bytes)
    raise ImageError("Нужно фото вещи или ссылка на страницу товара.")


async def _read_upload(upload: UploadFile) -> bytes:
    try:
        return await upload.read()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Не удалось прочитать файл.") from exc
