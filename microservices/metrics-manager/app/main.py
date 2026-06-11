# Copyright (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Metrics Manager - Unified metrics collection, ingestion, and relay service.

This service provides:
1. SSE streaming endpoint (/metrics/stream) for real-time metric delivery to clients
2. REST API endpoints for pushing custom metrics
3. Multiple input format support (JSON, InfluxDB Line Protocol, OpenTelemetry)
4. Prometheus-compatible metrics endpoint
5. Health and status monitoring

The service is designed to be deployed alongside any application that needs
system metrics visualization and custom metrics ingestion.
"""

import time
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Receive, Scope, Send

from .logging_config import get_logger, set_correlation_id, setup_logging
from .metrics import get_service_metrics
from .rate_limit import RateLimitMiddleware
from .responses import ServiceInfoResponse
from .routes import router as routes_router
from .settings import get_settings
from .sse import router as sse_router
from .store import get_metrics_store

logger = get_logger("main")


class CorrelationIdMiddleware:
    """Pure-ASGI middleware that adds correlation IDs and records request metrics."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())[:8]
        set_correlation_id(correlation_id)
        start_time = time.perf_counter()
        status_code = 200

        async def send_with_correlation(message: Any) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message.get("status", 200)
                headers = MutableHeaders(scope=message)
                headers.append("X-Correlation-ID", correlation_id)
            await send(message)

        try:
            await self.app(scope, receive, send_with_correlation)
        except Exception:
            latency_ms = (time.perf_counter() - start_time) * 1000
            get_service_metrics().record_request(success=False, latency_ms=latency_ms)
            raise

        latency_ms = (time.perf_counter() - start_time) * 1000
        get_service_metrics().record_request(
            success=status_code < 400, latency_ms=latency_ms
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle - startup and shutdown."""
    setup_logging()  # configure logging here so settings errors surface cleanly
    settings = get_settings()
    service_metrics = get_service_metrics()

    logger.info(
        "Starting Metrics Manager",
        extra={
            "version": settings.service_version,
            "environment": settings.environment,
            "port": settings.metrics_port,
        },
    )

    # Initialize metrics store
    store = get_metrics_store()
    stats = await store.get_stats()
    logger.info("Metrics store initialized", extra={"stats": stats})

    yield

    # Graceful shutdown - release resources
    logger.info(
        "Shutting down Metrics Manager",
        extra={"uptime_seconds": service_metrics.uptime_seconds},
    )
    await store.close()


# Initialize FastAPI app
settings = get_settings()

app = FastAPI(
    title="Metrics Manager",
    description="""
    Unified metrics collection, ingestion, and relay service.

    ## Features

    - **SSE Stream**: Real-time metrics from Telegraf via Server-Sent Events
    - **Custom Metrics API**: Push custom metrics via REST API
    - **Multiple Formats**: Support for JSON, InfluxDB Line Protocol, OpenTelemetry
    - **Prometheus Compatible**: Export metrics in Prometheus format
    - **Rate Limiting**: Configurable rate limiting for API protection
    - **Structured Logging**: JSON-formatted logs with correlation IDs

    ## Quick Start

    1. Push a metric: `POST /api/v1/metrics/simple {"name": "fps", "value": 29.97}`
    2. Get metrics: `GET /api/v1/metrics/latest`
    3. Stream metrics: `GET /metrics/stream`
    """,
    version=settings.service_version,
    lifespan=lifespan,
    docs_url="/docs" if settings.is_development else None,
    redoc_url="/redoc" if settings.is_development else None,
)

# Add middleware (order matters - last added is outermost/executes first)
# CORS (innermost)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting
app.add_middleware(RateLimitMiddleware)

# GZip compression for responses
if settings.enable_gzip_compression:
    app.add_middleware(GZipMiddleware, minimum_size=1000)

# Correlation ID tracking (outermost - added last)
app.add_middleware(CorrelationIdMiddleware)

# Include routers
app.include_router(sse_router)
app.include_router(routes_router)


@app.get("/", response_model=ServiceInfoResponse, tags=["info"])
async def root() -> ServiceInfoResponse:
    """Root endpoint with service information."""
    return ServiceInfoResponse(
        service="Metrics Manager",
        version=settings.service_version,
        description="Unified metrics collection, ingestion, and relay service",
        endpoints={
            "sse": {
                "stream": "GET /metrics/stream",
            },
            "metrics_api": {
                "push_batch": "POST /api/v1/metrics",
                "push_simple": "POST /api/v1/metrics/simple",
                "push_influx": "POST /api/v1/metrics/influx",
                "push_otlp": "POST /api/v1/metrics/otlp",
                "get_metrics": "GET /api/v1/metrics",
                "get_latest": "GET /api/v1/metrics/latest",
                "get_names": "GET /api/v1/metrics/names",
                "clear": "DELETE /api/v1/metrics",
            },
            "prometheus": {
                "metrics": "GET /metrics",
                "write": "POST /write",
                "service_metrics": "GET /api/v1/stats",
            },
            "health": {
                "basic": "GET /health",
                "detailed": "GET /api/health",
            },
        },
    )


@app.get("/api/v1/stats", tags=["monitoring"])
async def get_stats() -> dict[str, Any]:
    """
    Get internal service statistics.

    Returns operational metrics for the service including request counts,
    latencies, and SSE statistics.
    """
    return get_service_metrics().to_dict()


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.metrics_port,
        reload=settings.is_development,
        log_level=settings.log_level.lower(),
    )
