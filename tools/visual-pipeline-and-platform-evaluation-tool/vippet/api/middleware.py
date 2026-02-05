"""
Middleware for controlling API access based on application state.
"""

import logging

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from managers.app_state_manager import AppStateManager

logger = logging.getLogger("api.middleware")

# Paths that are always accessible, even during initialization
ALWAYS_ACCESSIBLE_PATHS = {
    "/health",
    "/status",
    "/docs",
    "/openapi.json",
    "/redoc",
}


class InitializationMiddleware(BaseHTTPMiddleware):
    """
    Middleware that blocks API requests while application is initializing.

    Health and status endpoints are always accessible.
    All other endpoints return 503 Service Unavailable during initialization.
    """

    async def dispatch(self, request: Request, call_next):
        # Extract path without the root_path prefix for comparison
        path = request.url.path

        # Remove /api/v1 prefix if present for path matching
        clean_path = path
        if path.startswith("/api/v1"):
            clean_path = path[7:]  # Remove "/api/v1"

        # Allow health and status endpoints always
        if clean_path in ALWAYS_ACCESSIBLE_PATHS:
            return await call_next(request)

        # Check if application is ready
        app_state_manager = AppStateManager()
        if not app_state_manager.is_ready():
            logger.debug(f"Blocking request to {path} - application not ready")
            return JSONResponse(
                status_code=503,
                content={
                    "message": f"Service is {app_state_manager.status.value}. Please wait.",
                    "status": app_state_manager.status.value,
                },
            )

        return await call_next(request)
