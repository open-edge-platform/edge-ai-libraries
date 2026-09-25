# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import logging
import threading
from typing import List, Optional, Tuple

from dlstreamer.onvif import discover_onvif_cameras, read_camera_profiles

from src.core.internal_types import (
    InternalCamera,
    InternalCameraProfileInfo,
    InternalCameraType,
    InternalNetworkCameraDetails,
)
from src.core.scoring import select_best_profile

logger = logging.getLogger("onvif")

NETWORK_CAMERA_ID_PREFIX = "network-camera-"

_AUTH_ERROR_MARKERS = (
    "not authorized",
    "notauthorized",
    "unauthorized",
    "authentication",
    "authority failure",
    "credentials",
)
_CONNECTION_ERROR_MARKERS = (
    "connectionerror",
    "connection refused",
    "connection reset",
    "connection aborted",
    "max retries exceeded",
    "timed out",
    "timeout",
    "unreachable",
    "name or service not known",
    "no route to host",
)


class CameraAuthError(Exception):
    """The camera rejected the supplied credentials."""


class CameraUnreachableError(ConnectionError):
    """The camera could not be contacted."""


def make_network_camera_id(hostname: str, port: int) -> str:
    return f"{NETWORK_CAMERA_ID_PREFIX}{hostname}-{port}"


def parse_network_camera_id(camera_id: str) -> Tuple[str, int]:
    """Split `network-camera-{hostname}-{port}` into (hostname, port); ValueError if malformed."""
    if not camera_id.startswith(NETWORK_CAMERA_ID_PREFIX):
        raise ValueError(f"Invalid camera_id format: {camera_id}")

    parts = camera_id[len(NETWORK_CAMERA_ID_PREFIX) :].rsplit("-", 1)
    if len(parts) != 2 or not parts[0]:
        raise ValueError(f"Invalid camera_id format: {camera_id}")

    try:
        port = int(parts[1])
    except ValueError:
        raise ValueError(f"Invalid port in camera_id: {camera_id}") from None
    if not 1 <= port <= 65535:
        raise ValueError(f"Invalid port in camera_id: {camera_id}")
    return parts[0], port


def _classify_error(error: str) -> Exception:
    lowered = error.lower()
    if any(marker in lowered for marker in _AUTH_ERROR_MARKERS):
        return CameraAuthError(error)
    if any(marker in lowered for marker in _CONNECTION_ERROR_MARKERS):
        return CameraUnreachableError(error)
    return RuntimeError(error)


def _to_profile_info(profile) -> InternalCameraProfileInfo:
    """Map a dlstreamer ONVIFProfile to the public profile info (credentials are dropped)."""
    resolution = None
    if profile.vec_resolution:
        width = profile.vec_resolution.get("width")
        height = profile.vec_resolution.get("height")
        if width and height:
            resolution = f"{width}x{height}"

    return InternalCameraProfileInfo(
        name=profile.name,
        rtsp_url=profile.rtsp_url,
        resolution=resolution,
        encoding=profile.vec_encoding,
        framerate=profile.vec_framerate_limit,
        bitrate=profile.vec_bitrate_limit,
    )


def _make_network_camera(
    hostname: str,
    port: int,
    profiles: Optional[List[InternalCameraProfileInfo]] = None,
) -> InternalCamera:
    profiles = profiles or []
    return InternalCamera(
        device_name=f"ONVIF Camera {hostname}",
        device_type=InternalCameraType.NETWORK,
        device_id=make_network_camera_id(hostname, port),
        details=InternalNetworkCameraDetails(
            ip=hostname,
            port=port,
            profiles=profiles,
            best_profile=select_best_profile(profiles) if profiles else None,
        ),
    )


class ONVIFCameraDiscovery:
    """Periodically runs WS-Discovery in a background thread and loads ONVIF media profiles."""

    def __init__(self, interval_s: float = 20.0) -> None:
        self._interval_s = interval_s
        self._endpoints: List[Tuple[str, int]] = []
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="onvif-discovery", daemon=True)
        self._thread.start()
        logger.info(f"ONVIF discovery started (interval {self._interval_s}s)")

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=10)
            self._thread = None

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self.scan_once()
            self._stop_event.wait(self._interval_s)

    def scan_once(self) -> None:
        """Run one WS-Discovery sweep; the previous result is kept if the sweep fails."""
        try:
            found = set()
            for camera in discover_onvif_cameras():
                hostname = camera.get("hostname")
                port = camera.get("port")
                if not hostname or not port:
                    logger.debug(f"Skipping invalid discovery entry: {camera}")
                    continue
                found.add((str(hostname), int(port)))
        except Exception as e:
            logger.error(f"ONVIF discovery sweep failed: {e}", exc_info=True)
            return

        with self._lock:
            self._endpoints = sorted(found)
        logger.debug(f"ONVIF discovery found {len(found)} camera(s)")

    def discover_cameras(self) -> List[InternalCamera]:
        """Return cameras from the latest sweep (without profiles)."""
        with self._lock:
            endpoints = list(self._endpoints)
        return [_make_network_camera(hostname, port) for hostname, port in endpoints]

    def load_camera_profiles(self, camera_id: str, username: str, password: str) -> InternalCamera:
        """Authenticate with a camera and return it with its media profiles and best profile.

        Raises:
            ValueError: malformed camera_id.
            CameraAuthError: credentials rejected.
            CameraUnreachableError: camera did not respond.
            RuntimeError: any other ONVIF failure.
        """
        hostname, port = parse_network_camera_id(camera_id)
        logger.debug(f"Loading ONVIF profiles from {hostname}:{port}")

        result = next(
            read_camera_profiles(
                [{"hostname": hostname, "port": port}],
                username=username,
                password=password,
            ),
            None,
        )
        if result is None:
            raise RuntimeError(f"No response from ONVIF profile reader for {hostname}:{port}")
        if not result.ok:
            logger.warning(f"Failed to load profiles from {hostname}:{port}: {result.error}")
            raise _classify_error(result.error or "")

        profile_infos = [_to_profile_info(p) for p in result.profiles]
        logger.debug(f"Loaded {len(profile_infos)} profile(s) from {hostname}:{port}")
        return _make_network_camera(hostname, port, profile_infos)
