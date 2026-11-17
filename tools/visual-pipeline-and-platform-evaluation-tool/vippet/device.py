from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import logging
import re
import threading
import time
from typing import Any, Optional

import httpx

from dlsps2_runner import DLSPS2_BASE_URL, DLSPS2_HTTP_TIMEOUT_S, DLSPS2_VERIFY_TLS

logger = logging.getLogger("device")

# Attempts, and seconds between them, to read the device list when it is first needed.
DEVICES_READ_ATTEMPTS = 5
DEVICES_RETRY_DELAY_S = 2.0


class DeviceType(Enum):
    DISCRETE = "DISCRETE"
    INTEGRATED = "INTEGRATED"


class DeviceFamily(Enum):
    CPU = "CPU"
    GPU = "GPU"
    NPU = "NPU"


class DeviceDiscoveryError(Exception):
    """Raised when the device list cannot be read from DLSPS 2.0."""


@dataclass
class DeviceInfo:
    """
    Inference device of DL Streamer Pipeline Server 2.0.

    Built from one entry of the server's ``GET /devices``, which lists the
    OpenVINO devices of the server runtime with their read-only properties.
    Only some of them are kept here. An entry looks like this:

        {
            "name": "GPU.0",
            "properties": {
                "DEVICE_TYPE": "INTEGRATED",
                "FULL_DEVICE_NAME": "Intel(R) Arc(TM) Graphics (iGPU)",
                "OPTIMIZATION_CAPABILITIES": ["FP32", "BIN", "FP16", "INT8", "EXPORT_IMPORT"],
                ...
            }
        }
    """

    device_name: str
    full_device_name: str = ""
    device_type: "DeviceType" = DeviceType.INTEGRATED
    device_family: "DeviceFamily" = DeviceFamily.CPU
    gpu_id: int | None = None


