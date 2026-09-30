# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the /v1/strategies endpoints.

All endpoints target <workspace>/strategy.yaml, which must already exist.
Writes are applied immediately by rebuilding the router's DecisionEngine. Tests
point ``GATEWAY_WORKSPACE`` at a tmp dir so API operations land there.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.config import ProviderConfig, RouterConfig, RoutingConfig, TelemetryConfig
from src.rsd.decision import DecisionEngine
from ._api_contract_support import make_test_client


pytestmark = pytest.mark.unit


STRATEGY_YAML = """\
strategies:
  - name: Planning
    description: "Planning intent."
    rules:
      - type: MessageContentRule
        param:
          pattern: plan
          roles: [user]
    provider_selector:
      label: planning
  - name: ZeroCost
    description: "No-cost provider."
    provider_selector:
      cost: 0
"""

POLICY_YAML = """\
policies:
  - name: Balanced
    criterion: FirstMatch
    strategies: [Planning]
"""


def _seed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    write_strategy: bool = True,
    write_policy: bool = True,
):
    monkeypatch.setenv("GATEWAY_WORKSPACE", str(tmp_path))
    if write_strategy:
        (tmp_path / "strategy.yaml").write_text(STRATEGY_YAML, encoding="utf-8")
    if write_policy:
        (tmp_path / "policy.yaml").write_text(POLICY_YAML, encoding="utf-8")
    config = RouterConfig(
        providers=[ProviderConfig(name="p", type="openai", model="m", enabled=True)],
        routing=RoutingConfig(policy="Balanced"),
        telemetry=TelemetryConfig(backend="memory", enabled=True),
    )
    return make_test_client(config=config, config_path=tmp_path / "config.yaml")


def _persisted(tmp_path: Path) -> list[dict]:
    doc = yaml.safe_load((tmp_path / "strategy.yaml").read_text(encoding="utf-8"))
    return doc["strategies"]


def test_list_strategies_returns_bare_array(tmp_path, monkeypatch):
    client = _seed(tmp_path, monkeypatch)
    response = client.get("/v1/strategies")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert {s["name"] for s in body} == {"Planning", "ZeroCost"}


def test_strategy_yaml_strategies_must_be_list_and_is_not_overwritten(
    tmp_path, monkeypatch
):
    client = _seed(tmp_path, monkeypatch)
    bad_yaml = "strategies: {bad: shape}\n"
    (tmp_path / "strategy.yaml").write_text(bad_yaml, encoding="utf-8")

    listed = client.get("/v1/strategies")
    assert listed.status_code == 500
    assert "'strategies' list" in listed.json()["detail"]

    created = client.post(
        "/v1/strategies/Cloudy", json={"provider_selector": {"cost": 0}}
    )
    assert created.status_code == 500
    assert "'strategies' list" in created.json()["detail"]
    assert (tmp_path / "strategy.yaml").read_text(encoding="utf-8") == bad_yaml


def test_get_strategy_found_and_missing(tmp_path, monkeypatch):
    client = _seed(tmp_path, monkeypatch)

    found = client.get("/v1/strategies/ZeroCost")
    assert found.status_code == 200
    assert found.json()["name"] == "ZeroCost"
    assert found.json()["provider_selector"] == {"cost": 0}

    missing = client.get("/v1/strategies/Nope")
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Strategy 'Nope' not found"


