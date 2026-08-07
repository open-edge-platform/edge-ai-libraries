# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

import asyncio

from src.api.v1 import _config_runtime
from src.api.v1 import config as config_api
from src.config import PluginConfig, ProviderConfig, RouterConfig, RoutingConfig, TelemetryConfig
from src.config.base import TelemetryBackendType
from src.models import ChatCompletionMessage, ChatCompletionRequest, ChatCompletionResponse
from src.plugins.dummy import DummyLoggerPlugin
from ._api_contract_support import RouterStub, make_test_client


pytestmark = pytest.mark.unit


class FakeOrchestrator:
    def __init__(self, config: RouterConfig, decision_engine=None, telemetry=None):
        self.config = config
        self.decision_engine = decision_engine
        self.telemetry = telemetry
        self.plugin_manager = object()

    async def initialize(self) -> None:
        return None

    def shutdown(self) -> None:
        return None

    async def health_check(self) -> dict[str, bool]:
        return {"fake": True}

    async def chat(self, _request) -> tuple[ChatCompletionResponse, object]:
        raise NotImplementedError


def _build_config(*, plugins: list[PluginConfig] | None = None) -> RouterConfig:
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
                    "auth": {"scheme": "none", "api_key": None, "custom_headers": {}},
                },
            )
        ],
        plugins=plugins or [],
        routing=RoutingConfig(policy="Balanced"),
        telemetry=TelemetryConfig(backend=TelemetryBackendType.MEMORY, enabled=True),
        log_level="INFO",
        cors_origins=["*"],
    )