class DeviceDiscovery:
    """
    Thread-safe singleton listing the inference devices of DLSPS 2.0.

    Pipelines run on DLSPS 2.0, so the devices they may use are those of the
    server: they are read from its ``GET /devices``. The first list read is
    kept for the lifetime of the process. Until a read succeeds, every call
    to :meth:`list_devices` asks the server again and raises
    :class:`DeviceDiscoveryError` if it does not answer.
    """

    _instance: Optional["DeviceDiscovery"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "DeviceDiscovery":
        if cls._instance is None:
            with cls._lock:
                # Double-checked locking
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        # Protect against multiple initialization
        if hasattr(self, "_initialized"):
            return
        self._initialized = True

        self._devices_lock = threading.Lock()
        self._devices: list[DeviceInfo] | None = None
        self._read_attempts = DEVICES_READ_ATTEMPTS

    def list_devices(self) -> list[DeviceInfo]:
        """
        List the inference devices of DLSPS 2.0.

        The first read retries a few times, so a server that is still
        starting does not fail it; later reads, made only while no list has
        been read yet, try once.

        Returns:
            list[DeviceInfo]: The devices, in the order the server lists them.

        Raises:
            DeviceDiscoveryError: The server's device list cannot be read.
        """
        if self._devices is None:
            with self._devices_lock:
                if self._devices is None:
                    attempts, self._read_attempts = self._read_attempts, 1
                    self._devices = self._read_devices(attempts)
        return self._devices

    def _read_devices(self, attempts: int) -> list[DeviceInfo]:
        error: Exception | None = None
        for attempt in range(attempts):
            if attempt:
                time.sleep(DEVICES_RETRY_DELAY_S)
            try:
                return self._parse_devices(self._get_dlsps2_devices())
            except (
                httpx.HTTPError,
                ValueError,
                KeyError,
                TypeError,
                AttributeError,
            ) as e:
                error = e
        raise DeviceDiscoveryError(
            f"Cannot read devices from DLSPS 2.0 at {DLSPS2_BASE_URL}: {error}"
        ) from error

    @staticmethod
    def _get_dlsps2_devices() -> list[dict[str, Any]]:
        response = httpx.get(
            f"{DLSPS2_BASE_URL}/devices",
            timeout=DLSPS2_HTTP_TIMEOUT_S,
            verify=DLSPS2_VERIFY_TLS,
        )
        response.raise_for_status()
        entries = response.json()
        if not isinstance(entries, list):
            raise TypeError(f"expected a device list, got {type(entries).__name__}")
        return entries

    def _parse_devices(self, entries: list[dict[str, Any]]) -> list[DeviceInfo]:
        devices = []
        for entry in entries:
            device = str(entry["name"])
            properties = entry.get("properties") or {}
            devices.append(
                DeviceInfo(
                    device_name=device,
                    full_device_name=str(properties.get("FULL_DEVICE_NAME", device)),
                    device_type=self.parse_device_type(
                        device, properties.get("DEVICE_TYPE")
                    ),
                    device_family=self.parse_device_family(device),
                    gpu_id=self.parse_gpu_id(device),
                )
            )

        # Add "GPU.<gpu_id>" to full_device_name if there are multiple GPUs
        gpu_devices = [d for d in devices if d.device_family == DeviceFamily.GPU]
        if len(gpu_devices) > 1:
            for d in gpu_devices:
                d.full_device_name += f" ({d.device_name})"
        return devices

    @staticmethod
    def parse_device_type(device: str, device_type: Any) -> DeviceType:
        # DLSPS 2.0 reports the OpenVINO DEVICE_TYPE enum by its name.
        try:
            return DeviceType(device_type)
        except ValueError:
            logger.error(
                f"Unknown device type: {device_type} for device: {device}. Fallback to INTEGRATED."
            )
            return DeviceType.INTEGRATED

    @staticmethod
    def parse_device_family(device: str) -> DeviceFamily:
        if device.startswith("CPU"):
            return DeviceFamily.CPU
        elif device.startswith("GPU"):
            return DeviceFamily.GPU
        elif device.startswith("NPU"):
            return DeviceFamily.NPU
        else:
            logger.error(
                f"Unknown device family for device: {device}. Fallback to CPU."
            )
            return DeviceFamily.CPU

    @staticmethod
    def parse_gpu_id(device: str) -> int | None:
        if device == "GPU":
            return 0
        elif device.startswith("GPU."):
            parts = device.split(".")
            if len(parts) == 2 and parts[1].isdigit():
                return int(parts[1])
            else:
                logger.info(f"Incorrect gpu_id for device: {device}")
                return None
        else:
            return None


def running_on_wsl() -> bool:
    """
    Check whether the application runs on a WSL host.

    Returns:
        bool: True if the WSL GPU device node is present, False otherwise.
    """
    return Path("/dev/dxg").exists()


def is_variant_supported(variant_name: str) -> bool:
    """
    Check whether a pipeline variant can run on the current platform.

    Variant names encode the devices they use, for example "CPU", "GPU",
    "GPU_NPU" or "GPU (WSL)". A variant is supported when every device family
    it requires is available and, for GPU variants, when its WSL flavour
    matches the current platform.

    Args:
        variant_name (str): Variant name as defined in the pipeline configuration.

    Returns:
        bool: True if the variant can run on this platform, False otherwise.
    """
    tokens = re.split(r"[^A-Z]+", variant_name.upper())
    required = {
        DeviceFamily(token) for token in tokens if token in DeviceFamily.__members__
    }
    if not required:
        return True

    try:
        available = {
            device.device_family for device in DeviceDiscovery().list_devices()
        }
    except Exception:
        logger.exception(
            "Device discovery failed, assuming variant '%s' is supported", variant_name
        )
        return True

    if not required.issubset(available):
        return False

    if DeviceFamily.GPU in required and ("WSL" in tokens) != running_on_wsl():
        return False

    return True
