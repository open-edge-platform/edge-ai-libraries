# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Tests for OpenVINO device discovery and the GET /devices cache."""

import sys
import types

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import devices as devices_router
from core import openvino_devices


_MODES = {
    "CPU": {"SUPPORTED_PROPERTIES": "RO", "FULL_DEVICE_NAME": "RO", "NUM_STREAMS": "RW"},
    "GPU": {"SUPPORTED_PROPERTIES": "RO", "FULL_DEVICE_NAME": "RO", "COMPATIBILITY_CHECK": "RO"},
}
_VALUES = {
    "CPU": {"FULL_DEVICE_NAME": "Fake CPU", "NUM_STREAMS": 1},
    "GPU": {"FULL_DEVICE_NAME": "Fake GPU"},
}


class _FakeCore:
    available_devices = ["CPU", "GPU"]

    def get_property(self, device, prop):
        if prop == "SUPPORTED_PROPERTIES":
            return _MODES[device]
        if prop == "COMPATIBILITY_CHECK":
            raise TypeError("parameterized property")
        return _VALUES[device][prop]


@pytest.fixture
def fake_openvino(monkeypatch):
    module = types.ModuleType("openvino")
    module.Core = _FakeCore
    monkeypatch.setitem(sys.modules, "openvino", module)
    monkeypatch.setattr(openvino_devices, "_devices", None)
    return module


def _client():
    app = FastAPI()
    app.include_router(devices_router.router)
    return TestClient(app)


def test_init_caches_read_only_properties(fake_openvino):
    openvino_devices.init_device_cache()

    devices = openvino_devices.get_cached_devices()
    assert [d["name"] for d in devices] == ["CPU", "GPU"]
    assert devices[0]["properties"] == {"FULL_DEVICE_NAME": "Fake CPU"}
    assert devices[1]["properties"] == {"FULL_DEVICE_NAME": "Fake GPU"}


def test_get_devices_serves_cache(fake_openvino):
    openvino_devices.init_device_cache()

    response = _client().get("/devices")

    assert response.status_code == 200
    assert response.json()[0]["name"] == "CPU"


def test_get_devices_returns_503_when_discovery_failed(monkeypatch):
    monkeypatch.setitem(sys.modules, "openvino", None)  # forces ImportError
    monkeypatch.setattr(openvino_devices, "_devices", None)

    openvino_devices.init_device_cache()
    response = _client().get("/devices")

    assert openvino_devices.get_cached_devices() is None
    assert response.status_code == 503


def test_to_json_converts_enum_like_values():
    class Enumish:
        name = "INTEGRATED"

    assert openvino_devices._to_json({"k": Enumish()}) == {"k": "INTEGRATED"}
    assert openvino_devices._to_json((1, "a")) == [1, "a"]
