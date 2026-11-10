# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
OpenVINO device discovery for DLSPS 2.0.

Devices and their read-only properties are probed once at startup and kept
in a module-level cache. Requests read the cache only, so they never touch
OpenVINO and cannot interfere with running pipelines.
"""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# COMPATIBILITY_CHECK is a parameterized query and cannot be read as a plain property.
_SKIPPED_PROPERTIES = frozenset({"COMPATIBILITY_CHECK", "SUPPORTED_PROPERTIES"})

_devices: Optional[list[dict[str, Any]]] = None


def _to_json(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, dict):
        return {str(_to_json(k)): _to_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_json(v) for v in value]
    # OpenVINO enums expose their symbolic name; other objects fall back to str().
    name = getattr(value, "name", None)
    if isinstance(name, str):
        return name
    return str(value)


def _probe_devices() -> list[dict[str, Any]]:
    # Imported here so the API still starts (with device discovery disabled) without OpenVINO.
    import openvino as ov

    core = ov.Core()
    devices = []
    for device_name in core.available_devices:
        supported = core.get_property(device_name, "SUPPORTED_PROPERTIES")
        properties: dict[str, Any] = {}
        for prop, mode in supported.items():
            if mode != "RO" or prop in _SKIPPED_PROPERTIES:
                continue
            try:
                properties[prop] = _to_json(core.get_property(device_name, prop))
            except Exception as exc:  # noqa: BLE001
                logger.debug("Skipping property %s on device %s: %s", prop, device_name, exc)
        devices.append({"name": device_name, "properties": properties})
    return devices


def init_device_cache() -> None:
    """Probe OpenVINO devices once and cache the result. Failures are logged and leave the cache unset."""
    global _devices
    try:
        _devices = _probe_devices()
        logger.info(
            "Cached %d OpenVINO device(s): %s",
            len(_devices),
            [device["name"] for device in _devices],
        )
    except ImportError:
        _devices = None
        logger.error("OpenVINO Python bindings not importable; device discovery disabled")
    except Exception:  # noqa: BLE001
        _devices = None
        logger.exception("OpenVINO device discovery failed")


def get_cached_devices() -> Optional[list[dict[str, Any]]]:
    """Return the cached device list, or None if discovery failed or never ran."""
    return _devices
