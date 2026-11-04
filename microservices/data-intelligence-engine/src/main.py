# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Engine service entrypoint.

Asset library management, data ingestion, retrieval, and database management. An
**asset library** (data-intelligence-engine/src/assetlib/library.py) is a set of assets, the sources
they are materialized into, and the pools that pair the two. Document assets can
be materialized into vector or graph sources and retrieved through their pools.
The service also ships a static console UI at /console.

All runtime state lives in the workspace (ENGINE_WORKSPACE, default
`data-intelligence-engine/workspace`): the Milvus volumes, the models, the uploaded files, and the
libraries themselves — which are restored from it on startup.

Run: data-intelligence-engine
"""

import logging
import os
from contextlib import asynccontextmanager

import uvicorn

import config
from api import (
    asset_library,
    databases,
    models,
    retrieval,
)
from core.knowledge.extraction_jobs import ExtractionScheduler
from core.manager import registry
from databasehub import repository as database_repository
from databasehub.manager import database_manager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles


def _configure_logging() -> None:
    """Show the engine's own log lines (background work has no request log).

    Only the engine's packages get a handler, so third-party libraries keep
    their own levels; they do not propagate to the root, so nothing prints twice.
    """
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(name)s - %(message)s"))
    for name in ("api", "assetlib", "core", "databasehub"):
        engine_logger = logging.getLogger(name)
        if not engine_logger.handlers:
            engine_logger.addHandler(handler)
        engine_logger.setLevel(config.LOG_LEVEL)
        engine_logger.propagate = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Bring back what the workspace holds: databases first, then libraries.

    The order is load-bearing. A library's sources name a `database_id`, and
    building a pool's projection resolves it, so the databases have to be
    registered before anything asks. A library whose database is missing still
    restores -- with the source reported unreconciled -- rather than being
    dropped, which would erase it from the next save.
    """
    # A database the hub registers for itself -- the workspace content store,
    # on a library's first ingest -- has no API caller to persist it, so it
    # writes through this.
    _configure_logging()
    database_manager.persist = lambda: database_repository.save(database_manager)
    databases = database_manager.restore(database_repository.load())
    print(
        f"Workspace {config.WORKSPACE_DIR}: restored {len(databases)} database"
        + ("" if len(databases) == 1 else "s")
        + (f" ({', '.join(databases)})" if databases else "")
    )
    restored = registry.restore()
    print(f"Workspace {config.WORKSPACE_DIR}: restored {len(restored)} asset librar"
          + ("y" if len(restored) == 1 else "ies")
          + (f" ({', '.join(restored)})" if restored else ""))
    if not databases:
        print(
            "No databases are registered. Asset content will go to the "
            f"workspace store ({config.CONTENT_DIR}), registered on first use; "
            "a vector or graph source cannot be created until one is: "
            "POST /v1/databases"
        )
    # Graph sources whose OKF extraction runs on a cron.
    scheduler = ExtractionScheduler(registry.list)
    scheduler.start()
    yield
    scheduler.stop()
    database_manager.close()


app = FastAPI(title="Data Intelligence Engine", lifespan=lifespan)


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    """Invalid input (unknown asset library, unsupported retriever type) is a
    client error; without this it would surface to the caller as a 500."""
    message = str(exc)
    status_code = 404 if "not found" in message.lower() else 400
    return JSONResponse(status_code=status_code, content={"detail": message})
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ALLOW_ORIGINS,
    allow_credentials=config.CORS_ALLOW_CREDENTIALS,
    allow_methods=config.CORS_ALLOW_METHODS,
    allow_headers=config.CORS_ALLOW_HEADERS,
)

app.include_router(asset_library.router)
app.include_router(retrieval.router)
app.include_router(models.router)
app.include_router(databases.router)


@app.get("/health")
def health():
    """Liveness, plus what this engine is holding.

    `databases` counts registrations, not live connections -- a registered
    database that is unreachable still counts here. `POST
    /v1/databases/{id}/check` is what answers reachability.
    """
    return {
        "service": "engine",
        "status": "ok",
        "workspace": config.WORKSPACE_DIR,
        "databases": len(database_manager.list_databases()),
        "asset_libraries": len(registry.list()),
    }


@app.get("/")
def root():
    return RedirectResponse(url="/console/")


# Static console UI (asset-library management + retrieval/reranking). Mounted last, under an
# explicit prefix so it never shadows /health or the /v1 API routes.
_CONSOLE_DIR = os.path.join(os.path.dirname(__file__), "console")
if os.path.isdir(_CONSOLE_DIR):
    app.mount("/console", StaticFiles(directory=_CONSOLE_DIR, html=True), name="console")


def run():
    uvicorn.run(app, host=config.HOST, port=config.PORT)


if __name__ == "__main__":
    run()
