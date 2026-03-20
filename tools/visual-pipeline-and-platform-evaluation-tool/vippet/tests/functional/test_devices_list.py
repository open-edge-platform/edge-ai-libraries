"""Functional test covering the devices endpoint happy path."""

import logging

import pytest
import requests

from helpers.api_helpers import fetch_devices

logger = logging.getLogger(__name__)

REQUIRED_DEVICE_KEYS: set[str] = {
    "device_name",
    "full_device_name",
    "device_type",
    "device_family",
    "gpu_id",
}
VALID_DEVICE_FAMILIES: set[str] = {"CPU", "GPU", "NPU"}


@pytest.mark.smoke
def test_devices_endpoint_returns_devices(http_client: requests.Session) -> None:
    devices = fetch_devices(http_client)

    assert devices, "Devices endpoint returned an empty list"
    logger.info("Available devices (%d): %s", len(devices), devices)
    for raw in devices:
        assert isinstance(raw, dict), "Each device entry must be an object"
        assert REQUIRED_DEVICE_KEYS.issubset(raw.keys()), (
            f"Device entry missing required keys: {REQUIRED_DEVICE_KEYS - raw.keys()}"
        )
        assert raw["device_family"] in VALID_DEVICE_FAMILIES, (
            f"Unexpected device_family {raw['device_family']!r}; expected one of {VALID_DEVICE_FAMILIES}"
        )
