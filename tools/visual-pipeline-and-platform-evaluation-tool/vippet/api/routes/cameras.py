import logging
from typing import List

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

import api.api_schemas as schemas
from managers.camera_manager import CameraManager

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
                "device_id": "usb_camera_0",
                "device_name": "Integrated Camera",
                "device_type": "USB",
                "details": {
                  "device_path": "/dev/video0",
                  "resolution": "1920x1080"
                }
              },
              {
                "device_id": "network_camera_192.168.1.100_80",
                "device_name": "ONVIF Camera 192.168.1.100",
                "device_type": "NETWORK",
                "details": {
                  "ip": "192.168.1.100",
                  "port": 80,
                  "profiles": []
                }
              }
            ]
    """
    try:
        cameras = CameraManager().discover_all_cameras()
        logger.debug(f"Discovered total {len(cameras)} camera(s)")
        return cameras
    except Exception:
        logger.error("Failed to discover cameras", exc_info=True)
        return JSONResponse(
            content=schemas.MessageResponse(
                message="Unexpected error when discovering cameras"
            ).model_dump(),
            status_code=500,
        )


@router.get(
    "/{camera_id}",
    operation_id="get_camera",
    response_model=schemas.Camera,
    summary="Get camera by ID",
    responses={
        200: {
            "description": "Camera successfully retrieved.",
            "model": schemas.Camera,
        },
        404: {
            "description": "Camera not found.",
            "model": schemas.MessageResponse,
        },
        500: {
            "description": "Unexpected error when retrieving camera.",
            "model": schemas.MessageResponse,
        },
    },
)
def get_camera(camera_id: str):
    """
    Get a specific camera by its ID.

    This endpoint retrieves information about a single camera device using its
    unique identifier. The camera must be already discovered and cached.

    Operation:
        * Search for the camera in the cached cameras list.
        * Return camera details if found.

    Path parameters:
        camera_id: The unique identifier of the camera (e.g., "usb_camera_0" or
                   "network_camera_192.168.1.100_80").

    Returns:
        200 OK:
            JSON object containing camera details.
        404 Not Found:
            MessageResponse if camera with the given ID is not found.
        500 Internal Server Error:
            MessageResponse with error description if retrieval fails unexpectedly.

    Success conditions:
        * Camera with the given ID exists in the cache.

    Failure conditions:
        * Camera with the given ID does not exist.
        * System error during retrieval.

    Successful response example (200):
        .. code-block:: json

            {
              "device_id": "usb_camera_0",
              "device_name": "Integrated Camera",
              "device_type": "USB",
              "details": {
                "device_path": "/dev/video0",
                "resolution": "1920x1080"
              }
            }
    """
    try:
        camera = CameraManager().get_camera_by_id(camera_id)
        if camera is None:
            logger.debug(f"Camera {camera_id} not found")
            raise HTTPException(
                status_code=404, detail=f"Camera with ID '{camera_id}' not found"
            )
        logger.debug(f"Retrieved camera {camera_id}")
        return camera
    except HTTPException:
        raise
    except Exception:
        logger.error(f"Failed to retrieve camera {camera_id}", exc_info=True)
        return JSONResponse(
            content=schemas.MessageResponse(
                message="Unexpected error when retrieving camera"
            ).model_dump(),
            status_code=500,
        )


@router.post(
    "/{camera_id}/profiles",
    operation_id="load_camera_profiles",
    response_model=schemas.CameraAuthResponse,
    summary="Load camera ONVIF profiles",
    responses={
        200: {
            "description": "Camera profiles loaded successfully.",
            "model": schemas.CameraAuthResponse,
        },
        400: {
            "description": "Invalid camera ID format.",
            "model": schemas.MessageResponse,
        },
        401: {
            "description": "Failed to load profiles - invalid credentials.",
            "model": schemas.MessageResponse,
        },
        404: {
            "description": "Camera not found.",
            "model": schemas.MessageResponse,
        },
        500: {
            "description": "Unexpected error when loading camera profiles.",
            "model": schemas.MessageResponse,
        },
    },
)
def load_camera_profiles(camera_id: str, request: schemas.CameraProfilesRequest):
    """
    Load ONVIF profiles from a network camera.

    This endpoint connects to a specific ONVIF-compatible network camera using
    the provided credentials and loads all available media profiles from the camera.

    Operation:
        * Parse the camera_id to extract IP address and port
        * Establish ONVIF connection with provided credentials
        * Load all available media profiles from the camera
        * Update the cached camera with profile information
        * Return updated camera object

    Path parameters:
        camera_id: The unique identifier of the camera (e.g., "network_camera_192.168.1.100_80").

    Request body:
        JSON object with username and password.

    Returns:
        200 OK:
            CameraAuthResponse with updated camera object containing profiles.
        400 Bad Request:
            Invalid camera_id format.
        401 Unauthorized:
            Failed to load profiles - credentials rejected by camera.
        404 Not Found:
            Camera with specified ID not found or not reachable.
        500 Internal Server Error:
            Unexpected error during profile loading.

    Success conditions:
        * Camera is reachable on the network.
        * Credentials are valid.
        * Camera supports ONVIF protocol.

    Failure conditions:
        * Invalid camera_id format.
        * Camera is offline or unreachable.
        * Invalid credentials.

    Successful response example (200):
        .. code-block:: json

            {
              "camera": {
                "device_id": "network_camera_192.168.1.100_80",
                "device_name": "ONVIF Camera 192.168.1.100",
                "device_type": "NETWORK",
                "details": {
                  "ip": "192.168.1.100",
                  "port": 80,
                  "profiles": [
                    {
                      "name": "Profile_1",
                      "rtsp_url": "rtsp://192.168.1.100:554/stream1",
                      "resolution": "1920x1080",
                      "encoding": "H264",
                      "framerate": 30,
                      "bitrate": 4096
                    },
                    {
                      "name": "Profile_2",
                      "rtsp_url": "rtsp://192.168.1.100:554/stream2",
                      "resolution": "1280x720",
                      "encoding": "H264",
                      "framerate": 15,
                      "bitrate": 2048
                    }
                  ]
                }
              }
            }
    """
    try:
        authenticated_camera = CameraManager().load_camera_profiles(
            camera_id, request.username, request.password
        )

        logger.debug(f"Successfully loaded profiles for camera {camera_id}")
        return schemas.CameraAuthResponse(camera=authenticated_camera)

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
                f"Failed to load profiles for camera {camera_id} - invalid credentials"
            )
            raise HTTPException(
                status_code=401,
                detail="Failed to load profiles - invalid credentials",
            )

        logger.error(f"Failed to load camera profiles: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")
