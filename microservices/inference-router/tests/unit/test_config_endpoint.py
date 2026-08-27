# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.api.v1 import _config_runtime
from src.config import ProviderConfig, RouterConfig, RoutingConfig, TelemetryConfig
from src.config.base import TelemetryBackendType
from ._api_contract_support import make_test_client


pytestmark = pytest.mark.unit


def _build_config(*, api_key: str = "top-secret") -> RouterConfig:
    return RouterConfig(
        providers=[
            ProviderConfig(
                name="provider-alpha",
                type="openai",
                model="model-alpha",
                enabled=True,
                settings={
                    "endpoint": "https://example.invalid/v1",
                    "timeout": 30.0,
                    "auth": {
                        "scheme": "bearer",
                        "api_key": api_key,
                        "custom_headers": {},
                    },
                },
            )
        ],
        routing=RoutingConfig(policy="Balanced"),
        telemetry=TelemetryConfig(backend=TelemetryBackendType.MEMORY, enabled=True),
        log_level="INFO",
        cors_origins=["*"],
    )


def _write_config(path: Path, config: RouterConfig) -> None:
    data = _config_runtime.serialize_router_config(config)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def test_get_config_returns_redacted_values(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config = _build_config(api_key="super-secret")
    _write_config(config_path, config)
    client = make_test_client(config=config, config_path=config_path)

    response = client.get("/v1/config")

    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "config"
    assert body["path"] == str(config_path)
    assert body["data"]["providers"][0]["settings"]["auth"]["api_key"] == "***REDACTED***"