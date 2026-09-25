# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import logging
from typing import Annotated, List

from fastapi import APIRouter, Depends, HTTPException, Path, Request
from fastapi.responses import JSONResponse

import src.api.schemas as schemas
from src.core.camera_manager import CameraManager, CameraNotFoundError
from src.core.internal_types import (
    InternalCamera,
    InternalCameraProfileInfo,
    InternalNetworkCameraDetails,
    InternalUSBCameraDetails,
)
from src.core.onvif import CameraAuthError, CameraUnreachableError

router = APIRouter()
logger = logging.getLogger("api.routes.sensors")

SensorId = Annotated[
    str,
    Path(
        max_length=schemas.SENSOR_ID_MAX_LENGTH,
        pattern=schemas.SENSOR_ID_PATTERN,
        description="Sensor identifier, e.g. `usb-camera-integrated-camera-0` or "
        "`network-camera-192.168.1.100-80`.",
    ),
]


def get_camera_manager(request: Request) -> CameraManager:
    return request.app.state.camera_manager


Manager = Annotated[CameraManager, Depends(get_camera_manager)]


@router.get(
    "",
    operation_id="get_sensors",
    response_model=List[schemas.Camera],
    summary="Get all sensors",
    responses={500: {"model": schemas.MessageResponse}},
)
def get_sensors(manager: Manager):
    """
    Return all USB cameras (enumerated live with `v4l2-ctl`) and ONVIF network cameras
    (from the latest WS-Discovery sweep). Previously loaded ONVIF profiles are preserved.
    """
    try:
        return [_internal_camera_to_api(cam) for cam in manager.discover_all_cameras()]
    except Exception:
        logger.error("Failed to discover sensors", exc_info=True)
        return JSONResponse(
            content=schemas.MessageResponse(
                message="Unexpected error when discovering sensors"
            ).model_dump(),
            status_code=500,
        )


@router.get(
    "/{sensor_id}",
    operation_id="get_sensor",
    response_model=schemas.Camera,
    summary="Get sensor by ID",
    responses={
        404: {"model": schemas.MessageResponse},
        500: {"model": schemas.MessageResponse},
    },
)
def get_sensor(sensor_id: SensorId, manager: Manager):
    """Return a single sensor by its identifier."""
    try:
        camera = manager.get_camera_by_id(sensor_id)
    except Exception:
        logger.error(f"Failed to retrieve sensor {sensor_id}", exc_info=True)
        return JSONResponse(
            content=schemas.MessageResponse(
                message="Unexpected error when retrieving sensor"
            ).model_dump(),
            status_code=500,
        )
    if camera is None:
        raise HTTPException(status_code=404, detail=f"Sensor with ID '{sensor_id}' not found")
    return _internal_camera_to_api(camera)


@router.post(
    "/{sensor_id}/profiles",
    operation_id="load_sensor_profiles",
    response_model=schemas.CameraAuthResponse,
    summary="Load ONVIF profiles of a network sensor",
    responses={
        400: {"model": schemas.MessageResponse, "description": "Invalid sensor ID."},
        401: {"model": schemas.MessageResponse, "description": "Invalid credentials."},
        404: {"model": schemas.MessageResponse, "description": "Not found or unreachable."},
        500: {"model": schemas.MessageResponse},
    },
)
def load_sensor_profiles(
    sensor_id: SensorId, request: schemas.CameraProfilesRequest, manager: Manager
):
    """
    Connect to an ONVIF network camera with the supplied credentials, read its media
    profiles and select the best one. Credentials are used only for this request and
    are never stored or returned by the service.
    """
    try:
        camera = manager.load_camera_profiles(
            sensor_id, request.username, request.password.get_secret_value()
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except CameraNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except CameraAuthError:
        raise HTTPException(
            status_code=401, detail="Failed to load profiles - invalid credentials"
        ) from None
    except CameraUnreachableError:
        raise HTTPException(status_code=404, detail="Camera not reachable") from None
    except Exception:
        logger.error(f"Failed to load profiles for sensor {sensor_id}", exc_info=True)
        raise HTTPException(
            status_code=500, detail="Unexpected error when loading camera profiles"
        ) from None

    return schemas.CameraAuthResponse(camera=_internal_camera_to_api(camera))


def _internal_profile_to_api(profile: InternalCameraProfileInfo) -> schemas.CameraProfileInfo:
    return schemas.CameraProfileInfo(
        name=profile.name,
        rtsp_url=profile.rtsp_url,
        resolution=profile.resolution,
        encoding=profile.encoding,
        framerate=profile.framerate,
        bitrate=profile.bitrate,
    )


def _internal_camera_to_api(camera: InternalCamera) -> schemas.Camera:
    if isinstance(camera.details, InternalUSBCameraDetails):
        best_capture = None
        if camera.details.best_capture is not None:
            best_capture = schemas.V4L2BestCapture(
                fourcc=camera.details.best_capture.fourcc,
                width=camera.details.best_capture.width,
                height=camera.details.best_capture.height,
                fps=camera.details.best_capture.fps,
            )
        details: schemas.USBCameraDetails | schemas.NetworkCameraDetails = schemas.USBCameraDetails(
            device_path=camera.details.device_path,
            best_capture=best_capture,
        )
    elif isinstance(camera.details, InternalNetworkCameraDetails):
        best_profile = None
        if camera.details.best_profile is not None:
            best_profile = _internal_profile_to_api(camera.details.best_profile)
        details = schemas.NetworkCameraDetails(
            ip=camera.details.ip,
            port=camera.details.port,
            profiles=[_internal_profile_to_api(p) for p in camera.details.profiles],
            best_profile=best_profile,
        )
    else:
        raise ValueError(f"Unknown camera details type: {type(camera.details)}")

    return schemas.Camera(
        device_id=camera.device_id,
        device_name=camera.device_name,
        device_type=schemas.CameraType(camera.device_type.value),
        details=details,
    )
