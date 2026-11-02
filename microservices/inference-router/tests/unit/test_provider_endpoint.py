# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.api.v1 import _config_runtime
from src.config import ProviderConfig, RouterConfig, RoutingConfig, TelemetryConfig
from src.config.base import TelemetryBackendType
from src.models import ChatCompletionResponse
from ._api_contract_support import make_test_client


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


def _provider(
    name: str,
    *,
    model: str = "model-alpha",
    enabled: bool = True,
    fallback: bool = False,
    api_key: str | None = None,
) -> ProviderConfig:
    return ProviderConfig(
        name=name,
        type="openai",
        model=model,
        enabled=enabled,
        fallback=fallback,
        metadata={"labels": [name], "cost": 0},
        settings={
            "endpoint": f"https://{name}.invalid/v1",
            "timeout": 30.0,
            "auth": {"scheme": "bearer", "api_key": api_key, "custom_headers": {}},
        },
    )


def _build_config(*, providers: list[ProviderConfig] | None = None) -> RouterConfig:
    return RouterConfig(
        providers=providers or [_provider("provider-alpha")],
        plugins=[],
        routing=RoutingConfig(policy="Balanced"),
        telemetry=TelemetryConfig(backend=TelemetryBackendType.MEMORY, enabled=True),
        log_level="INFO",
        cors_origins=["*"],
    )


