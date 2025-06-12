# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.common import logger, settings
from src.common.schema import DataPrepResponse, StatusEnum
from src.endpoints import (
    check_health_router,
    delete_video_router,
    download_video_router,
    list_videos_router,
    prep_video_router_legacy,
    process_document_router,
    process_minio_video_router,
    upload_and_process_video_router,
)

# Dump loaded settings
logger.debug(f"Settings loaded: {settings.model_dump()}")

# Initialize FastAPI app
app = FastAPI(
    title=settings.APP_DISPLAY_NAME,
    description=settings.APP_DESC,
    root_path="/v1/dataprep",
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
app.include_router(prep_video_router_legacy)
app.include_router(process_minio_video_router)
app.include_router(upload_and_process_video_router)

# Video management endpoints
app.include_router(list_videos_router)
app.include_router(download_video_router)
app.include_router(delete_video_router)
