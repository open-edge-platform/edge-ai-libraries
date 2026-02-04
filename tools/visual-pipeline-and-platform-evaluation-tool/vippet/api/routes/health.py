"""
Health and status endpoints for application monitoring.

These endpoints are used by Docker healthcheck and UI to monitor
application initialization state.
"""

import logging
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from api.api_schemas import AppStatus
from managers.app_state_manager import AppStateManager

router = APIRouter()
logger = logging.getLogger("api.routes.health")


class HealthResponse(BaseModel):
    """
    Response model for health endpoint.

    Attributes:
        healthy: True if application is healthy (not shutdown).
    """

    healthy: bool


class StatusResponse(BaseModel):
    """
    Response model for status endpoint.

    Attributes:
        status: Current application status.
        message: Optional message describing current activity.
        ready: True if application is ready to serve API requests.
    """

    status: AppStatus
    message: Optional[str]
    ready: bool


@router.get("/health", operation_id="get_health", response_model=HealthResponse)
def get_health() -> HealthResponse:
    """
    Health check endpoint for Docker healthcheck.

    Returns healthy=true as long as the application is not in shutdown state.
    This allows the container to remain healthy during initialization.

    Returns:
        200 OK: Health status response.

    Example response:
        .. code-block:: json

            {
              "healthy": true
            }
    """
    app_state_manager = AppStateManager()
    return HealthResponse(healthy=app_state_manager.is_healthy())


@router.get("/status", operation_id="get_status", response_model=StatusResponse)
def get_status() -> StatusResponse:
    """
    Detailed status endpoint for monitoring initialization progress.

    Returns:
        200 OK: Detailed status response.

    Example response (during initialization):
        .. code-block:: json

            {
              "status": "initializing",
              "message": "Loading video metadata...",
              "ready": false
            }

    Example response (when ready):
        .. code-block:: json

            {
              "status": "ready",
              "message": null,
              "ready": true
            }
    """
    app_state_manager = AppStateManager()
    return StatusResponse(
        status=app_state_manager.status,
        message=app_state_manager.message,
        ready=app_state_manager.is_ready(),
    )
