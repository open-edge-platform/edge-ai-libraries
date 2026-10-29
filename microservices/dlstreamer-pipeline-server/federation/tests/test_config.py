# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import io
import tempfile

import pytest
import yaml

from src.config import FederationConfig, NodeConfig, load_config


class TestNodeConfig:
    def test_defaults(self):
        node = NodeConfig(id="n1", url="http://localhost:8080")
        assert node.max_pipelines == 50
        assert node.ssh is None

    def test_all_fields(self):
        node = NodeConfig(id="n1", url="http://host:8080", max_pipelines=30, ssh="user@host")
        assert node.max_pipelines == 30
        assert node.ssh == "user@host"


class TestLoadConfig:
    def test_loads_nodes(self, tmp_path):
        cfg = {
            "nodes": [
                {"id": "a", "url": "http://a:8080"},
                {"id": "b", "url": "http://b:8080", "max_pipelines": 25, "ssh": "u@b"},
            ],
            "health_check_interval": 5,
            "request_timeout": 3.0,
        }
        path = tmp_path / "nodes.yaml"
        path.write_text(yaml.dump(cfg))

        result = load_config(path)
        assert isinstance(result, FederationConfig)
        assert len(result.nodes) == 2
        assert result.nodes[0].id == "a"
        assert result.nodes[1].ssh == "u@b"
        assert result.health_check_interval == 5
        assert result.request_timeout == 3.0

    def test_defaults_for_optional_fields(self, tmp_path):
        cfg = {"nodes": [{"id": "x", "url": "http://x:8080"}]}
        path = tmp_path / "nodes.yaml"
        path.write_text(yaml.dump(cfg))

        result = load_config(path)
        assert result.health_check_interval == 10
        assert result.request_timeout == 5.0

    def test_empty_nodes(self, tmp_path):
        path = tmp_path / "nodes.yaml"
        path.write_text(yaml.dump({"nodes": []}))

        result = load_config(path)
        assert result.nodes == []
