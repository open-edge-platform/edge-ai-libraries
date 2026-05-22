# SPDX-License-Identifier: Apache-2.0
"""
Minimal FastAPI application serving only the /servers REST API endpoints.

This is the **central** servers host — other ViPPET instances point their
``SERVERS_HOST`` env var at this machine's IP so they proxy all server
registry calls here instead of connecting to a database directly.

Requires ``DATABASE_URL`` to be set (PostgreSQL).
Starts immediately with no dependency on GStreamer, VideosManager,
PipelineManager, or any other heavy service.

Usage (from the vippet/ directory):
    DATABASE_URL=postgresql://... PYTHONPATH=. uvicorn api.servers_app:app --host 0.0.0.0 --port 7860
"""

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import servers
from database import init_db

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
logger = logging.getLogger()
logger.setLevel(os.environ.get("APP_LOG_LEVEL", "INFO").upper())
logger.handlers = [handler]

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
try:
    init_db()
    logger.info("Database initialised successfully")
except Exception as _db_err:
    logger.warning(
        "Database initialisation failed (server registration will be unavailable): %s",
        _db_err,
    )

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="ViPPET Servers API",
    description="Minimal server-registration endpoints — no pipeline or media services required.",
    version="1.0.0",
    root_path="/api/v1",
    servers=[{"url": "/api/v1"}],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(servers.router, prefix="/servers", tags=["servers"])
