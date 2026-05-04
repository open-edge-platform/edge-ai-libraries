# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from src.common.logger import get_logger
from src.common.middleware import request_id_middleware
from src.common.schema import (
    BatchQueryResponse,
    FilterCapabilitiesResponse,
    HealthResponse,
    QueryRequest,
)
from src.common.settings import settings
from src.retriever.batch_executor import execute_batch
from src.retriever.backend_factory import check_ready, get_filter_capabilities


logger = get_logger()


def _utc_timestamp() -> str:
    """Return an ISO-8601 UTC timestamp with Z suffix."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

app = FastAPI(
    title=settings.APP_DISPLAY_NAME,
    description=settings.APP_DESC,
)
app.middleware("http")(request_id_middleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Return service liveness status."""
    return HealthResponse(status="ok", timestamp=_utc_timestamp())


@app.get("/ready", response_model=HealthResponse)
async def readiness_check() -> HealthResponse:
    """Validate runtime dependencies and return readiness status."""
    try:
        check_ready()
        return HealthResponse(status="ready", timestamp=_utc_timestamp())
    except Exception as exc:
        logger.exception("Readiness check failed")
        raise HTTPException(status_code=503, detail="Service not ready")


@app.post("/query", response_model=BatchQueryResponse)
async def query_endpoint(request: Request, payload: list[QueryRequest]) -> BatchQueryResponse:
    """Execute a batch of semantic retrieval queries."""
    if not payload:
        raise HTTPException(status_code=400, detail="Request body must contain at least one query")

    request_id = getattr(request.state, "request_id", str(uuid4()))

    try:
        results, errors = await execute_batch(payload)
        response = BatchQueryResponse(
            request_id=request_id,
            results=results,
            errors=errors,
        )
        logger.info(
            "Completed batch query request_id=%s query_count=%d result_count=%d error_count=%d",
            request_id,
            len(payload),
            len(results),
            len(errors),
        )
        return response
    except Exception as exc:
        logger.exception("Unhandled failure while processing batch request_id=%s", request_id)
        raise HTTPException(
            status_code=500,
            detail=f"Query execution failed. Contact support with request_id={request_id}",
        )


@app.get("/capabilities/filters", response_model=FilterCapabilitiesResponse)
async def filter_capabilities_endpoint(
    backend: str | None = Query(default=None),
) -> FilterCapabilitiesResponse:
    """Return filter grammar capabilities for supported backends."""
    try:
        return get_filter_capabilities(backend_name=backend)
    except NotImplementedError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
