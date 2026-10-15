# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
CameraManager: client of the sensor-manager microservice.

Camera discovery (USB and ONVIF) and ONVIF profile loading are performed by
sensor-manager. This manager caches the last known camera list for lookups
done while building pipelines, and keeps ONVIF credentials supplied by the
user in memory only, so they can be injected into ``rtspsrc`` elements.
"""

import logging
import os
import threading
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

import httpx

from internal_types import (
    InternalCamera,
    InternalCameraProfileInfo,
    InternalCameraType,
    InternalNetworkCameraDetails,
    InternalUSBCameraDetails,
    InternalV4L2BestCapture,
)

logger = logging.getLogger("camera_manager")

SENSOR_MANAGER_URL: str = os.environ.get(
    "SENSOR_MANAGER_URL", "http://host.docker.internal:8090"
).rstrip("/")
SENSOR_MANAGER_API_PREFIX: str = "/api/v1"
SENSOR_MANAGER_TIMEOUT_S: float = float(
    os.environ.get("SENSOR_MANAGER_TIMEOUT_S", "30")
)


class CameraServiceError(Exception):
    """Error reported by (or while contacting) the sensor-manager service."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _profile_from_api(data: Dict[str, Any]) -> InternalCameraProfileInfo:
    return InternalCameraProfileInfo(
        name=data["name"],
        rtsp_url=data.get("rtsp_url"),
        resolution=data.get("resolution"),
        encoding=data.get("encoding"),
        framerate=data.get("framerate"),
        bitrate=data.get("bitrate"),
    )


def _camera_from_api(data: Dict[str, Any]) -> InternalCamera:
    device_type = InternalCameraType(data["device_type"])
    details = data["details"]
    if device_type == InternalCameraType.USB:
        best_capture = details.get("best_capture")
        camera_details: InternalUSBCameraDetails | InternalNetworkCameraDetails = (
            InternalUSBCameraDetails(
                device_path=details["device_path"],
                best_capture=InternalV4L2BestCapture(
                    fourcc=best_capture["fourcc"],
                    width=int(best_capture["width"]),
                    height=int(best_capture["height"]),
                    fps=float(best_capture["fps"]),
                )
                if best_capture
                else None,
            )
        )
    else:
        best_profile = details.get("best_profile")
        camera_details = InternalNetworkCameraDetails(
            ip=details["ip"],
            port=int(details["port"]),
            profiles=[_profile_from_api(p) for p in details.get("profiles") or []],
            best_profile=_profile_from_api(best_profile) if best_profile else None,
        )
    return InternalCamera(
        device_id=data["device_id"],
        device_name=data["device_name"],
        device_type=device_type,
        details=camera_details,
    )


