# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import logging
import threading
from typing import List, Optional

from src.core.internal_types import InternalCamera
from src.core.onvif import NETWORK_CAMERA_ID_PREFIX, ONVIFCameraDiscovery
from src.core.usb import USBCameraDiscovery

logger = logging.getLogger("camera_manager")


class CameraNotFoundError(LookupError):
    """The requested camera is not known to the service."""


class CameraManager:
    """Keeps the list of discovered USB and ONVIF cameras, including loaded ONVIF profiles."""

    def __init__(
        self,
        usb_discovery: USBCameraDiscovery,
        onvif_discovery: ONVIFCameraDiscovery,
    ) -> None:
        self.usb_discovery = usb_discovery
        self.onvif_discovery = onvif_discovery
        self._usb_cameras: List[InternalCamera] = []
        self._network_cameras: List[InternalCamera] = []
        self._lock = threading.Lock()

    @staticmethod
    def _update_camera_cache(
        cached_cameras: List[InternalCamera],
        discovered_cameras: List[InternalCamera],
    ) -> List[InternalCamera]:
        """Drop cameras that disappeared, add new ones and keep cached entries (with profiles)."""
        discovered = {cam.device_id: cam for cam in discovered_cameras}

        updated = []
        for cached in cached_cameras:
            if cached.device_id in discovered:
                updated.append(cached)
                del discovered[cached.device_id]
            else:
                logger.debug(f"Camera {cached.device_id} is no longer available")

        for new_cam in discovered.values():
            logger.debug(f"New camera discovered: {new_cam.device_id}")
            updated.append(new_cam)

        return updated

    def discover_usb_cameras(self) -> List[InternalCamera]:
        try:
            discovered = self.usb_discovery.discover_cameras()
            with self._lock:
                self._usb_cameras = self._update_camera_cache(self._usb_cameras, discovered)
        except Exception as e:
            logger.error(f"Failed USB camera discovery: {e}", exc_info=True)

        with self._lock:
            return self._usb_cameras.copy()

    def discover_network_cameras(self) -> List[InternalCamera]:
        try:
            discovered = self.onvif_discovery.discover_cameras()
            with self._lock:
                self._network_cameras = self._update_camera_cache(self._network_cameras, discovered)
        except Exception as e:
            logger.error(f"Failed network camera discovery: {e}", exc_info=True)

        with self._lock:
            return self._network_cameras.copy()

    def discover_all_cameras(self) -> List[InternalCamera]:
        usb_cameras = self.discover_usb_cameras()
        network_cameras = self.discover_network_cameras()
        logger.debug(
            f"Discovered {len(usb_cameras)} USB and {len(network_cameras)} network camera(s)"
        )
        return usb_cameras + network_cameras

    def _find_cached(self, camera_id: str) -> Optional[InternalCamera]:
        with self._lock:
            for camera in self._usb_cameras + self._network_cameras:
                if camera.device_id == camera_id:
                    return camera
        return None

    def get_camera_by_id(self, camera_id: str) -> Optional[InternalCamera]:
        """Return a camera from the cache, refreshing discovery once on a cache miss."""
        camera = self._find_cached(camera_id)
        if camera is None:
            self.discover_all_cameras()
            camera = self._find_cached(camera_id)
        return camera

    def load_camera_profiles(self, camera_id: str, username: str, password: str) -> InternalCamera:
        """Load ONVIF profiles for a discovered network camera and store them in the cache.

        Raises:
            ValueError: camera_id is not a network camera id.
            CameraNotFoundError: the camera is not currently discovered.
            CameraAuthError, CameraUnreachableError, RuntimeError: see ONVIFCameraDiscovery.
        """
        if not camera_id.startswith(NETWORK_CAMERA_ID_PREFIX):
            raise ValueError("Invalid camera type - only network cameras supported")

        if not any(c.device_id == camera_id for c in self.discover_network_cameras()):
            raise CameraNotFoundError(f"Camera with ID '{camera_id}' not found")

        camera = self.onvif_discovery.load_camera_profiles(camera_id, username, password)

        with self._lock:
            for i, cached in enumerate(self._network_cameras):
                if cached.device_id == camera_id:
                    self._network_cameras[i] = camera
                    break

        return camera
