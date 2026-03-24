import logging
from typing import List

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

import api.api_schemas as schemas
from internal_types import (
    InternalCamera,
    InternalCameraProfileInfo,
    InternalNetworkCameraDetails,
    InternalUSBCameraDetails,
)
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
    **Get all cameras (both USB and network) available to the system.**

    ## Operation
    Combines results from both USB and network camera discovery to provide
    a comprehensive list of all available camera devices.

    1. Discover all USB cameras using v4l2-ctl or device scanning
    2. Discover all network cameras using various protocols
    3. Combine and return the complete list

    ## Parameters
    - **Path/Query parameters:** None

    ## Response Codes

    | Code | Description |
    |------|-------------|
    | 200 | JSON array of Camera objects (USB and network cameras) |
    | 500 | `MessageResponse` - Unexpected error during discovery |

    ## Conditions

    ### ✅ Success
    - At least one discovery method succeeds
    - Results can be combined and returned
    - Empty list is returned if no cameras are found

    ### ❌ Failure
    - Both USB and network discovery fail
    - System error during discovery process

    ## Example Response

    ```json
    [
      {
        "device_id": "usb-camera-0",
        "device_name": "Integrated Camera",
        "device_type": "USB",
        "details": {
          "device_path": "/dev/video0",
          "resolution": "1920x1080"
        }
      },
      {
        "device_id": "network-camera-192.168.1.100-80",
        "device_name": "ONVIF Camera 192.168.1.100",
        "device_type": "NETWORK",
        "details": {
          "ip": "192.168.1.100",
          "port": 80,
          "profiles": []
        }
      }
    ]
    ```
    """
    try:
        internal_cameras = CameraManager().discover_all_cameras()
        logger.debug(f"Discovered total {len(internal_cameras)} camera(s)")
        return [_internal_camera_to_api(cam) for cam in internal_cameras]
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
    **Get a specific camera by its ID.**

    ## Operation
    Retrieves information about a single camera device using its unique identifier.
    The camera must be already discovered and cached.

    1. Search for the camera in the cached cameras list
    2. Return camera details if found

    ## Path Parameters
    - `camera_id` - The unique identifier of the camera (e.g., `"usb-camera-0"` or `"network-camera-192.168.1.100-80"`)

    ## Response Codes

    | Code | Description |
    |------|-------------|
    | 200 | JSON object containing camera details |
    | 404 | `MessageResponse` - Camera with the given ID not found |
    | 500 | `MessageResponse` - Unexpected error during retrieval |

    ## Conditions

    ### ✅ Success
    - Camera with the given ID exists in the cache

    ### ❌ Failure
    - Camera with the given ID does not exist → 404
    - System error during retrieval → 500

    ## Example Response

    ```json
    {
      "device_id": "usb-camera-0",
      "device_name": "Integrated Camera",
      "device_type": "USB",
      "details": {
        "device_path": "/dev/video0",
        "resolution": "1920x1080"
      }
    }
    ```
    """
    try:
        internal_camera = CameraManager().get_camera_by_id(camera_id)
        if internal_camera is None:
            logger.debug(f"Camera {camera_id} not found")
            raise HTTPException(
                status_code=404, detail=f"Camera with ID '{camera_id}' not found"
            )
        logger.debug(f"Retrieved camera {camera_id}")
        return _internal_camera_to_api(internal_camera)
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
    **Load ONVIF profiles from a network camera.**

    ## Operation
    Connects to a specific ONVIF-compatible network camera using the provided
    credentials and loads all available media profiles from the camera.

    1. Parse the `camera_id` to extract IP address and port
    2. Establish ONVIF connection with provided credentials
    3. Load all available media profiles from the camera
    4. Update the cached camera with profile information
    5. Return updated camera object

    ## Path Parameters
    - `camera_id` - Unique identifier of the camera (e.g., `"network-camera-192.168.1.100-80"`)

    ## Request Body
    **`CameraProfilesRequest`** with:
    - `username` *(required)* - ONVIF camera username
    - `password` *(required)* - ONVIF camera password

    ## Response Codes

    | Code | Description |
    |------|-------------|
    | 200 | `CameraAuthResponse` with updated camera object containing profiles |
    | 400 | `MessageResponse` - Invalid camera_id format |
    | 401 | `MessageResponse` - Credentials rejected by camera |
    | 404 | `MessageResponse` - Camera not found or not reachable |
    | 500 | `MessageResponse` - Unexpected error during profile loading |

    ## Conditions

    ### ✅ Success
    - Camera is reachable on the network
    - Credentials are valid
    - Camera supports ONVIF protocol

    ### ❌ Failure
    - Invalid camera_id format → 400
    - Camera is offline or unreachable → 404
    - Invalid credentials → 401

    ## Example Response

    ```json
    {
      "camera": {
        "device_id": "network-camera-192.168.1.100-80",
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
    ```
    """
    try:
        internal_camera = CameraManager().load_camera_profiles(
            camera_id, request.username, request.password
        )

        logger.debug(f"Successfully loaded profiles for camera {camera_id}")
        return schemas.CameraAuthResponse(
            camera=_internal_camera_to_api(internal_camera)
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
                f"Failed to load profiles for camera {camera_id} - invalid credentials"
            )
            raise HTTPException(
                status_code=401,
                detail="Failed to load profiles - invalid credentials",
            )

        logger.error(f"Failed to load camera profiles: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


# ------------------------------------------------------------------
# Conversion helpers: internal types -> API types
#
# These functions convert internal types returned by CameraManager
# into API schema types for HTTP responses. CameraManager works
# exclusively with internal types; conversion to API types happens
# only here in the route layer.
# ------------------------------------------------------------------


def _internal_profile_to_api(
    profile: InternalCameraProfileInfo,
) -> schemas.CameraProfileInfo:
    """
    Convert InternalCameraProfileInfo to API CameraProfileInfo.

    Args:
        profile: Internal camera profile.

    Returns:
        CameraProfileInfo ready for API response.
    """
    return schemas.CameraProfileInfo(
        name=profile.name,
        rtsp_url=profile.rtsp_url,
        resolution=profile.resolution,
        encoding=profile.encoding,
        framerate=profile.framerate,
        bitrate=profile.bitrate,
    )


def _internal_camera_to_api(camera: InternalCamera) -> schemas.Camera:
    """
    Convert InternalCamera to API Camera.

    Converts internal camera details (USB or network) to the
    corresponding API detail type.

    Args:
        camera: Internal camera object.

    Returns:
        Camera ready for API response.
    """
    if isinstance(camera.details, InternalUSBCameraDetails):
        best_capture = None
        if camera.details.best_capture is not None:
            best_capture = schemas.V4L2BestCapture(
                fourcc=camera.details.best_capture.fourcc,
                width=camera.details.best_capture.width,
                height=camera.details.best_capture.height,
                fps=camera.details.best_capture.fps,
            )
        api_details: schemas.USBCameraDetails | schemas.NetworkCameraDetails = (
            schemas.USBCameraDetails(
                device_path=camera.details.device_path,
                best_capture=best_capture,
            )
        )
    elif isinstance(camera.details, InternalNetworkCameraDetails):
        api_profiles = [_internal_profile_to_api(p) for p in camera.details.profiles]
        best_profile = None
        if camera.details.best_profile is not None:
            best_profile = _internal_profile_to_api(camera.details.best_profile)
        api_details = schemas.NetworkCameraDetails(
            ip=camera.details.ip,
            port=camera.details.port,
            profiles=api_profiles,
            best_profile=best_profile,
        )
    else:
        raise ValueError(f"Unknown camera details type: {type(camera.details)}")

    return schemas.Camera(
        device_id=camera.device_id,
        device_name=camera.device_name,
        device_type=schemas.CameraType(camera.device_type.value),
        details=api_details,
    )
