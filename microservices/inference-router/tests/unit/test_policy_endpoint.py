# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the /v1/policies endpoints.

All endpoints target <workspace>/policy.yaml, which must already exist. Writes
are applied immediately by rebuilding the router's DecisionEngine. Tests point
``GATEWAY_WORKSPACE`` at a tmp dir so API operations land there.
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
  - name: CostFirst
    criterion: FirstMatch
    strategies: [ZeroCost]
"""


def _seed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    active_policy: str | None = "Balanced",
    write_policy: bool = True,
):
    monkeypatch.setenv("GATEWAY_WORKSPACE", str(tmp_path))
    (tmp_path / "strategy.yaml").write_text(STRATEGY_YAML, encoding="utf-8")
    if write_policy:
        (tmp_path / "policy.yaml").write_text(POLICY_YAML, encoding="utf-8")
    config = RouterConfig(
        providers=[ProviderConfig(name="p", type="openai", model="m", enabled=True)],
        routing=RoutingConfig(policy=active_policy),
        telemetry=TelemetryConfig(backend="memory", enabled=True),
    )
    return make_test_client(config=config, config_path=tmp_path / "config.yaml")


def _persisted(tmp_path: Path) -> list[dict]:
    doc = yaml.safe_load((tmp_path / "policy.yaml").read_text(encoding="utf-8"))
    return doc["policies"]


def test_list_policies_returns_bare_array(tmp_path, monkeypatch):
    client = _seed(tmp_path, monkeypatch)
    response = client.get("/v1/policies")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert {p["name"] for p in body} == {"Balanced", "CostFirst"}


def test_policy_yaml_policies_must_be_list_and_is_not_overwritten(tmp_path, monkeypatch):
    client = _seed(tmp_path, monkeypatch, active_policy=None)
    bad_yaml = "policies: {bad: shape}\n"
    (tmp_path / "policy.yaml").write_text(bad_yaml, encoding="utf-8")

    listed = client.get("/v1/policies")
    assert listed.status_code == 500
    assert "'policies' list" in listed.json()["detail"]

    created = client.post("/v1/policies/Fast", json={"strategies": ["Planning"]})
    assert created.status_code == 500
    assert "'policies' list" in created.json()["detail"]
    assert (tmp_path / "policy.yaml").read_text(encoding="utf-8") == bad_yaml


def test_get_policy_found_and_missing(tmp_path, monkeypatch):
    client = _seed(tmp_path, monkeypatch)

    found = client.get("/v1/policies/Balanced")
    assert found.status_code == 200
    assert found.json() == {
        "name": "Balanced",
        "criterion": "FirstMatch",
        "strategies": ["Planning"],
    }

    missing = client.get("/v1/policies/Nope")
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Policy 'Nope' not found"


def test_get_policy_fills_default_criterion(tmp_path, monkeypatch):
    # A hand-written policy that omits ``criterion`` is returned with the
    # runtime default (FirstMatch), matching the documented object shape.
    monkeypatch.setenv("GATEWAY_WORKSPACE", str(tmp_path))
    (tmp_path / "strategy.yaml").write_text(STRATEGY_YAML, encoding="utf-8")
    (tmp_path / "policy.yaml").write_text(
        "policies:\n  - name: Bare\n    strategies: [Planning]\n", encoding="utf-8"
    )
    config = RouterConfig(
        providers=[ProviderConfig(name="p", type="openai", model="m", enabled=True)],
        routing=RoutingConfig(policy="Bare"),
        telemetry=TelemetryConfig(backend="memory", enabled=True),
    )
    client = make_test_client(config=config, config_path=tmp_path / "config.yaml")

    body = client.get("/v1/policies/Bare").json()
    assert body == {"name": "Bare", "criterion": "FirstMatch", "strategies": ["Planning"]}


def test_create_policy_persists_and_rebuilds_engine(tmp_path, monkeypatch):
    client = _seed(tmp_path, monkeypatch)

    response = client.post(
        "/v1/policies/Fast",
        json={"criterion": "AllMatch", "strategies": ["Planning", "ZeroCost"]},
    )
    assert response.status_code == 200
    assert response.json() == {
        "name": "Fast",
        "criterion": "AllMatch",
        "strategies": ["Planning", "ZeroCost"],
    }

    names = [p["name"] for p in _persisted(tmp_path)]
    assert names == ["Balanced", "CostFirst", "Fast"]

    # Immediate effect: the router's DecisionEngine was rebuilt in place.
    engine = client.app.state.router.decision_engine
    assert isinstance(engine, DecisionEngine)
    assert "Fast" in engine.policy_definitions


def test_create_policy_defaults_criterion_to_first_match(tmp_path, monkeypatch):
    client = _seed(tmp_path, monkeypatch)
    response = client.post("/v1/policies/Fast", json={"strategies": ["Planning"]})
    assert response.status_code == 200
    assert response.json()["criterion"] == "FirstMatch"


def test_create_policy_ignores_body_name(tmp_path, monkeypatch):
    client = _seed(tmp_path, monkeypatch)
    response = client.post(
        "/v1/policies/Fast", json={"name": "OTHER", "strategies": ["Planning"]}
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Fast"
    assert [p["name"] for p in _persisted(tmp_path)] == ["Balanced", "CostFirst", "Fast"]


def test_update_existing_policy_replaces_wholesale(tmp_path, monkeypatch):
    client = _seed(tmp_path, monkeypatch)
    response = client.post("/v1/policies/CostFirst", json={"strategies": ["Planning"]})
    assert response.status_code == 200

    cost_first = next(p for p in _persisted(tmp_path) if p["name"] == "CostFirst")
    assert cost_first["strategies"] == ["Planning"]


def test_create_policy_unknown_strategy_is_400_and_no_write(tmp_path, monkeypatch):
    client = _seed(tmp_path, monkeypatch)
    response = client.post("/v1/policies/Bad", json={"strategies": ["Planing"]})
    assert response.status_code == 400
    assert "unknown strategy" in response.json()["detail"]
    # Nothing was written.
    assert [p["name"] for p in _persisted(tmp_path)] == ["Balanced", "CostFirst"]


def test_create_policy_invalid_criterion_is_400(tmp_path, monkeypatch):
    client = _seed(tmp_path, monkeypatch)
    response = client.post(
        "/v1/policies/Bad", json={"criterion": "Whatever", "strategies": ["Planning"]}
    )
    assert response.status_code == 400


def test_create_policy_empty_strategies_is_400(tmp_path, monkeypatch):
    client = _seed(tmp_path, monkeypatch)
    response = client.post("/v1/policies/Bad", json={"strategies": []})
    assert response.status_code == 400


def test_post_policy_missing_workspace_file_is_400(tmp_path, monkeypatch):
    client = _seed(tmp_path, monkeypatch, write_policy=False)
    response = client.post("/v1/policies/Fast", json={"strategies": ["Planning"]})
    assert response.status_code == 400
    assert "not found" in response.json()["detail"]


def test_get_policy_missing_workspace_file_is_400(tmp_path, monkeypatch):
    client = _seed(tmp_path, monkeypatch, write_policy=False)

    listed = client.get("/v1/policies")
    assert listed.status_code == 400
    assert "not found" in listed.json()["detail"]

    fetched = client.get("/v1/policies/Balanced")
    assert fetched.status_code == 400
    assert "not found" in fetched.json()["detail"]


def test_delete_policy_removes_and_persists(tmp_path, monkeypatch):
    client = _seed(tmp_path, monkeypatch)
    response = client.delete("/v1/policies/CostFirst")
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert [p["name"] for p in _persisted(tmp_path)] == ["Balanced"]

    # Deleting again is a 404.
    again = client.delete("/v1/policies/CostFirst")
    assert again.status_code == 404


def test_delete_active_policy_is_409(tmp_path, monkeypatch):
    client = _seed(tmp_path, monkeypatch, active_policy="Balanced")
    response = client.delete("/v1/policies/Balanced")
    assert response.status_code == 409
    assert "active routing policy" in response.json()["detail"]
    # Untouched.
    assert [p["name"] for p in _persisted(tmp_path)] == ["Balanced", "CostFirst"]


def test_delete_policy_missing_workspace_file_is_400(tmp_path, monkeypatch):
    client = _seed(tmp_path, monkeypatch, write_policy=False)
    response = client.delete("/v1/policies/Balanced")
    assert response.status_code == 400