def _error_detail(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return f"Camera service returned HTTP {response.status_code}"
    detail = body.get("detail") if isinstance(body, dict) else None
    if isinstance(detail, str):
        return detail
    if response.status_code == 422:
        return "Invalid camera request"
    message = body.get("message") if isinstance(body, dict) else None
    return message if isinstance(message, str) else "Camera service error"


class CameraManager:
    """
    Thread-safe singleton giving access to cameras discovered by sensor-manager.

    Lookups used by the pipeline graph (by device path / RTSP URL) are served
    from the cache populated by ``discover_all_cameras()`` and
    ``load_camera_profiles()``; they never contact sensor-manager.
    """

    _instance: Optional["CameraManager"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "CameraManager":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if hasattr(self, "_initialized"):
            return
        self._initialized = True

        self._cameras: List[InternalCamera] = []
        # camera_id -> (username, password); kept in memory only.
        self._credentials: Dict[str, Tuple[str, str]] = {}
        self._cache_lock = threading.Lock()
        # Overridable in tests with httpx.MockTransport.
        self._transport: Optional[httpx.BaseTransport] = None

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        with httpx.Client(
            base_url=f"{SENSOR_MANAGER_URL}{SENSOR_MANAGER_API_PREFIX}",
            timeout=SENSOR_MANAGER_TIMEOUT_S,
            transport=self._transport,
        ) as client:
            return client.request(method, path, **kwargs)

    def _apply_credentials(self, camera: InternalCamera) -> InternalCamera:
        if isinstance(camera.details, InternalNetworkCameraDetails):
            credentials = self._credentials.get(camera.device_id)
            if credentials is not None:
                camera.details.username, camera.details.password = credentials
        return camera

    def discover_all_cameras(self) -> List[InternalCamera]:
        """Fetch all cameras from sensor-manager and refresh the cache.

        On communication errors the last cached list is returned.
        """
        try:
            response = self._request("GET", "/sensors")
            response.raise_for_status()
            cameras = [_camera_from_api(item) for item in response.json()]
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as e:
            logger.error(f"Failed to get cameras from sensor-manager: {e}")
            with self._cache_lock:
                return list(self._cameras)

        with self._cache_lock:
            present = {camera.device_id for camera in cameras}
            self._credentials = {
                camera_id: creds
                for camera_id, creds in self._credentials.items()
                if camera_id in present
            }
            self._cameras = [self._apply_credentials(camera) for camera in cameras]
            logger.debug(f"Discovered {len(self._cameras)} camera(s)")
            return list(self._cameras)

    def get_camera_by_id(self, camera_id: str) -> Optional[InternalCamera]:
        """Get a camera from the cache (no discovery is triggered)."""
        with self._cache_lock:
            for camera in self._cameras:
                if camera.device_id == camera_id:
                    return camera
        return None

    def get_usb_camera_details_by_device_path(
        self, device_path: str
    ) -> Optional[InternalUSBCameraDetails]:
        """Get cached USB camera details for a device path (e.g. ``/dev/video0``)."""
        if not device_path:
            return None
        with self._cache_lock:
            for camera in self._cameras:
                if (
                    isinstance(camera.details, InternalUSBCameraDetails)
                    and camera.details.device_path == device_path
                ):
                    return camera.details
        logger.debug(f"No USB camera found for device path {device_path}")
        return None

    def get_network_camera_details_by_rtsp_url(
        self, rtsp_url: str
    ) -> Optional[InternalNetworkCameraDetails]:
        """Get cached network camera details (with credentials) owning a profile with this RTSP URL."""
        if not rtsp_url:
            return None
        normalized = rtsp_url.strip()
        with self._cache_lock:
            for camera in self._cameras:
                if not isinstance(camera.details, InternalNetworkCameraDetails):
                    continue
                if any(p.rtsp_url == normalized for p in camera.details.profiles):
                    return camera.details
        logger.debug(f"No network camera found for RTSP URL {rtsp_url}")
        return None

    def get_encoding_for_rtsp_url(self, rtsp_url: str) -> Optional[str]:
        """Get the encoding of the cached ONVIF profile with this RTSP URL."""
        if not rtsp_url:
            return None
        normalized = rtsp_url.strip()
        with self._cache_lock:
            for camera in self._cameras:
                if not isinstance(camera.details, InternalNetworkCameraDetails):
                    continue
                for profile in camera.details.profiles:
                    if profile.rtsp_url == normalized:
                        return profile.encoding
        return None

    def load_camera_profiles(
        self, camera_id: str, username: str, password: str
    ) -> InternalCamera:
        """Load ONVIF profiles through sensor-manager and remember the credentials.

        Raises:
            CameraServiceError: sensor-manager rejected the request or is unreachable.
        """
        try:
            response = self._request(
                "POST",
                f"/sensors/{quote(camera_id, safe='')}/profiles",
                json={"username": username, "password": password},
            )
        except httpx.HTTPError as e:
            logger.error(f"Failed to contact sensor-manager: {e}")
            raise CameraServiceError(500, "Camera service unavailable") from None

        if response.status_code != 200:
            raise CameraServiceError(response.status_code, _error_detail(response))

        try:
            camera = _camera_from_api(response.json()["camera"])
        except (KeyError, TypeError, ValueError) as e:
            logger.error(f"Invalid response from sensor-manager: {e}")
            raise CameraServiceError(
                500, "Invalid response from camera service"
            ) from None

        with self._cache_lock:
            self._credentials[camera_id] = (username, password)
            self._apply_credentials(camera)
            for i, cached in enumerate(self._cameras):
                if cached.device_id == camera_id:
                    self._cameras[i] = camera
                    break
            else:
                self._cameras.append(camera)

        logger.debug(f"Loaded profiles for camera {camera_id}")
        return camera
