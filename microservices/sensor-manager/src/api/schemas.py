# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from enum import Enum
from typing import List, Optional, Union

from pydantic import BaseModel, Field, SecretStr

# Allowed characters of sensor ids produced by the service (slugs, hostnames, IPv4/IPv6, ports).
SENSOR_ID_PATTERN = r"^[A-Za-z0-9._:\-]+$"
SENSOR_ID_MAX_LENGTH = 256
CREDENTIAL_MAX_LENGTH = 256


class CameraType(str, Enum):
    """Type of camera device: `USB` (local V4L2 device) or `NETWORK` (ONVIF camera)."""

    USB = "USB"
    NETWORK = "NETWORK"


class MessageResponse(BaseModel):
    """Human-readable error or status message."""

    message: str


class HealthResponse(BaseModel):
    """Service health status."""

    healthy: bool


class V4L2BestCapture(BaseModel):
    """Best capture configuration selected from the V4L2 formats supported by a USB camera."""

    fourcc: str
    width: int
    height: int
    fps: float


class USBCameraDetails(BaseModel):
    """USB camera details: device path and the best capture configuration."""

    device_path: str
    best_capture: Optional[V4L2BestCapture] = None


class CameraProfileInfo(BaseModel):
    """ONVIF media profile of a network camera."""

    name: str
    rtsp_url: Optional[str] = None
    resolution: Optional[str] = None
    encoding: Optional[str] = None
    framerate: Optional[int] = None
    bitrate: Optional[int] = None


class NetworkCameraDetails(BaseModel):
    """Network camera details; `profiles` and `best_profile` are populated after authentication."""

    ip: str
    port: int
    profiles: List[CameraProfileInfo]
    best_profile: Optional[CameraProfileInfo] = None


class Camera(BaseModel):
    """
    Camera device information supporting both USB and network cameras.

    ### Example
    ```json
    {
      "device_id": "network-camera-192.168.1.100-80",
      "device_name": "ONVIF Camera 192.168.1.100",
      "device_type": "NETWORK",
      "details": {"ip": "192.168.1.100", "port": 80, "profiles": [], "best_profile": null}
    }
    ```
    """

    device_id: str
    device_name: str
    device_type: CameraType
    details: Union[USBCameraDetails, NetworkCameraDetails]


class CameraProfilesRequest(BaseModel):
    """ONVIF credentials used to read the media profiles of a network camera."""

    username: str = Field(..., max_length=CREDENTIAL_MAX_LENGTH)
    password: SecretStr = Field(..., max_length=CREDENTIAL_MAX_LENGTH)


class CameraAuthResponse(BaseModel):
    """Network camera with populated ONVIF profiles."""

    camera: Camera
