# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from video_analyzer.api.router import api_router
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


@app.on_event("startup")
def _load_prompt_registry() -> None:
    """Load runtime-registered video summary task prompts from the cache dir."""
    try:
        from video_analyzer.prompts.prompt_registry import get_registry
        get_registry()  # lazy singleton triggers load()
    except Exception as e:
        logger.warning("Prompt registry failed to load at startup: %s", e)


@app.on_event("startup")
def _log_available_routes() -> None:
    """Dump every mounted HTTP route so users can tell at startup what the
    service exposes. Paths here already carry the API_V1_PREFIX."""
    logger.info("Available routes are:")
    for route in app.routes:
        methods = getattr(route, "methods", None)
        path = getattr(route, "path", None)
        if not methods or not path:
            continue
        logger.info("Route: %s, Methods: %s", path, ", ".join(sorted(methods)))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "video_analyzer.main:app",
        host="127.0.0.1",
        port=8000,
        reload=settings.DEBUG,
        log_level="debug" if settings.DEBUG else "info",
        timeout_keep_alive=180,                             # Increase keep-alive timeout to 3 minutes (180 seconds)
        timeout=settings.REQUEST_TIMEOUT,
        limit_max_requests=settings.MAX_CONCURRENT_REQUESTS,
    )
