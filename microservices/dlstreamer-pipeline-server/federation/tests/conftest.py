# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pytest

from src.config import FederationConfig, NodeConfig


@pytest.fixture
def two_nodes():
    return [
        NodeConfig(id="node-1", url="http://node1:8080", max_pipelines=50),
        NodeConfig(id="node-2", url="http://node2:8080", max_pipelines=50),
    ]


@pytest.fixture
def config(two_nodes):
    return FederationConfig(nodes=two_nodes, health_check_interval=10, request_timeout=2.0)
