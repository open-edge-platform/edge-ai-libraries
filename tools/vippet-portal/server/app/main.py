"""ViPPET Portal — aggregates benchmark and test results from many ViPPET instances."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI

from . import aggregator
from .db import init_db
from .routers import benchmarks, experiments, instances, tests

logging.basicConfig(level=logging.INFO)
# One INFO line per upstream call drowns out real errors; failures still surface via WARNING.
logging.getLogger("httpx").setLevel(logging.WARNING)

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
