# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pathlib
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from audio_analyzer.api.router import api_router
from audio_analyzer.core.settings import settings
from audio_analyzer.utils.model_manager import ModelManager
from audio_analyzer.utils.logger import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for FastAPI application.
    Handles startup and shutdown events.
    """
    # Create necessary directories
    logger.debug("Creating required directories")
    for dir in [
        settings.OUTPUT_DIR,
        settings.UPLOAD_DIR,
        settings.AUDIO_DIR,
        settings.GGML_MODEL_DIR,
        settings.OPENVINO_MODEL_DIR,
    ]:
        pathlib.Path(dir).mkdir(parents=True, exist_ok=True)
        logger.debug(f"Created directory: {dir}")

    # Download required models before the application starts
    logger.info("Starting model download for enabled models")
    await ModelManager.download_models()
    logger.info("Models download completed")
    
    yield
    logger.info("Application shutdown")


app = FastAPI(
    title=f"{settings.APP_NAME} API",
    version=settings.API_VER,
    description=settings.API_DESCRIPTION,
    openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
    debug=settings.DEBUG,
    lifespan=lifespan,  # Use the lifespan context manager
    root_path="/audio"
)

# Set up CORS middleware
if settings.BACKEND_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin) for origin in settings.BACKEND_CORS_ORIGINS],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Include the API router containing all endpoints
app.include_router(api_router, prefix=settings.API_V1_PREFIX)


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "audio_analyzer.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level="debug" if settings.DEBUG else "info",
        timeout_keep_alive=180,  # Increase keep-alive timeout to 3 minutes (180 seconds)
    )