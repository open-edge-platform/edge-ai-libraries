# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
FastAPI application entry point for VDMS DataPrep microservice.

This module initializes the FastAPI application with all necessary middleware,
routers, and configuration for the Visual Data Management System (VDMS) based
data preparation microservice.
"""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from langchain_vdms.vectorstores import VDMS_Utils

from src.common import logger, settings
from src.common.schema import DataPrepResponse, StatusEnum
from src.core.embedding import _client_cache
from src.endpoints import (
    check_health_router,
    delete_video_router,
    download_video_router,
    list_videos_router,
    process_document_router,
    process_minio_video_router,
    upload_and_process_video_router,
)

# Dump loaded settings, if in debug mode
logger.debug(f"Settings loaded: {settings.model_dump()}")


async def _run_startup_preloads() -> None:
    """Warm up embedding and detection models during application startup."""

    try:
        from src.core.embedding.sdk_embedding_helper import (
            preload_object_detector,
            preload_sdk_client,
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

    if settings.EMBEDDING_PROCESSING_MODE.lower() == "sdk":
        logger.info("Startup preload: warming up SDK embedding client")
        tasks.append(("sdk", asyncio.ensure_future(asyncio.to_thread(preload_sdk_client))))
    else:
        logger.info(
            "Startup preload: embedding mode '%s' does not require SDK warmup",
            settings.EMBEDDING_PROCESSING_MODE,
        )

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

    logger.info("Starting VDMS-Dataprep Service . . .")

    await _run_startup_preloads()

    try:
        yield
    finally:
        clients_to_update: list[tuple[str, object]] = []

        if _client_cache:
            for client_key, client_wrapper in _client_cache.items():
                client = getattr(client_wrapper, "client", None)
                if client is not None:
                    clients_to_update.append((client_key, client))

        try:
            from src.core.embedding.sdk_embedding_helper import _sdk_client
        except Exception:  # pragma: no cover - defensive import guard
            _sdk_client = None

        if _sdk_client is not None:
            sdk_client = getattr(_sdk_client, "vdms_client", None)
            if sdk_client is not None:
                clients_to_update.append(("sdk_client", sdk_client))

        if clients_to_update:
            logger.info("Updating VDMS index before tearing down . . .")

        for client_key, client in clients_to_update:
            try:
                vdms_utils = VDMS_Utils(client)
                query = vdms_utils.add_descriptor_set(
                    "FindDescriptorSet",
                    name=settings.DB_COLLECTION,
                    storeIndex=True,
                )

                res, _ = vdms_utils.run_vdms_query([query])
                if res and "FailedCommand" in res[0]:
                    raise ValueError(
                        f"Failed to update VDMS index for collection {settings.DB_COLLECTION}."
                    )

                logger.info(f"VDMS client '{client_key}' index updated successfully.")
            except Exception as exc:  # pragma: no cover - best effort logging
                logger.error(f"Error updating index for VDMS client '{client_key}': {exc}")

        logger.info("Tearing down VDMS-Dataprep Service . . .")


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

# Video management endpoints
app.include_router(list_videos_router)
app.include_router(download_video_router)
app.include_router(delete_video_router)