def _write_config(path: Path, config: RouterConfig) -> None:
    data = _config_runtime.serialize_router_config(config)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def test_list_providers_includes_disabled_and_redacts_secrets(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config = _build_config(
        providers=[
            _provider("provider-alpha", api_key="sk-super-secret"),
            _provider("provider-beta", model="model-beta", enabled=False),
        ]
    )
    _write_config(config_path, config)
    client = make_test_client(config=config, config_path=config_path)

    response = client.get("/v1/providers")

    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "list"
    assert {provider["name"] for provider in body["data"]} == {"provider-alpha", "provider-beta"}

    beta = next(provider for provider in body["data"] if provider["name"] == "provider-beta")
    assert beta["enabled"] is False

    alpha = next(provider for provider in body["data"] if provider["name"] == "provider-alpha")
    # Secret is redacted, non-sensitive settings are passed through untouched.
    assert alpha["settings"]["auth"]["api_key"] == "***REDACTED***"
    assert alpha["settings"]["endpoint"] == "https://provider-alpha.invalid/v1"
    assert alpha["metadata"]["labels"] == ["provider-alpha"]


def test_get_provider_found_and_missing(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config = _build_config(providers=[_provider("provider-alpha", api_key="sk-secret")])
    _write_config(config_path, config)
    client = make_test_client(config=config, config_path=config_path)

    found = client.get("/v1/providers/provider-alpha")
    assert found.status_code == 200
    body = found.json()
    assert body["name"] == "provider-alpha"
    assert body["type"] == "openai"
    assert body["model"] == "model-alpha"
    assert body["settings"]["auth"]["api_key"] == "***REDACTED***"

    missing = client.get("/v1/providers/nope")
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Provider 'nope' not found"


def test_get_provider_reflects_live_probe_metadata(tmp_path: Path) -> None:
    """GET surfaces the live provider-instance metadata (what routing reads).

    A probe mutates the running provider's ``ProviderMetadata`` in memory; the
    read API overlays that live view so e.g. ``performance.num_requests_waiting``
    is visible — without the value ever being written to ``config.yaml``.
    """
    from src.providers.base import ProviderMetadata
    from ._api_contract_support import RouterStub

    config_path = tmp_path / "config.yaml"
    config = _build_config(providers=[_provider("provider-alpha")])
    _write_config(config_path, config)

    class _LiveProvider:
        def __init__(self) -> None:
            # Config carries ttft; the probe added num_requests_waiting live.
            self.metadata = ProviderMetadata(
                labels=["provider-alpha"],
                cost=0,
                performance={"ttft_ms": 300, "num_requests_waiting": 4.0},
            )

    router = RouterStub()
    router.provider_map = {"provider-alpha": _LiveProvider()}

    before = config_path.read_text(encoding="utf-8")
    client = make_test_client(router=router, config=config, config_path=config_path)

    body = client.get("/v1/providers/provider-alpha").json()
    assert body["metadata"]["performance"]["num_requests_waiting"] == 4.0
    assert body["metadata"]["performance"]["ttft_ms"] == 300

    # Reflection is read-only: the on-disk config is untouched by the GET.
    assert config_path.read_text(encoding="utf-8") == before
    assert "num_requests_waiting" not in before


def test_create_provider_persists_and_updates_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_config_runtime, "RouterOrchestrator", FakeOrchestrator)
    config_path = tmp_path / "config.yaml"
    config = _build_config()
    _write_config(config_path, config)
    client = make_test_client(config=config, config_path=config_path)

    response = client.post(
        "/v1/providers/cloud",
        json={
            "type": "openai",
            "model": "gpt-4o",
            "enabled": True,
            "metadata": {"labels": ["cloud"], "cost": 5},
            "settings": {"endpoint": "https://api.openai.com/v1"},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "cloud"
    assert body["type"] == "openai"
    assert body["model"] == "gpt-4o"
    assert body["metadata"] == {"labels": ["cloud"], "cost": 5}
    assert body["settings"] == {"endpoint": "https://api.openai.com/v1"}

    persisted = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    names = [provider["name"] for provider in persisted["providers"]]
    assert names == ["provider-alpha", "cloud"]
    created = persisted["providers"][1]
    assert created["type"] == "openai"
    assert created["model"] == "gpt-4o"
    assert created["settings"] == {"endpoint": "https://api.openai.com/v1"}


def test_create_provider_requires_type_and_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_config_runtime, "RouterOrchestrator", FakeOrchestrator)
    config_path = tmp_path / "config.yaml"
    config = _build_config()
    _write_config(config_path, config)
    client = make_test_client(config=config, config_path=config_path)

    # Missing both type and model on a brand-new provider.
    response = client.post("/v1/providers/incomplete", json={"enabled": True})
    assert response.status_code == 400
    assert "type" in response.json()["detail"] and "model" in response.json()["detail"]

    # Missing just the model is equally invalid.
    response = client.post("/v1/providers/incomplete", json={"type": "openai"})
    assert response.status_code == 400

    # Nothing was written to disk.
    persisted = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert [provider["name"] for provider in persisted["providers"]] == ["provider-alpha"]


def test_update_provider_toggles_enabled_and_replaces_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_config_runtime, "RouterOrchestrator", FakeOrchestrator)
    config_path = tmp_path / "config.yaml"
    config = _build_config(providers=[_provider("provider-alpha"), _provider("keep-me", model="model-keep")])
    _write_config(config_path, config)
    client = make_test_client(config=config, config_path=config_path)

    response = client.post(
        "/v1/providers/provider-alpha",
        json={"enabled": False, "settings": {"endpoint": "https://new.invalid/v1"}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["enabled"] is False
    # settings replaced wholesale, type/model preserved from the existing entry.
    assert body["settings"] == {"endpoint": "https://new.invalid/v1"}
    assert body["type"] == "openai"
    assert body["model"] == "model-alpha"

    persisted = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    updated = next(p for p in persisted["providers"] if p["name"] == "provider-alpha")
    assert updated["enabled"] is False
    assert updated["settings"] == {"endpoint": "https://new.invalid/v1"}
    # The other provider is untouched.
    assert [p["name"] for p in persisted["providers"]] == ["provider-alpha", "keep-me"]


def test_provider_fallback_defaults_to_false(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_config_runtime, "RouterOrchestrator", FakeOrchestrator)
    config_path = tmp_path / "config.yaml"
    config = _build_config()
    _write_config(config_path, config)
    client = make_test_client(config=config, config_path=config_path)

    created = client.post("/v1/providers/cloud", json={"type": "openai", "model": "gpt-4o"})

    assert created.status_code == 200
    assert created.json()["fallback"] is False
    assert client.get("/v1/providers/provider-alpha").json()["fallback"] is False


def test_setting_fallback_demotes_previous_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_config_runtime, "RouterOrchestrator", FakeOrchestrator)
    config_path = tmp_path / "config.yaml"
    config = _build_config(
        providers=[
            _provider("provider-alpha", fallback=True),
            _provider("provider-beta", model="model-beta"),
            _provider("provider-gamma", model="model-gamma"),
        ]
    )
    _write_config(config_path, config)
    client = make_test_client(config=config, config_path=config_path)

    response = client.post("/v1/providers/provider-beta", json={"fallback": True})

    assert response.status_code == 200
    assert response.json()["fallback"] is True

    # GET reflects the demotion of the previous fallback.
    assert client.get("/v1/providers/provider-alpha").json()["fallback"] is False
    listed = {p["name"]: p["fallback"] for p in client.get("/v1/providers").json()["data"]}
    assert listed == {"provider-alpha": False, "provider-beta": True, "provider-gamma": False}

    # Runtime state agrees.
    runtime = {p.name: p.fallback for p in client.app.state.config.providers}
    assert runtime == listed

    # And so does config.yaml.
    persisted = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    on_disk = {p["name"]: p.get("fallback", False) for p in persisted["providers"]}
    assert on_disk == listed


def test_creating_provider_as_fallback_demotes_previous_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_config_runtime, "RouterOrchestrator", FakeOrchestrator)
    config_path = tmp_path / "config.yaml"
    config = _build_config(providers=[_provider("provider-alpha", fallback=True)])
    _write_config(config_path, config)
    client = make_test_client(config=config, config_path=config_path)

    response = client.post(
        "/v1/providers/cloud", json={"type": "openai", "model": "gpt-4o", "fallback": True}
    )

    assert response.status_code == 200
    assert response.json()["fallback"] is True
    assert client.get("/v1/providers/provider-alpha").json()["fallback"] is False
    persisted = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert {p["name"]: p["fallback"] for p in persisted["providers"]} == {
        "provider-alpha": False,
        "cloud": True,
    }


def test_unsetting_fallback_does_not_promote_another_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_config_runtime, "RouterOrchestrator", FakeOrchestrator)
    config_path = tmp_path / "config.yaml"
    config = _build_config(
        providers=[
            _provider("provider-alpha", fallback=True),
            _provider("provider-beta", model="model-beta"),
        ]
    )
    _write_config(config_path, config)
    client = make_test_client(config=config, config_path=config_path)

    response = client.post("/v1/providers/provider-alpha", json={"fallback": False})

    assert response.status_code == 200
    listed = {p["name"]: p["fallback"] for p in client.get("/v1/providers").json()["data"]}
    assert listed == {"provider-alpha": False, "provider-beta": False}


