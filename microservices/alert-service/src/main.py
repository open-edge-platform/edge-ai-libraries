"""FastAPI application entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.api.router import api_router
from src.core.config import load_config
from src.core.settings import settings
from src.worker import AlertWorker

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: load config, start worker. Shutdown: stop worker."""
    config = load_config(settings.CONFIG_PATH)
    logger.info(
        "Loaded config: %d subscriptions", len(config.subscriptions)
    )

    worker = AlertWorker(config)
    app.state.worker = worker
    app.state.config = config
    await worker.start()

    yield

    await worker.stop()


app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    description="Config-driven async Alert Service with deduplication and pluggable delivery",
    debug=settings.DEBUG,
    lifespan=lifespan,
)

app.include_router(api_router, prefix=settings.API_V1_PREFIX)
