# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from video_analyzer.api.router import api_router, available_routes
from video_analyzer.core.settings import settings
from video_analyzer.utils.logger import logger


app = FastAPI(
    title=f"{settings.APP_NAME} API",
    version=settings.API_VER,
    description=settings.API_DESCRIPTION,
    openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
    debug=settings.DEBUG
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

    # List available routes 
    available_routes()
    
    uvicorn.run(
        "video_analyzer.main:app",
        host="127.0.0.1",
        port=8000,
        reload=settings.DEBUG,
        log_level="debug" if settings.DEBUG else "info",
        timeout_keep_alive=180,  # Increase keep-alive timeout to 3 minutes (180 seconds)
    )