def _write_config(path: Path, config: RouterConfig) -> None:
    data = _config_runtime.serialize_router_config(config)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def test_list_plugins_includes_disabled_entries(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config = _build_config(
        plugins=[
            PluginConfig(name="pre-one", node="dummy_logger", trigger="prerouting", settings={"label": "pre"}),
            PluginConfig(name="post-two", node="dummy_logger", trigger="postresponse", enabled=False, settings={"label": "post"}),
        ]
    )
    _write_config(config_path, config)
    client = make_test_client(config=config, config_path=config_path)

    response = client.get("/v1/plugins")

    assert response.status_code == 200
    body = response.json()
    assert {plugin["name"] for plugin in body["data"]} == {"pre-one", "post-two"}
    disabled = next(plugin for plugin in body["data"] if plugin["name"] == "post-two")
    assert disabled["enabled"] is False
    assert disabled["settings"] == {"label": "post"}


def test_list_plugin_nodes_returns_registered_types(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config = _build_config()
    _write_config(config_path, config)
    client = make_test_client(config=config, config_path=config_path)

    response = client.get("/v1/plugins/nodes")

    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "list"
    nodes = {entry["node"]: entry for entry in body["data"]}
    # The dummy_logger type is always registered and carries a settings schema.
    assert "dummy_logger" in nodes
    assert nodes["dummy_logger"]["settings_schema"].get("type") == "object"


def test_get_plugin_node_returns_type_metadata(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config = _build_config()
    _write_config(config_path, config)
    client = make_test_client(config=config, config_path=config_path)

    response = client.get("/v1/plugins/dummy_logger")

    assert response.status_code == 200
    body = response.json()
    # Default describe_node() hook returns the node's type metadata.
    assert body["node"] == "dummy_logger"
    assert body["settings_schema"].get("type") == "object"


def test_get_plugin_node_unknown_type_404(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config = _build_config()
    _write_config(config_path, config)
    client = make_test_client(config=config, config_path=config_path)

    response = client.get("/v1/plugins/does-not-exist")

    assert response.status_code == 404
    assert "not registered" in response.json()["detail"]


def test_create_plugin_persists_and_updates_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_config_runtime, "RouterOrchestrator", FakeOrchestrator)
    config_path = tmp_path / "config.yaml"
    config = _build_config()
    _write_config(config_path, config)
    client = make_test_client(config=config, config_path=config_path)

    response = client.post(
        "/v1/plugins/dummy_logger/new-plugin",
        json={"trigger": "prerouting", "settings": {"label": "created"}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "new-plugin"
    assert body["trigger"] == "prerouting"
    assert body["settings"] == {"label": "created"}

    persisted = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert persisted["plugins"]["prerouting"] == [
        {"name": "new-plugin", "node": "dummy_logger", "enabled": True, "settings": {"label": "created"}}
    ]


def test_update_plugin_can_move_trigger_and_disable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_config_runtime, "RouterOrchestrator", FakeOrchestrator)
    config_path = tmp_path / "config.yaml"
    config = _build_config(
        plugins=[
            PluginConfig(name="move-me", node="dummy_logger", trigger="prerouting", settings={"label": "before"})
        ]
    )
    _write_config(config_path, config)
    client = make_test_client(config=config, config_path=config_path)

    response = client.post(
        "/v1/plugins/dummy_logger/move-me",
        json={"trigger": "postresponse", "enabled": False, "settings": {"label": "after"}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["trigger"] == "postresponse"
    assert body["enabled"] is False
    assert body["settings"] == {"label": "after"}

    persisted = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert persisted["plugins"]["prerouting"] == []
    assert persisted["plugins"]["postresponse"] == [
        {"name": "move-me", "node": "dummy_logger", "enabled": False, "settings": {"label": "after"}}
    ]


def test_update_plugin_rejects_invalid_trigger_before_persist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_config_runtime, "RouterOrchestrator", FakeOrchestrator)
    config_path = tmp_path / "config.yaml"
    config = _build_config()
    _write_config(config_path, config)
    before = config_path.read_text(encoding="utf-8")
    client = make_test_client(config=config, config_path=config_path)

    response = client.post(
        "/v1/plugins/dummy_logger/bad-trigger",
        json={"trigger": "not-a-trigger", "settings": {"label": "bad"}},
    )

    assert response.status_code == 422
    assert config_path.read_text(encoding="utf-8") == before


def test_delete_plugin_removes_runtime_and_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_config_runtime, "RouterOrchestrator", FakeOrchestrator)
    config_path = tmp_path / "config.yaml"
    config = _build_config(
        plugins=[
            PluginConfig(name="delete-me", node="dummy_logger", trigger="prerouting", settings={"label": "bye"})
        ]
    )
    _write_config(config_path, config)
    client = make_test_client(config=config, config_path=config_path)

    response = client.delete("/v1/plugins/dummy_logger/delete-me")

    assert response.status_code == 200
    assert response.json()["status"] == "success"
    persisted = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert persisted["plugins"]["prerouting"] == []

    missing = client.get("/v1/plugins/dummy_logger/delete-me")
    assert missing.status_code == 404


# A config file written by hand with an env-var placeholder for the API key.
# ``${SECRET_KEY}`` must survive plugin edits untouched — the runtime holds the
# resolved value, but persistence must never leak it into the reviewable file.
_RAW_CONFIG_WITH_PLACEHOLDER = """\
log_level: INFO
providers:
  - name: provider-alpha
    type: openai
    model: model-alpha
    enabled: true
    metadata: {}
    settings:
      endpoint: https://example.invalid/v1
      timeout: 30.0
      auth:
        scheme: bearer
        api_key: ${SECRET_KEY}
        custom_headers: {}
plugins:
  prerouting: []
  postrouting: []
  postresponse: []
routing:
  policy: Balanced
  strategy: null
telemetry:
  backend: memory
  enabled: true
  file_path: null
cors_origins:
  - '*'
"""


def test_plugin_write_preserves_env_placeholder_in_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_config_runtime, "RouterOrchestrator", FakeOrchestrator)
    config_path = tmp_path / "config.yaml"
    # File on disk carries the ``${SECRET_KEY}`` placeholder ...
    config_path.write_text(_RAW_CONFIG_WITH_PLACEHOLDER, encoding="utf-8")
    # ... while the running config holds the *resolved* secret in memory.
    config = _build_config()
    config.providers[0].settings["auth"]["api_key"] = "resolved-super-secret"
    client = make_test_client(config=config, config_path=config_path)

    response = client.post(
        "/v1/plugins/dummy_logger/new-plugin",
        json={"trigger": "prerouting", "settings": {"label": "created"}},
    )
    assert response.status_code == 200

    written = config_path.read_text(encoding="utf-8")
    # The plugin change landed ...
    persisted = yaml.safe_load(written)
    assert persisted["plugins"]["prerouting"] == [
        {"name": "new-plugin", "node": "dummy_logger", "enabled": True, "settings": {"label": "created"}}
    ]
    # ... but the placeholder is intact and the resolved secret never hit disk.
    assert "${SECRET_KEY}" in written
    assert "resolved-super-secret" not in written


# ─────────────────────────────────────────────────────────────────────────
# Per-plugin metrics endpoint
# ─────────────────────────────────────────────────────────────────────────


class _StubPlugin:
    """Minimal live-plugin stand-in for the manager lookup (name + plugin_type)."""

    def __init__(self, name: str, node: str, metrics, reset_ok: bool) -> None:
        self.name = name
        self._node = node
        self._metrics = metrics
        self._reset_ok = reset_ok

    def plugin_type(self) -> str:
        return self._node

    def describe(self):
        return {"name": self.name, "node": self._node, "metrics": self._metrics}

    def reset(self) -> bool:
        return self._reset_ok


class _StubManager:
    """Plugin manager exposing a fixed set of live plugin instances."""

    def __init__(self, plugins) -> None:
        self._plugins = list(plugins)

    def get_all_plugins_config(self):
        return []

    def get_plugin_by_name_and_node(self, name: str, node: str):
        for plugin in self._plugins:
            if plugin.name == name and plugin.plugin_type() == node:
                return plugin
        return None


def _client_with_plugins(*plugins) -> "object":
    router = RouterStub()
    router.plugin_manager = _StubManager(plugins)
    return make_test_client(router=router)


def test_get_plugin_detail_includes_instance_metrics() -> None:
    plugin = DummyLoggerPlugin(name="metric-dummy", settings={"label": "m"}, trigger="prerouting")
    request = ChatCompletionRequest(model="auto", messages=[ChatCompletionMessage(role="user", content="hi")])
    asyncio.run(plugin.process_request(request))
    asyncio.run(plugin.process_request(request))
    client = _client_with_plugins(plugin)

    response = client.get("/v1/plugins/dummy_logger/metric-dummy")

    assert response.status_code == 200
    body = response.json()
    # describe() folds per-instance metrics into the detail payload.
    assert body["name"] == "metric-dummy"
    assert body["node"] == "dummy_logger"
    assert body["metrics"] == {"process_request": 2, "process_response": 0}


def test_reset_plugin_instance_zeroes_metrics() -> None:
    plugin = DummyLoggerPlugin(name="metric-dummy", settings={"label": "m"}, trigger="prerouting")
    request = ChatCompletionRequest(model="auto", messages=[ChatCompletionMessage(role="user", content="hi")])
    asyncio.run(plugin.process_request(request))
    client = _client_with_plugins(plugin)

    reset = client.post("/v1/plugins/dummy_logger/metric-dummy/reset")
    assert reset.status_code == 200
    assert reset.json()["status"] == "success"

    after = client.get("/v1/plugins/dummy_logger/metric-dummy")
    assert after.json()["metrics"] == {"process_request": 0, "process_response": 0}


def test_reset_plugin_instance_not_loaded_404() -> None:
    client = _client_with_plugins()

    response = client.post("/v1/plugins/dummy_logger/nope/reset")

    assert response.status_code == 404
    assert "not loaded" in response.json()["detail"]


def test_reset_plugin_instance_unsupported_400() -> None:
    # A plugin whose reset() returns False does not support reset.
    plugin = _StubPlugin("plain", "plain_node", metrics=None, reset_ok=False)
    client = _client_with_plugins(plugin)

    response = client.post("/v1/plugins/plain_node/plain/reset")

    assert response.status_code == 400
    assert "does not support reset" in response.json()["detail"]


def test_reset_plugin_node_unsupported_400() -> None:
    # dummy_logger's reset_node() default returns False.
    client = _client_with_plugins()

    response = client.post("/v1/plugins/dummy_logger/reset")

    assert response.status_code == 400
    assert "does not support reset" in response.json()["detail"]


def test_reset_plugin_node_unknown_404() -> None:
    client = _client_with_plugins()

    response = client.post("/v1/plugins/does-not-exist/reset")

    assert response.status_code == 404
    assert "not registered" in response.json()["detail"]


def test_plugin_write_is_atomic_and_leaves_no_temp_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_config_runtime, "RouterOrchestrator", FakeOrchestrator)
    config_path = tmp_path / "config.yaml"
    config = _build_config()
    _write_config(config_path, config)
    client = make_test_client(config=config, config_path=config_path)

    response = client.post(
        "/v1/plugins/dummy_logger/atomic",
        json={"trigger": "prerouting", "settings": {"label": "x"}},
    )
    assert response.status_code == 200
    # No stray temp file survives a successful atomic rename.
    assert list(tmp_path.glob("*.tmp")) == []