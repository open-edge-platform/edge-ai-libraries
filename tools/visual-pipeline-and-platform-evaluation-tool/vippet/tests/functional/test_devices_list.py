"""Integration test covering the devices endpoint happy path.

Run with Python 3.12+ and pytest while the VIPPET API is available locally:

    python3.12 -m pytest integration/test_devices_list.py
"""

import logging

import pytest
import requests

from api_helpers import fetch_devices
from vippet.api.api_schemas import Device

logger = logging.getLogger(__name__)

pytestmark = pytest.mark.integration


def test_devices_endpoint_returns_devices(http_client: requests.Session) -> None:
    devices = fetch_devices(http_client)

    assert devices, "Devices endpoint returned an empty list"
    for raw in devices:
        Device.model_validate(raw)
