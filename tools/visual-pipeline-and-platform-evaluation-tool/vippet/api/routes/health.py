"""
Health and status endpoints for application monitoring.

These endpoints are used by Docker healthcheck and UI to monitor
application initialization state.
"""

import logging

from fastapi import APIRouter

from api.api_schemas import AppStatus, HealthResponse, StatusResponse
from internal_types import InternalAppStatus
from managers.app_state_manager import AppStateManager

router = APIRouter()
logger = logging.getLogger("api.routes.health")


@router.get(
    "/health",
    operation_id="get_health",
    summary="Health Check",
    response_model=HealthResponse,
)
def get_health() -> HealthResponse:
    """
    **Health check endpoint for Docker healthcheck.**

    ## Operation
    Returns `healthy=true` as long as the application is not in shutdown state.
    This allows the container to remain healthy during initialization.

    ## Parameters
    - **Path/Query parameters:** None

    ## Response Format

    ### 200 OK
    **HealthResponse** with:
    - `healthy` - `true` if application is healthy (not shutdown)

    ## Conditions

    ### ✅ Success
    - Application is running (not in shutdown state)

    ## Example Response

    ```json
    {
      "healthy": true
    }
    ```
    """
    app_state_manager = AppStateManager()
    return HealthResponse(healthy=app_state_manager.is_healthy())


@router.get(
    "/status",
    operation_id="get_status",
    summary="Application Status",
    response_model=StatusResponse,
)
def get_status() -> StatusResponse:
    """
    **Detailed status endpoint for monitoring initialization progress.**

    ## Operation
    Returns the current application status, including initialization state,
    progress messages, and readiness for serving API requests.

    ## Parameters
    - **Path/Query parameters:** None

    ## Response Format

    ### 200 OK
    **StatusResponse** with:
    - `status` - Current application status (`starting`, `initializing`, `ready`, `shutdown`)
    - `message` - Optional message describing current activity
    - `ready` - `true` if application is ready to serve API requests

    ## Conditions

    ### ✅ Success
    - Application is running and status can be retrieved

    ## Examples

    ### Response (During Initialization)
    ```json
    {
      "status": "initializing",
      "message": "Loading video metadata...",
      "ready": false
    }
    ```

    ### Response (When Ready)
    ```json
    {
      "status": "ready",
      "message": null,
      "ready": true
    }
    ```
    """
    app_state_manager = AppStateManager()
    return StatusResponse(
        status=_internal_app_status_to_api(app_state_manager.status),
        message=app_state_manager.message,
        ready=app_state_manager.is_ready(),
    )


# ------------------------------------------------------------------
# Conversion helpers: internal types -> API types
# ------------------------------------------------------------------


def _internal_app_status_to_api(status: InternalAppStatus) -> AppStatus:
    """
    Convert InternalAppStatus to API AppStatus.

    Args:
        status: Internal application status.

    Returns:
        AppStatus ready for API response.
    """
    return AppStatus(status.value)
