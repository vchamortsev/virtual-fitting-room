"""Точка входа FastAPI."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api.routes import router
from app.config import get_settings
from app.core.leads import LeadStore
from app.core.runner import JobRunner
from app.core.security import RateLimiter
from app.core.store import JobStore
from app.providers.registry import ProviderRegistry

STATIC_DIR = Path(__file__).resolve().parent / "static"
log = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings = get_settings()
    store = JobStore(settings.data_dir / "jobs.sqlite")
    registry = ProviderRegistry(settings)
    runner = JobRunner(
        store=store,
        registry=registry,
        data_dir=settings.data_dir,
        retention_hours=settings.retention_hours,
        public_base_url=settings.public_base_url,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )
        app.state.settings = settings
        app.state.store = store
        app.state.registry = registry
        app.state.runner = runner
        app.state.limiter = RateLimiter(settings.rate_limit_per_minute)
        app.state.leads = LeadStore(settings.data_dir / "leads.sqlite")
        app.state.lead_limiter = RateLimiter(8)
        runner.start()
        log.info(
            "Примерочная %s слушает задания. Модель по умолчанию: %s",
            __version__,
            registry.default_id(),
        )
        yield
        runner.stop()
        store.close()
        app.state.leads.close()

    app = FastAPI(
        title="Виртуальная примерочная",
        version=__version__,
        summary="Локальный API примерки одежды для небольших магазинов.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.parsed_cors_origins,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )
    app.include_router(router)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def root():
        return FileResponse(STATIC_DIR / "landing.html")

    @app.get("/demo", include_in_schema=False)
    def demo():
        return FileResponse(STATIC_DIR / "demo.html")

    return app
