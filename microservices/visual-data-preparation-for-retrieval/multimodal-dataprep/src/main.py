# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
FastAPI application entry point for VDMS DataPrep microservice.

This module initializes the FastAPI application with all necessary middleware,
routers, and configuration for the Visual Data Management System (VDMS) based
data preparation microservice.
"""

import asyncio
import json
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.common import logger, settings
from src.common.schema import DataPrepResponse, StatusEnum
from src.core.vectorstores import get_vector_store
from src.endpoints import (
    batch_ingest_router,
    check_health_router,
    delete_video_router,
    download_video_router,
    ingest_image_router,
    list_videos_router,
    process_document_router,
    process_minio_video_router,
    telemetry_router,
    upload_and_process_video_router,
)

# Dump loaded settings, if in debug mode
logger.debug(f"Settings loaded: {settings.model_dump()}")

_SENSITIVE_KEYS = ("PASSWORD", "SECRET", "TOKEN", "ACCESS_KEY")


def _mask_settings_for_log(raw_settings: dict[str, Any]) -> dict[str, Any]:
    """Mask sensitive values before logging settings."""

    masked: dict[str, Any] = {}
    for key, value in raw_settings.items():
        key_upper = key.upper()
        if isinstance(value, dict):
            masked[key] = _mask_settings_for_log(value)
            continue

        if value is not None and any(token in key_upper for token in _SENSITIVE_KEYS):
            masked[key] = "***"
        else:
            masked[key] = value
    return masked


def _log_runtime_settings() -> None:
    """Log sanitized settings for observability."""

    try:
        raw_settings = settings.model_dump()
    except Exception as exc:  # pragma: no cover - defensive guard
        logger.error("Unable to serialize settings for logging: %s", exc)
        return

    masked = _mask_settings_for_log(raw_settings)
    logger.info("Resolved settings: %s", json.dumps(masked, indent=2, default=str))


async def _run_startup_preloads() -> None:
    """Warm up embedding and detection models during application startup."""

    try:
        from src.core.embedding.embedding_helper import (
            preload_object_detector,
            preload_embedding_client,
        )
        from src.core.utils.config_utils import get_config
    except Exception as exc:  # pragma: no cover - defensive guard
        logger.error("Skipping startup preloads due to import error: %s", exc)
        return

    config = get_config()
    detection_config = config.get("object_detection", {})
    enable_detection = detection_config.get("enabled", True)
    detection_confidence = detection_config.get("confidence_threshold", 0.85)

    tasks: list[tuple[str, asyncio.Future]] = []

    logger.info("Startup preload: warming up embedding client")
    tasks.append(("embedding", asyncio.ensure_future(asyncio.to_thread(preload_embedding_client))))

    logger.info(
        "Startup preload: warming up object detector (enabled=%s, confidence=%.2f)",
        enable_detection,
        detection_confidence,
    )
    tasks.append(
        (
            "detector",
            asyncio.ensure_future(
                asyncio.to_thread(
                    preload_object_detector,
                    enable_detection,
                    detection_confidence,
                )
            ),
        )
    )

    if not tasks:
        return

    results = await asyncio.gather(*(task for _, task in tasks), return_exceptions=True)

    summary: dict[str, bool] = {}
    for (label, _), result in zip(tasks, results):
        if isinstance(result, Exception):
            logger.error("Startup preload '%s' failed: %s", label, result)
            summary[label] = False
        else:
            summary[label] = bool(result)
            logger.info("Startup preload '%s' completed (success=%s)", label, summary[label])

    if summary and not all(summary.values()):
        logger.warning("One or more startup preloads reported issues: %s", summary)
    elif summary:
        logger.info("All startup preloads completed successfully")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager to handle startup and shutdown operations."""

    logger.info("Starting Multimodal-Dataprep Service . . .")
    _log_runtime_settings()

    await _run_startup_preloads()

    try:
        yield
    finally:
        # Flush/refresh the active vector store index before teardown. This is a
        # backend-agnostic call: VDMS persists its descriptor-set index, Milvus
        # is a no-op (eager indexing).
        try:
            logger.info("Updating vector store index before tearing down . . .")
            get_vector_store().update_index()
            logger.info("Vector store index updated successfully.")
        except Exception as exc:  # pragma: no cover - best effort logging
            logger.error(f"Error updating vector store index: {exc}")

        logger.info("Tearing down Multimodal-Dataprep Service . . .")


# Initialize FastAPI app
app = FastAPI(
    title=settings.APP_DISPLAY_NAME,
    description=settings.APP_DESC,
    root_path="/v1/dataprep",
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOW_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=settings.ALLOW_METHODS.split(","),
    allow_headers=settings.ALLOW_HEADERS.split(","),
)


# Setting up custom error message format
@app.exception_handler(HTTPException)
async def custom_exception_handler(request, exc):
    """Custom exception handler for HTTP exceptions.
    
    Args:
        request: The incoming request object
        exc: The HTTPException that was raised
        
    Returns:
        JSONResponse: A standardized error response using DataPrepResponse format
    """
    error_res = DataPrepResponse(status=StatusEnum.error, message=exc.detail)
    return JSONResponse(content=error_res.model_dump(), status_code=exc.status_code)


# Include routers from endpoints modules

# Health endpoint
app.include_router(check_health_router)

# Document processing endpoint
app.include_router(process_document_router)

# Video processing endpoints
app.include_router(process_minio_video_router)
app.include_router(upload_and_process_video_router)
app.include_router(batch_ingest_router)
app.include_router(ingest_image_router)

# Telemetry endpoints
app.include_router(telemetry_router)

# Video management endpoints
app.include_router(list_videos_router)
app.include_router(download_video_router)
app.include_router(delete_video_router)

