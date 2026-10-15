# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
from dataclasses import dataclass


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    log_level: str
    onvif_discovery_enabled: bool
    onvif_discovery_interval_s: float

    @classmethod
    def from_env(cls) -> "Settings":
        port = int(os.environ.get("SENSOR_MANAGER_PORT", "8090"))
        if not 1 <= port <= 65535:
            raise ValueError(f"SENSOR_MANAGER_PORT out of range: {port}")
        interval = float(os.environ.get("ONVIF_DISCOVERY_INTERVAL_S", "20"))
        if interval < 1:
            raise ValueError(f"ONVIF_DISCOVERY_INTERVAL_S must be >= 1, got {interval}")
        return cls(
            # Host networking is required for WS-Discovery, so the bind address stays configurable.
            host=os.environ.get("SENSOR_MANAGER_HOST", "0.0.0.0"),  # noqa: S104
            port=port,
            log_level=os.environ.get("LOG_LEVEL", "INFO").upper(),
            onvif_discovery_enabled=_env_bool("ONVIF_DISCOVERY_ENABLED", True),
            onvif_discovery_interval_s=interval,
        )
