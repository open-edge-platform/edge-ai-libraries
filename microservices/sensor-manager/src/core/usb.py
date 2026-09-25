# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import logging
import re
import subprocess
from typing import List, Optional

from slugify import slugify

from src.core.internal_types import (
    InternalCamera,
    InternalCameraType,
    InternalUSBCameraDetails,
    InternalV4L2Format,
    InternalV4L2FormatSize,
)
from src.core.scoring import select_best_from_v4l2_formats

logger = logging.getLogger("usb")

_FORMAT_RE = re.compile(r"\[\d+\]\s*:\s*'(\w+)'")
_SIZE_RE = re.compile(r"Size:\s*Discrete\s+(\d+)x(\d+)")
_FPS_RE = re.compile(r"\((\d+(?:\.\d+)?)\s*fps\)")


def _slugify_device_name(text: str) -> str:
    return slugify(text, regex_pattern=r"[^-a-z0-9_\.]+")


class USBCameraDiscovery:
    """Enumerates V4L2 capture devices with v4l2-ctl."""

    def _parse_v4l2_formats(self, device_path: str) -> List[InternalV4L2Format]:
        """Run `v4l2-ctl --list-formats-ext` for a device and parse its output."""
        try:
            result = subprocess.run(
                ["v4l2-ctl", "--device", device_path, "--list-formats-ext"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode != 0:
                logger.debug(f"v4l2-ctl --list-formats-ext failed for {device_path}")
                return []

            return self._parse_formats_ext_output(result.stdout)

        except Exception as e:
            logger.debug(f"Error parsing V4L2 formats for {device_path}: {e}")
            return []

    @staticmethod
    def _parse_formats_ext_output(output: str) -> List[InternalV4L2Format]:
        """Parse the raw text output of `v4l2-ctl --list-formats-ext`."""
        formats: List[InternalV4L2Format] = []
        current_format: Optional[InternalV4L2Format] = None
        current_size: Optional[InternalV4L2FormatSize] = None

        for line in output.split("\n"):
            stripped = line.strip()

            m = _FORMAT_RE.search(stripped)
            if m:
                current_format = InternalV4L2Format(fourcc=m.group(1), sizes=[])
                formats.append(current_format)
                current_size = None
                continue

            m = _SIZE_RE.search(stripped)
            if m and current_format is not None:
                current_size = InternalV4L2FormatSize(
                    width=int(m.group(1)), height=int(m.group(2)), fps_list=[]
                )
                current_format.sizes.append(current_size)
                continue

            m = _FPS_RE.search(stripped)
            if m and current_size is not None:
                current_size.fps_list.append(float(m.group(1)))

        return formats

    def _can_capture_video(self, device_path: str) -> bool:
        """Return True if "Video Capture" is listed in the device's "Device Caps" section."""
        try:
            result = subprocess.run(
                ["v4l2-ctl", "-d", device_path, "--all"],
                capture_output=True,
                text=True,
                timeout=3,
            )
        except FileNotFoundError:
            logger.error(f"v4l2-ctl not available, cannot verify {device_path} capabilities")
            return False
        except subprocess.TimeoutExpired:
            logger.warning(f"Timeout querying {device_path} capabilities")
            return False
        except Exception as e:
            logger.error(f"Error checking {device_path} capabilities: {e}", exc_info=True)
            return False

        if result.returncode != 0:
            logger.warning(f"Failed to query capabilities for {device_path}")
            return False

        in_device_caps_section = False
        for line in result.stdout.split("\n"):
            line_stripped = line.strip()
            if line_stripped.startswith("Device Caps"):
                in_device_caps_section = True
                if "Video Capture" in line:
                    return True
            elif in_device_caps_section:
                if line.startswith("\t") or line.startswith(" " * 4):
                    if "Video Capture" in line:
                        return True
                elif line_stripped and ":" in line_stripped:
                    break

        logger.debug(f"{device_path} does not support video capture in Device Caps")
        return False

    def discover_cameras(self) -> List[InternalCamera]:
        """Discover USB cameras and select the best capture configuration for each."""
        cameras: List[InternalCamera] = []

        try:
            result = subprocess.run(
                ["v4l2-ctl", "--list-devices"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            current_device_name = None
            for line in result.stdout.strip().split("\n") if result.stdout else []:
                line = line.strip()
                if not line:
                    continue

                if any(
                    keyword in line.lower()
                    for keyword in ["error", "failed", "cannot", "permission denied"]
                ):
                    continue

                if not line.startswith("/dev/"):
                    current_device_name = line.rstrip(":").split("(")[0].strip()
                    continue

                device_path = line
                if not current_device_name or "/dev/video" not in device_path:
                    continue

                if not self._can_capture_video(device_path):
                    logger.debug(f"Skipping {device_path} - no capture capability")
                    continue

                device_num = device_path.replace("/dev/video", "")
                device_name = _slugify_device_name(current_device_name)
                best_capture = select_best_from_v4l2_formats(self._parse_v4l2_formats(device_path))

                cameras.append(
                    InternalCamera(
                        device_name=current_device_name,
                        device_type=InternalCameraType.USB,
                        device_id=f"usb-camera-{device_name}-{device_num}",
                        details=InternalUSBCameraDetails(
                            device_path=device_path,
                            best_capture=best_capture,
                        ),
                    )
                )

        except FileNotFoundError:
            logger.error("v4l2-ctl not found, cannot discover USB cameras")
        except subprocess.TimeoutExpired:
            logger.error("v4l2-ctl command timed out")
        except Exception as e:
            logger.error(f"Error discovering USB cameras: {e}", exc_info=True)

        logger.debug(f"Discovered {len(cameras)} USB camera(s)")
        return cameras