def test_routing_update_preserves_provider_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_config_runtime, "RouterOrchestrator", FakeOrchestrator)
    config_path = tmp_path / "config.yaml"
    config = _build_config(
        providers=[
            _provider("provider-alpha"),
            _provider("provider-beta", model="model-beta", fallback=True),
        ]
    )
    _write_config(config_path, config)
    client = make_test_client(config=config, config_path=config_path)

    response = client.post("/v1/routing", json={"policy": "Balanced"})

    assert response.status_code == 200
    assert client.get("/v1/providers/provider-beta").json()["fallback"] is True


def test_delete_provider_removes_from_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_config_runtime, "RouterOrchestrator", FakeOrchestrator)
    config_path = tmp_path / "config.yaml"
    config = _build_config(providers=[_provider("provider-alpha"), _provider("delete-me", model="model-del")])
    _write_config(config_path, config)
    client = make_test_client(config=config, config_path=config_path)

    response = client.delete("/v1/providers/delete-me")
    assert response.status_code == 200
    assert response.json()["status"] == "success"

    persisted = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert [p["name"] for p in persisted["providers"]] == ["provider-alpha"]

    # Deleting again is a 404.
    missing = client.delete("/v1/providers/delete-me")
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Provider 'delete-me' not found"


# A config file written by hand with an env-var placeholder for the API key.
# ``${SECRET_KEY}`` must survive provider edits untouched — the runtime holds
# the resolved value, but persistence must never leak it into the file.
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
  - name: provider-beta
    type: openai
    model: model-beta
    enabled: true
    metadata: {}
    settings:
      endpoint: https://beta.invalid/v1
      auth:
        scheme: none
        api_key: null
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


