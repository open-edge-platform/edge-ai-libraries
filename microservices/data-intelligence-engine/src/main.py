# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import logging
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
from console_ui import ConsoleStaticFiles, console_directory
from databasehub import repository as database_repository
from databasehub.manager import database_manager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse


def _configure_logging() -> None:
    """Attach a log handler to the engine's own packages only, without propagating to root."""
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
    """Restore the workspace: databases first (sources resolve their `database_id`), then libraries."""
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
    """Report a ValueError as 404 (not found) or 400 rather than 500."""
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
    """Liveness, plus what this engine holds; `databases` counts registrations, not live connections."""
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


# Mount only build output, never the frontend sources or dependencies.
_CONSOLE_DIR = console_directory()
app.mount(
    "/console",
    ConsoleStaticFiles(directory=_CONSOLE_DIR, html=True, check_dir=False),
    name="console",
)


def run():
    uvicorn.run(app, host=config.HOST, port=config.PORT)


if __name__ == "__main__":
    run()
