# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import ipaddress
import logging
import re
import subprocess
import threading
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from slugify import slugify

from src.core.internal_types import (
    InternalCamera,
    InternalCameraType,
    InternalGigECameraDetails,
    InternalGigECapture,
)

logger = logging.getLogger("gige")

GIGE_CAMERA_ID_PREFIX = "gige-camera-"
ARV_TOOL = "arv-tool-0.8"

_LIST_TIMEOUT_S = 10
_CONTROL_TIMEOUT_S = 10

_DEVICE_LINE_RE = re.compile(r"^(?P<id>.+?)\s+\((?P<address>[^()]+)\)$")
# Device ids come from the network; no leading dash so they can never be parsed as options.
# Length is capped so that the derived sensor id fits SENSOR_ID_MAX_LENGTH (256).
_ARAVIS_ID_RE = re.compile(r"^[A-Za-z0-9._][A-Za-z0-9._ \-]{0,243}$")
_FEATURE_LINE_RE = re.compile(r"^(?P<name>\w+)\s*=\s*(?P<value>.*)$")
_NUMBER_RE = re.compile(r"^-?\d+(?:\.\d+)?")

_FEATURES = (
    "DeviceVendorName",
    "DeviceModelName",
    "DeviceSerialNumber",
    # Pre-SFNC 2.0 cameras expose the serial number as DeviceID.
    "DeviceID",
    "PixelFormat",
    "Width",
    "Height",
    "AcquisitionFrameRate",
)


@dataclass
class _GigEDeviceInfo:
    vendor: str
    model: Optional[str]
    serial: str
    capture: Optional[InternalGigECapture]


def _slug(text: str) -> str:
    return slugify(text, regex_pattern=r"[^-a-z0-9_\.]+")


def make_gige_camera_id(aravis_id: str) -> str:
    # The Aravis id comes from the discovery reply, so it stays the same whether or not
    # the camera can be opened; the id must not depend on the feature read.
    return f"{GIGE_CAMERA_ID_PREFIX}{_slug(aravis_id)}"


def _parse_number(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    m = _NUMBER_RE.match(value)
    return float(m.group(0)) if m else None


def parse_device_list(output: str) -> List[Tuple[str, str]]:
    """Parse the `arv-tool-0.8` device list into (aravis_id, ipv4); non-GigE devices are skipped."""
    devices = []
    for line in output.splitlines():
        m = _DEVICE_LINE_RE.match(line.strip())
        if not m:
            continue
        aravis_id, address = m.group("id"), m.group("address").strip()
        try:
            ip = str(ipaddress.IPv4Address(address))
        except ValueError:
            logger.debug(f"Skipping non-GigE device {aravis_id!r} ({address!r})")
            continue
        if not _ARAVIS_ID_RE.match(aravis_id):
            logger.warning(f"Skipping GigE device with unsupported id at {ip}")
            continue
        devices.append((aravis_id, ip))
    return devices


def parse_features(output: str) -> Dict[str, str]:
    """Parse `arv-tool-0.8 control` output lines of the form `Name = value`."""
    features = {}
    for line in output.splitlines():
        m = _FEATURE_LINE_RE.match(line.strip())
        if m and m.group("name") in _FEATURES:
            features[m.group("name")] = m.group("value").strip()
    return features


def _to_device_info(features: Dict[str, str]) -> Optional[_GigEDeviceInfo]:
    vendor = features.get("DeviceVendorName")
    serial = features.get("DeviceSerialNumber") or features.get("DeviceID")
    if not vendor or not serial:
        return None

    width = _parse_number(features.get("Width"))
    height = _parse_number(features.get("Height"))
    capture = None
    if width is not None and height is not None:
        pixel_format = features.get("PixelFormat")
        capture = InternalGigECapture(
            pixel_format=pixel_format.split()[0] if pixel_format else None,
            width=int(width),
            height=int(height),
            fps=_parse_number(features.get("AcquisitionFrameRate")),
        )

    return _GigEDeviceInfo(
        vendor=vendor,
        model=features.get("DeviceModelName") or None,
        serial=serial,
        capture=capture,
    )


def _make_gige_camera(aravis_id: str, ip: str, info: Optional[_GigEDeviceInfo]) -> InternalCamera:
    device_id = make_gige_camera_id(aravis_id)
    if info is None:
        # Details are unknown until the camera can be opened (e.g. it is streaming elsewhere).
        return InternalCamera(
            device_id=device_id,
            device_name=f"GigE Camera {ip}",
            device_type=InternalCameraType.GIGE,
            details=InternalGigECameraDetails(ip=ip),
        )

    name = " ".join(part for part in (info.vendor, info.model) if part)
    return InternalCamera(
        device_id=device_id,
        device_name=name,
        device_type=InternalCameraType.GIGE,
        details=InternalGigECameraDetails(
            ip=ip,
            vendor=info.vendor,
            model=info.model,
            serial=info.serial,
            current_capture=info.capture,
        ),
    )


class GigECameraDiscovery:
    """Periodically discovers GigE Vision cameras with Aravis `arv-tool-0.8` in the background."""

    def __init__(self, interval_s: float = 20.0) -> None:
        self._interval_s = interval_s
        self._devices: List[Tuple[str, str]] = []
        # Read once per device: opening a camera takes its control channel for a moment.
        self._info_cache: Dict[str, _GigEDeviceInfo] = {}
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="gige-discovery", daemon=True)
        self._thread.start()
        logger.info(f"GigE discovery started (interval {self._interval_s}s)")

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=_LIST_TIMEOUT_S + _CONTROL_TIMEOUT_S)
            self._thread = None

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self.scan_once()
            self._stop_event.wait(self._interval_s)

    def _read_device_info(self, aravis_id: str) -> Optional[_GigEDeviceInfo]:
        try:
            result = subprocess.run(
                [ARV_TOOL, f"--name={aravis_id}", "control", *_FEATURES],
                capture_output=True,
                text=True,
                timeout=_CONTROL_TIMEOUT_S,
            )
        except subprocess.TimeoutExpired:
            logger.warning(f"Timeout reading features of GigE camera {aravis_id!r}")
            return None
        except Exception as e:
            logger.warning(f"Error reading features of GigE camera {aravis_id!r}: {e}")
            return None

        info = _to_device_info(parse_features(result.stdout or ""))
        if info is None:
            logger.warning(f"Could not read identity of GigE camera {aravis_id!r}")
        return info

    def scan_once(self) -> None:
        """Run one discovery sweep; the previous result is kept if the sweep fails."""
        try:
            result = subprocess.run(
                [ARV_TOOL],
                capture_output=True,
                text=True,
                timeout=_LIST_TIMEOUT_S,
            )
        except Exception as e:
            logger.error(f"GigE discovery sweep failed: {e}")
            return

        devices = parse_device_list(result.stdout or "")
        with self._lock:
            missing = [d for d, _ in devices if d not in self._info_cache]

        new_info = {}
        for aravis_id in missing:
            info = self._read_device_info(aravis_id)
            if info is not None:
                new_info[aravis_id] = info

        with self._lock:
            self._info_cache.update(new_info)
            present = {d for d, _ in devices}
            self._info_cache = {k: v for k, v in self._info_cache.items() if k in present}
            self._devices = devices
        logger.debug(f"GigE discovery found {len(devices)} camera(s)")

    def discover_cameras(self) -> List[InternalCamera]:
        """Return cameras from the latest sweep."""
        with self._lock:
            return [
                _make_gige_camera(aravis_id, ip, self._info_cache.get(aravis_id))
                for aravis_id, ip in self._devices
            ]
