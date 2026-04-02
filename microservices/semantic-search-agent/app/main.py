"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app

from app.api.routes import router
from app.core.config import settings
from app.core.logger import setup_logging
from app.services.vlm.factory import VLMBackendFactory

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """Application lifespan manager."""
    setup_logging(settings.log_level)
    logger.info(f"Starting {settings.service_name} v{settings.service_version}")
    
    # Initialize VLM backend only if matching strategy requires it
    if settings.default_matching_strategy in ("semantic", "hybrid"):
        try:
            vlm_backend = VLMBackendFactory.create(settings.vlm_backend)
            if vlm_backend.is_available():
                logger.info(f"VLM backend '{settings.vlm_backend}' initialized successfully")
            else:
                logger.warning(f"VLM backend '{settings.vlm_backend}' is not available")
        except Exception as e:
            logger.error(f"Failed to initialize VLM backend: {e}")
    else:
        logger.info(f"Using '{settings.default_matching_strategy}' matching strategy - VLM backend not required")
    
    yield
    
    logger.info("Shutting down service")


app = FastAPI(
    title=settings.service_name,
    version=settings.service_version,
    description="AI-powered semantic comparison service for item matching and validation",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(router, prefix="/api/v1")

# Prometheus metrics endpoint
if settings.prometheus_enabled:
    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": settings.service_name,
        "version": settings.service_version,
        "status": "running",
    }


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.api_port,
        log_level=settings.log_level.lower(),
        reload=False,
    )
