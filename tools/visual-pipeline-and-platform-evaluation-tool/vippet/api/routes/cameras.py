import logging
from typing import List

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

import api.api_schemas as schemas
from managers.camera_manager import get_camera_manager

router = APIRouter()
logger = logging.getLogger("api.routes.cameras")


@router.get(
    "",
    operation_id="get_cameras",
    response_model=List[schemas.Camera],
    summary="Get all cameras",
    responses={
        200: {
            "description": "List of all cameras successfully retrieved.",
            "model": List[schemas.Camera],
        },
        500: {
            "description": "Unexpected error when discovering cameras.",
            "model": schemas.MessageResponse,
        },
    },
)
def get_cameras():
    """
    Get all cameras (both USB and network) available to the system.

    This endpoint combines results from both USB and network camera discovery
    to provide a comprehensive list of all available camera devices.

    Operation:
        * Discover all USB cameras using v4l2-ctl or device scanning.
        * Discover all network cameras using various protocols.
        * Combine and return the complete list.

    Path / query parameters:
        None.

    Returns:
        200 OK:
            JSON array of Camera objects containing both USB and network cameras.
            If no cameras are found, an empty list is returned.
        500 Internal Server Error:
            MessageResponse with error description if discovery fails unexpectedly.

    Success conditions:
        * At least one discovery method succeeds.
        * Results can be combined and returned.

    Failure conditions:
        * Both USB and network discovery fail.
        * System error during discovery process.

    Successful response example (200):
        .. code-block:: json

            [
              {
                "device_path": "/dev/video0",
                "device_name": "Integrated Camera",
                "device_type": "USB",
                "device_id": "usb_camera_0",
                "url": null,
                "resolution": null,
                "status": "AVAILABLE"
              },
              {
                "device_path": null,
                "device_name": "Axis Camera M1065-L",
                "device_type": "NETWORK",
                "device_id": "network_camera_1",
                "url": "rtsp://192.168.1.100:554/axis-media/media.amp",
                "resolution": "1920x1080",
                "status": "AVAILABLE"
              }
            ]
    """
    try:
        camera_manager = get_camera_manager()
        cameras = camera_manager.discover_all_cameras()
        logger.info(f"Discovered total {len(cameras)} camera(s)")
        return cameras
    except Exception:
        logger.error("Failed to discover cameras", exc_info=True)
        return JSONResponse(
            content=schemas.MessageResponse(
                message="Unexpected error when discovering cameras"
            ).model_dump(),
            status_code=500,
        )


@router.post(
    "/profiles",
    operation_id="get_camera_profiles",
    response_model=schemas.CameraAuthResponse,
    summary="Get camera ONVIF profiles",
    responses={
        200: {
            "description": "Camera profiles retrieved successfully.",
            "model": schemas.CameraAuthResponse,
        },
        400: {
            "description": "Invalid camera ID format.",
            "model": schemas.MessageResponse,
        },
        401: {
            "description": "Failed to retrieve profiles - invalid credentials.",
            "model": schemas.MessageResponse,
        },
        404: {
            "description": "Camera not found.",
            "model": schemas.MessageResponse,
        },
        500: {
            "description": "Unexpected error when retrieving camera profiles.",
            "model": schemas.MessageResponse,
        },
    },
)
def get_camera_profiles(request: schemas.CameraAuthRequest):
    """
    Retrieve ONVIF profiles from a network camera.

    This endpoint connects to a specific ONVIF-compatible network camera using
    the provided credentials and retrieves all available media profiles from the camera.

    Operation:
        * Parse the camera_id to extract IP address and port
        * Establish ONVIF connection with provided credentials
        * Retrieve all available media profiles from the camera
        * Update the cached camera with profile information
        * Return success status

    Request body:
        JSON object with camera_id, username, and password.

    Returns:
        200 OK:
            CameraAuthResponse indicating success.
        400 Bad Request:
            Invalid camera_id format.
        401 Unauthorized:
            Failed to retrieve profiles - credentials rejected by camera.
        404 Not Found:
            Camera with specified ID not found or not reachable.
        500 Internal Server Error:
            Unexpected error during profile retrieval.

    Success conditions:
        * Camera is reachable on the network.
        * Credentials are valid.
        * Camera supports ONVIF protocol.

    Failure conditions:
        * Invalid camera_id format.
        * Camera is offline or unreachable.
        * Invalid credentials.
        * Camera does not support ONVIF.
        * Network connectivity issues.

    Successful response example (200):
        .. code-block:: json

            {
              "message": "Camera profiles retrieved successfully",
              "camera_id": "network_camera_192.168.1.100_80"
            }
    """
    try:
        camera_manager = get_camera_manager()
        camera_manager.get_camera_profiles(
            request.camera_id, request.username, request.password
        )

        logger.info(f"Successfully retrieved profiles for camera {request.camera_id}")
        return schemas.CameraAuthResponse(
            message="Camera profiles retrieved successfully",
            camera_id=request.camera_id,
        )

    except ValueError as e:
        logger.warning(f"Invalid camera_id: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except ConnectionError as e:
        logger.warning(f"Failed to connect to camera: {e}")
        raise HTTPException(status_code=404, detail=f"Camera not reachable: {str(e)}")
    except Exception as e:
        error_msg = str(e).lower()
        # Check if it's an authentication error
        if (
            "unauthorized" in error_msg
            or "authentication" in error_msg
            or "credentials" in error_msg
        ):
            logger.warning(
                f"Failed to retrieve profiles for camera {request.camera_id} - invalid credentials"
            )
            raise HTTPException(
                status_code=401,
                detail="Failed to retrieve profiles - invalid credentials",
            )

        logger.error(f"Failed to get camera profile: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")
