# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class NodeConfig:
    id: str
    url: str
    max_pipelines: int = 50
    ssh: str | None = None


@dataclass
class FederationConfig:
    nodes: list[NodeConfig] = field(default_factory=list)
    health_check_interval: int = 10
    request_timeout: float = 5.0


def load_config(path: str | Path) -> FederationConfig:
    with open(Path(path)) as f:
        data = yaml.safe_load(f)

    nodes = [NodeConfig(**n) for n in data.get("nodes", [])]
    return FederationConfig(
        nodes=nodes,
        health_check_interval=data.get("health_check_interval", 10),
        request_timeout=data.get("request_timeout", 5.0),
    )
