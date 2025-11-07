# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from fastapi import APIRouter

from video_analyzer.api.endpoints import health, models, summarization
from video_analyzer.utils.logger import logger

api_router = APIRouter()

# Include routers for each endpoints in the API
api_router.include_router(health.router)
api_router.include_router(summarization.router)
api_router.include_router(models.router)

def available_routes():
    logger.info("Available routes are:")
    for route in api_router.routes:
        methods = getattr(route, "methods", None)
        path = getattr(route, "path", None)

        if methods is None or path is None:
            continue

        logger.info("Route: %s, Methods: %s", path, ', '.join(methods))