def test_provider_write_preserves_env_placeholder_for_untouched_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_config_runtime, "RouterOrchestrator", FakeOrchestrator)
    config_path = tmp_path / "config.yaml"
    # File on disk carries the ``${SECRET_KEY}`` placeholder on provider-alpha ...
    config_path.write_text(_RAW_CONFIG_WITH_PLACEHOLDER, encoding="utf-8")
    # ... while the running config holds the *resolved* secret in memory.
    config = _build_config(
        providers=[
            _provider("provider-alpha", api_key="resolved-super-secret"),
            _provider("provider-beta", model="model-beta"),
        ]
    )
    client = make_test_client(config=config, config_path=config_path)

    # Editing provider-beta must not disturb provider-alpha's placeholder.
    response = client.post("/v1/providers/provider-beta", json={"enabled": False})
    assert response.status_code == 200

    written = config_path.read_text(encoding="utf-8")
    persisted = yaml.safe_load(written)
    beta = next(p for p in persisted["providers"] if p["name"] == "provider-beta")
    assert beta["enabled"] is False
    # The placeholder is intact and the resolved secret never hit disk.
    assert "${SECRET_KEY}" in written
    assert "resolved-super-secret" not in written


def test_provider_update_without_settings_keeps_placeholder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_config_runtime, "RouterOrchestrator", FakeOrchestrator)
    config_path = tmp_path / "config.yaml"
    config_path.write_text(_RAW_CONFIG_WITH_PLACEHOLDER, encoding="utf-8")
    config = _build_config(
        providers=[
            _provider("provider-alpha", api_key="resolved-super-secret"),
            _provider("provider-beta", model="model-beta"),
        ]
    )
    client = make_test_client(config=config, config_path=config_path)

    # Toggling provider-alpha WITHOUT resending settings keeps its raw settings
    # (including the ${SECRET_KEY} placeholder) verbatim on disk.
    response = client.post("/v1/providers/provider-alpha", json={"enabled": False})
    assert response.status_code == 200

    written = config_path.read_text(encoding="utf-8")
    persisted = yaml.safe_load(written)
    alpha = next(p for p in persisted["providers"] if p["name"] == "provider-alpha")
    assert alpha["enabled"] is False
    assert alpha["settings"]["auth"]["api_key"] == "${SECRET_KEY}"
    assert "resolved-super-secret" not in written


def test_create_provider_stores_literal_placeholder_and_redacts_response(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_config_runtime, "RouterOrchestrator", FakeOrchestrator)
    # Env var is set, so the runtime resolves the placeholder to this secret.
    monkeypatch.setenv("OPENAI_API_KEY", "sk-live-xyz")
    config_path = tmp_path / "config.yaml"
    config = _build_config()
    _write_config(config_path, config)
    client = make_test_client(config=config, config_path=config_path)

    response = client.post(
        "/v1/providers/cloud",
        json={
            "type": "openai",
            "model": "gpt-4o",
            "settings": {"auth": {"scheme": "bearer", "api_key": "${OPENAI_API_KEY}"}},
        },
    )
    assert response.status_code == 200
    # Response redacts the resolved key ...
    assert response.json()["settings"]["auth"]["api_key"] == "***REDACTED***"

    # ... but the caller's ${VAR} placeholder is written verbatim (not resolved),
    # so the resolved secret never lands on disk.
    written = config_path.read_text(encoding="utf-8")
    assert "sk-live-xyz" not in written
    persisted = yaml.safe_load(written)
    created = next(p for p in persisted["providers"] if p["name"] == "cloud")
    assert created["settings"]["auth"]["api_key"] == "${OPENAI_API_KEY}"


def test_provider_write_is_atomic_and_leaves_no_temp_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_config_runtime, "RouterOrchestrator", FakeOrchestrator)
    config_path = tmp_path / "config.yaml"
    config = _build_config()
    _write_config(config_path, config)
    client = make_test_client(config=config, config_path=config_path)

    response = client.post("/v1/providers/atomic", json={"type": "openai", "model": "m"})
    assert response.status_code == 200
    # No stray temp file survives a successful atomic rename.
    assert list(tmp_path.glob("*.tmp")) == []
