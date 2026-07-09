# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.routers import pipelines
from config.loader import load_legacy_config
from core.pipeline_manager import PipelineManager

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

handler = logging.StreamHandler()
handler.setFormatter(
    logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%SZ",
    )
)

for _uvicorn_logger in ("uvicorn", "uvicorn.error", "uvicorn.access"):
    _logger = logging.getLogger(_uvicorn_logger)
    _logger.setLevel(os.environ.get("WEB_SERVER_LOG_LEVEL", "WARNING").upper())
    _logger.handlers = [handler]
    _logger.propagate = False

# Configure the root logger so all module loggers (e.g. core.pipeline_manager)
# inherit the application log level and emit through the shared handler.
root_logger = logging.getLogger()
root_logger.setLevel(os.environ.get("APP_LOG_LEVEL", "INFO").upper())
root_logger.handlers = [handler]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("DL Streamer Pipeline Server (dlsps2) starting…")
    pipeline_manager = PipelineManager()
    pipelines.set_pipeline_manager(pipeline_manager)

    try:
        legacy_config = load_legacy_config()
        pipelines.set_legacy_config(legacy_config)
        logger.info(
            "Loaded %d pipeline(s) from config",
            len(legacy_config.pipelines),
        )
    except FileNotFoundError:
        logger.info("No config.json found — named pipeline API disabled")

    yield
    logger.info("DL Streamer Pipeline Server (dlsps2) shutting down…")
    pipeline_manager.shutdown()


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="DL Streamer Pipeline Server API",
    description="REST API for managing DL Streamer pipeline instances.",
    version="2.0.0",
    lifespan=lifespan,
)

app.include_router(pipelines.router)
