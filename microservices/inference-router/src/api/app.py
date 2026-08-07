# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""FastAPI application factory."""

import json
import asyncio
import logging
import time
import traceback
from pathlib import Path
from typing import Optional

from fastapi.encoders import jsonable_encoder
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.config import RouterConfig
from src.router import RouterOrchestrator
from src.router.logging_utils import log_to_gateway_file
from src.observability import Telemetry

from src.api.concurrency import (
    get_active_requests,
    get_max_concurrency,
    set_max_concurrency,
)


logger = logging.getLogger("gateway")


def _sanitize_validation_errors(errors: list[object]) -> list[object]:
    """Convert validation errors into JSON-safe data for API responses."""
    return json.loads(json.dumps(errors, default=str))


def create_app(
    router: RouterOrchestrator,
    config: RouterConfig,
    telemetry: Optional[Telemetry] = None,
    *,
    config_path: Optional[Path] = None,
    max_concurrency: int = 0,
    verbose: bool = False,
    verbose_full: bool = False,
    log_dir: Optional[Path] = None,
) -> FastAPI:
    """
    Create FastAPI application with configured middleware and routes.

    Args:
        router: RouterOrchestrator instance
        config: RouterConfig with settings
        telemetry: Optional telemetry backend (InMemoryTelemetry, FileBasedTelemetry).
        max_concurrency: Max concurrent in-flight chat requests. ``0`` = unlimited.
            Enforced by ``concurrency_guard`` on the chat endpoint.
        verbose: When ``True``, endpoints print raw backend responses.
        verbose_full: When ``True``, endpoints additionally log raw request bodies.
        log_dir: When set, endpoints additionally append verbose dumps to
            ``<log_dir>/gateway.log`` and per-request log files.

    Returns:
        FastAPI application instance
    """
    app = FastAPI(
        title="Inference Router",
        description="A pluggable inference router for chat completion requests",
        version="0.1.0",
    )

    # Store router + diagnostic settings on app state for use by endpoints.
    app.state.router = router
    app.state.plugin_manager = router.plugin_manager
    app.state.telemetry = telemetry
    app.state.config = config
    app.state.config_path = config_path
    app.state.config_lock = asyncio.Lock()
    app.state.verbose = verbose
    app.state.verbose_full = verbose_full
    app.state.log_dir = log_dir

    # Apply concurrency limit. The guard reads this via module state, so it
    # must be set before any endpoint depends on it.
    set_max_concurrency(max_concurrency)

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Import and include routers
    from src.api.v1 import config as v1_config_router
    from src.api.v1 import passthrough as v1_passthrough_router
    from src.api.v1 import plugin as v1_plugin_router
    from src.api.v1 import policy as v1_policy_router
    from src.api.v1 import provider as v1_provider_router
    from src.api.v1 import router as v1_router
    from src.api.v1 import strategy as v1_strategy_router

    app.include_router(v1_router.router, prefix="/v1")
    app.include_router(v1_config_router.router, prefix="/v1")
    # Pass-through routes carry their full public path (e.g. "/v1/ocr") from the
    # service registry, so they are included without an extra prefix.
    app.include_router(v1_passthrough_router.router)

    # Generic plugin endpoint registry: mount any router a plugin *type* opts to
    # contribute via ``PluginBaseNode.routes()``. Mounted once per type under
    # ``/v1``, and BEFORE the generic plugin router so a plugin's specific paths
    # (e.g. ``/plugins/dummy_logger/ping``) take precedence over the parametrized
    # ``/plugins/{node}/{name}`` catch-all. A failing plugin must not break app
    # assembly, so each mount is isolated — log and continue.
    from src.plugins.manager import iter_registered_plugin_classes

    for plugin_cls in iter_registered_plugin_classes():
        try:
            plugin_router = plugin_cls.routes()
        except Exception:
            logger.warning(
                "Plugin %s.routes() raised; skipping its endpoints",
                plugin_cls.__name__,
                exc_info=True,
            )
            continue
        if plugin_router is None:
            continue
        app.include_router(plugin_router, prefix="/v1")
        logger.info(
            "Mounted plugin-contributed routes for node '%s'", plugin_cls.plugin_type()
        )

    app.include_router(v1_plugin_router.router, prefix="/v1")
    app.include_router(v1_provider_router.router, prefix="/v1")
    app.include_router(v1_policy_router.router, prefix="/v1")
    app.include_router(v1_strategy_router.router, prefix="/v1")

    # Root path — advertises the public endpoints.
    @app.get("/")
    async def root():
        return {
            "name": "Inference Router API",
            "version": "0.1.0",
            "status": "running",
            "endpoints": {
                "health": "/health",
                "chat": "/v1/chat/completions",
                "models": "/v1/models",
                "metrics": "/v1/metrics",
                "config": "/v1/config",
                "routing": "/v1/routing",
                "providers": "/v1/providers",
                "policies": "/v1/policies",
                "strategies": "/v1/strategies",
                "audio_transcriptions": "/v1/audio/transcriptions",
                "audio_speech": "/v1/audio/speech",
                "embeddings": "/v1/embeddings",
                "rerank": "/v1/rerank",
                "ocr": "/v1/ocr",
            },
        }

    # Health check endpoint with concurrency status.
    @app.get("/health")
    async def health():
        max_conc = get_max_concurrency()
        return {
            "status": "healthy",
            "router": "initialized",
            "timestamp": int(time.time()),
            "concurrency": {
                "active_requests": get_active_requests(),
                "max_concurrency": max_conc if max_conc > 0 else "unlimited",
            },
        }

    # Detailed health check with provider status.
    @app.get("/health/detailed")
    async def health_detailed():
        provider_health = await router.health_check()
        return {
            "status": "healthy",
            "providers": provider_health,
        }

    # Validation error handler — logs the offending request body so 422s are
    # debuggable. ``log_dir`` is captured from the closure.
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        raw_body = (await request.body()).decode("utf-8", errors="replace")
        error_details = _sanitize_validation_errors(exc.errors())

        msg = "❌ Request validation failed"
        print(msg)
        log_to_gateway_file(msg, log_dir)
        logger.error(f"Request validation failed: {request.method} {request.url.path}")

        msg = f"   Path: {request.method} {request.url.path}"
        print(msg)
        log_to_gateway_file(msg, log_dir)

        msg = f"   Body: {raw_body}"
        print(msg)
        log_to_gateway_file(msg, log_dir)
        logger.debug(f"Request body: {raw_body}")

        msg = f"   Errors: {error_details}"
        print(msg)
        log_to_gateway_file(msg, log_dir)
        logger.error(f"Validation errors: {error_details}")

        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "message": "Request validation failed",
                    "type": "RequestValidationError",
                    "detail": error_details,
                    "body": None,
                }
            },
        )

    # Catch-all handler — preserves the full traceback in logs while returning
    # a sanitised error to the client.
    @app.exception_handler(Exception)
    async def global_exception_handler(_request: Request, exc: Exception):
        msg = f"❌ Unhandled exception: {type(exc).__name__}: {exc}"
        print(msg)
        log_to_gateway_file(msg, log_dir)
        log_to_gateway_file(traceback.format_exc(), log_dir)
        logger.error(f"Unhandled exception: {type(exc).__name__}: {exc}")
        logger.debug(f"Traceback: {traceback.format_exc()}")

        return JSONResponse(
            status_code=500,
            content={"error": {"message": "Internal server error", "type": type(exc).__name__}},
        )

    logger.info(f"Created FastAPI app with {len(app.routes)} routes")
    return app