def test_create_strategy_persists_and_rebuilds_engine(tmp_path, monkeypatch):
    client = _seed(tmp_path, monkeypatch)

    response = client.post(
        "/v1/strategies/Cloudy",
        json={
            "description": "Cloud tier.",
            "provider_selector": {"label": "cloud", "capability": {"complexity": 0.7}},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Cloudy"
    assert body["provider_selector"]["label"] == "cloud"

    names = [s["name"] for s in _persisted(tmp_path)]
    assert names == ["Planning", "ZeroCost", "Cloudy"]

    # Immediate effect: the router's DecisionEngine was rebuilt in place.
    engine = client.app.state.router.decision_engine
    assert isinstance(engine, DecisionEngine)
    assert "Cloudy" in engine.strategy_definitions


def test_create_strategy_ignores_body_name(tmp_path, monkeypatch):
    client = _seed(tmp_path, monkeypatch)
    response = client.post(
        "/v1/strategies/Cloudy",
        json={"name": "OTHER", "provider_selector": {"cost": 1}},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Cloudy"


def test_create_strategy_drops_unknown_keys(tmp_path, monkeypatch):
    # Unknown keys pass the builder (it ignores them) but must not be persisted.
    client = _seed(tmp_path, monkeypatch)
    response = client.post(
        "/v1/strategies/Cloudy",
        json={"provider_selector": {"cost": 0}, "typoField": 123},
    )
    assert response.status_code == 200
    assert "typoField" not in response.json()
    stored = next(s for s in _persisted(tmp_path) if s["name"] == "Cloudy")
    assert "typoField" not in stored


def test_update_existing_strategy_replaces_wholesale(tmp_path, monkeypatch):
    client = _seed(tmp_path, monkeypatch)
    response = client.post(
        "/v1/strategies/ZeroCost",
        json={"description": "changed", "provider_selector": {"cost": 5}},
    )
    assert response.status_code == 200
    zero = next(s for s in _persisted(tmp_path) if s["name"] == "ZeroCost")
    assert zero["description"] == "changed"
    assert zero["provider_selector"] == {"cost": 5}


def test_create_strategy_missing_provider_selector_is_400(tmp_path, monkeypatch):
    client = _seed(tmp_path, monkeypatch)
    response = client.post("/v1/strategies/Bad", json={"description": "no selector"})
    assert response.status_code == 400
    assert [s["name"] for s in _persisted(tmp_path)] == ["Planning", "ZeroCost"]


def test_get_strategy_fills_default_shape(tmp_path, monkeypatch):
    # ZeroCost omits rules/sort/require_healthy/limit; GET fills the full shape.
    client = _seed(tmp_path, monkeypatch)
    body = client.get("/v1/strategies/ZeroCost").json()
    assert body == {
        "name": "ZeroCost",
        "description": "No-cost provider.",
        "rules": [],
        "provider_selector": {"cost": 0},
        "sort": [],
        "require_healthy": False,
        "limit": None,
    }


def test_create_strategy_unknown_rule_type_is_400(tmp_path, monkeypatch):
    client = _seed(tmp_path, monkeypatch)
    response = client.post(
        "/v1/strategies/Bad",
        json={
            "rules": [{"type": "NotARule", "param": {}}],
            "provider_selector": {"cost": 0},
        },
    )
    assert response.status_code == 400
    assert "NotARule" in response.json()["detail"]


def test_post_strategy_missing_workspace_file_is_400(tmp_path, monkeypatch):
    client = _seed(tmp_path, monkeypatch, write_strategy=False)
    response = client.post("/v1/strategies/Cloudy", json={"provider_selector": {"cost": 0}})
    assert response.status_code == 400
    assert "not found" in response.json()["detail"]


def test_get_strategy_missing_workspace_file_is_400(tmp_path, monkeypatch):
    client = _seed(tmp_path, monkeypatch, write_strategy=False)

    listed = client.get("/v1/strategies")
    assert listed.status_code == 400
    assert "not found" in listed.json()["detail"]

    fetched = client.get("/v1/strategies/Planning")
    assert fetched.status_code == 400
    assert "not found" in fetched.json()["detail"]


def test_delete_unreferenced_strategy_succeeds(tmp_path, monkeypatch):
    client = _seed(tmp_path, monkeypatch)
    response = client.delete("/v1/strategies/ZeroCost")
    assert response.status_code == 200
    assert [s["name"] for s in _persisted(tmp_path)] == ["Planning"]

    again = client.delete("/v1/strategies/ZeroCost")
    assert again.status_code == 404


def test_delete_referenced_strategy_is_409(tmp_path, monkeypatch):
    # Planning is referenced by the Balanced policy.
    client = _seed(tmp_path, monkeypatch)
    response = client.delete("/v1/strategies/Planning")
    assert response.status_code == 409
    assert "referenced by policies: Balanced" in response.json()["detail"]
    assert [s["name"] for s in _persisted(tmp_path)] == ["Planning", "ZeroCost"]


def test_delete_referenced_strategy_skips_nameless_policy(tmp_path, monkeypatch):
    # A policy entry lacking 'name' that references the strategy must not crash
    # the 409 message assembly (None in ', '.join -> TypeError -> 500).
    monkeypatch.setenv("GATEWAY_WORKSPACE", str(tmp_path))
    (tmp_path / "strategy.yaml").write_text(STRATEGY_YAML, encoding="utf-8")
    (tmp_path / "policy.yaml").write_text(
        "policies:\n"
        "  - strategies: [Planning]\n"  # nameless, references Planning
        "  - name: Named\n    strategies: [Planning]\n",
        encoding="utf-8",
    )
    config = RouterConfig(
        providers=[ProviderConfig(name="p", type="openai", model="m", enabled=True)],
        routing=RoutingConfig(policy=None),
        telemetry=TelemetryConfig(backend="memory", enabled=True),
    )
    client = make_test_client(config=config, config_path=tmp_path / "config.yaml")

    response = client.delete("/v1/strategies/Planning")
    assert response.status_code == 409
    assert "Named" in response.json()["detail"]


def test_delete_strategy_missing_workspace_file_is_400(tmp_path, monkeypatch):
    client = _seed(tmp_path, monkeypatch, write_strategy=False)
    response = client.delete("/v1/strategies/Planning")
    assert response.status_code == 400
