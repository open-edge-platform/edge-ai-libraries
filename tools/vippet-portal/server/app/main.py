"""ViPPET Portal — aggregates benchmark and test results from many ViPPET instances."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import aggregator
from .db import init_db
from .routers import benchmarks, experiments, instances, tests

logging.basicConfig(level=logging.INFO)
# One INFO line per upstream call drowns out real errors; failures still surface via WARNING.
logging.getLogger("httpx").setLevel(logging.WARNING)

UI_DIST = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    yield
    await aggregator.close_http_client()


app = FastAPI(
    title="ViPPET Portal",
    description="Aggregates benchmark, performance and density results from multiple ViPPET instances.",
    version="0.1.0",
    lifespan=lifespan,
)

api = APIRouter(prefix="/api/v1")
api.include_router(instances.router)
api.include_router(benchmarks.router)
api.include_router(experiments.router)
api.include_router(tests.router)


@api.get("/health", tags=["health"], operation_id="get_health")
async def get_health() -> dict[str, bool]:
    return {"healthy": True}


app.include_router(api)

if UI_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=UI_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str) -> FileResponse:
        candidate = UI_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(UI_DIST / "index.html")
