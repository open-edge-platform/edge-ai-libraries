# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for FastAPI application.
    Handles startup and shutdown events.
    """

    # Execute following during startup
    logger.info("Starting VDMS-Dataprep Service . . .")

    # Run the application
    yield

    # Execute following during shutdown
    if _client_cache:
        logger.info("Updating VDMS index before tearing down . . .")
        for client_key, client_wrapper in _client_cache.items():
            try:
                vdms_utils = VDMS_Utils(client_wrapper.client)
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
            except Exception as e:
                logger.error(f"Error updating index for VDMS client '{client_key}': {e}")

    logger.info("Tearing down VDMS-Dataprep Service . . .")


# Initialize FastAPI app
app = FastAPI(
    title=settings.APP_DISPLAY_NAME,
    description=settings.APP_DESC,
    root_path="/v1/dataprep",
    lifespan=lifespan,  # Handle startup, shutdown and lifespan of application
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
