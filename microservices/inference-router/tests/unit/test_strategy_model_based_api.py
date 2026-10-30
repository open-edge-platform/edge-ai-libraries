# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Strategy API with a ModelBasedRule: versions from text, checks, prompt_info, policy switches.

The registry, the L1/L2/L3 checks and the classifier are the real ones; only
the backbone is a small deterministic fake, so no OpenVINO is needed. The
packaged default version is replaced by one packed on the fake backbone.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from src.api.v1 import _config_runtime
from src.config import ProviderConfig, RouterConfig, RoutingConfig, TelemetryConfig
from src.config.base import TelemetryBackendType
from src.exceptions import ConfigurationError
from src.rsd.engine.decision import DecisionEngine
from src.rsd.model_based import hard_version, settings
from src.rsd.model_based.format import read_rcv, write_rcv
from src.rsd.model_based.hard_version import build_hard_bundle
from src.rsd.model_based.registry import (
    ClassifierRegistry,
    set_registry_for_testing,
)

from ._api_contract_support import make_test_client
from ._fake_backbone import FakeRuntime

pytestmark = pytest.mark.unit

MODEL = "qwen35-2b"
TEXT = "Decide whether a small local model can answer the request."

STRATEGY_YAML = """\
strategies:
  - name: ModelBasedRouting
    rules:
      - type: ModelBasedRule
    provider_selector:
      label: {0: local, 1: cloud}
  - name: ZeroCost
    provider_selector:
      cost: 0
"""

POLICY_YAML = """\
policies:
  - name: ModelBased
    criterion: FirstMatch
    strategies: [ModelBasedRouting]
"""


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Workspace, IR dir, artifacts dir, a fake-backbone default version, a fresh registry."""
    monkeypatch.setenv("GATEWAY_WORKSPACE", str(tmp_path))
    (tmp_path / "strategy.yaml").write_text(STRATEGY_YAML, encoding="utf-8")
    (tmp_path / "policy.yaml").write_text(POLICY_YAML, encoding="utf-8")
    (tmp_path / "ir").mkdir()
    monkeypatch.setenv("IR_OV_MODEL", str(tmp_path / "ir"))
    monkeypatch.setenv("IR_ARTIFACTS_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setenv("IR_DEVICE", "CPU")
    monkeypatch.delenv("IR_BACKBONE", raising=False)

    runtime = FakeRuntime()
    packaged = tmp_path / "prompts"
    (packaged / MODEL).mkdir(parents=True)
    write_rcv(
        packaged / MODEL / "v1.rcv",
        build_hard_bundle(
            runtime, model=MODEL, version="v1", text="default", labels=["local", "cloud"],
            threshold=0.5,
        ),
    )
    monkeypatch.setattr(settings, "_DEFAULT_PROMPT_DIR", packaged)

    registry = ClassifierRegistry(
        runtime_factory=lambda path, device: runtime, tokenizer_factory=lambda path: runtime
    )
    set_registry_for_testing(registry)
    config = RouterConfig(
        providers=[ProviderConfig(name="p", type="openai", model="m", enabled=True)],
        routing=RoutingConfig(policy="ModelBased"),
        telemetry=TelemetryConfig(backend=TelemetryBackendType.MEMORY, enabled=True),
    )
    client = make_test_client(config=config, config_path=tmp_path / "config.yaml")
    yield client, tmp_path, registry
    set_registry_for_testing(None)


def _stored(tmp_path: Path, name: str) -> dict:
    doc = yaml.safe_load((tmp_path / "strategy.yaml").read_text(encoding="utf-8"))
    return next(s for s in doc["strategies"] if s["name"] == name)


def _versions(tmp_path: Path) -> list[str]:
    directory = tmp_path / "artifacts" / MODEL
    return sorted(p.name for p in directory.glob("*.rcv")) if directory.exists() else []


def _text_body(selector=None, **param):
    return {
        "rules": [{"type": "ModelBasedRule", "param": {"text": TEXT, **param}}],
        "provider_selector": {"label": selector or {"0": "local", "1": "cloud"}},
    }


def test_text_packs_a_hard_version_and_stores_only_model_and_version(env):
    client, tmp_path, _ = env
    response = client.post("/v1/strategies/Triage", json=_text_body(note="first try"))

    assert response.status_code == 200, response.text
    result = response.json()["prompt_result"]
    assert result["version"] == "v2"  # after the packaged v1
    assert (result["kind"], result["created"], result["active"]) == ("hard", True, False)
    assert result["previous"] is None
    assert result["validation"]["L3_min_cos"] == pytest.approx(1.0)
    assert result["content_hash"].startswith("sha256:")
    assert _stored(tmp_path, "Triage")["rules"][0]["param"] == {"model": MODEL, "version": "v2"}

    bundle = read_rcv(tmp_path / "artifacts" / MODEL / "v2.rcv")
    assert bundle.kind == "hard" and bundle.zone_names == ["local", "cloud"]
    assert bundle.prompt.startswith(TEXT) and bundle.prompt.endswith("A: local\nB: cloud")
    assert bundle.meta["label_tokens"] == ["A", "B"]
    assert (bundle.threshold, bundle.meta["note"]) == (pytest.approx(0.7), "first try")


def test_same_content_reuses_its_version(env):
    client, tmp_path, _ = env
    first = client.post("/v1/strategies/Triage", json=_text_body()).json()["prompt_result"]
    again = client.post("/v1/strategies/Other", json=_text_body()).json()["prompt_result"]
    assert (again["version"], again["created"]) == (first["version"], False)
    assert _versions(tmp_path) == ["v2.rcv"]

    changed = client.post("/v1/strategies/Triage", json=_text_body(threshold=0.9)).json()
    assert changed["prompt_result"]["version"] == "v3"
    assert changed["prompt_result"]["previous"] == "v2"
    assert _versions(tmp_path) == ["v2.rcv", "v3.rcv"]


def test_explicit_labels_name_the_categories_in_zone_order(env):
    client, tmp_path, _ = env
    body = _text_body(
        selector={"0": "local", "1": "cloud", "2": "local"}, labels=["easy", "hard", "plan"]
    )
    assert client.post("/v1/strategies/Triage", json=body).status_code == 200
    bundle = read_rcv(tmp_path / "artifacts" / MODEL / "v2.rcv")
    assert bundle.zone_names == ["easy", "hard", "plan"]


def test_categories_from_the_selector_need_position_keys(env):
    client, tmp_path, _ = env
    response = client.post(
        "/v1/strategies/Triage", json=_text_body(selector={"0": "local", "2": "cloud"})
    )
    assert response.status_code == 400
    assert "keyed 0..N-1" in response.json()["detail"]
    assert _versions(tmp_path) == []


@pytest.mark.parametrize(
    "param,match",
    [
        ({"text": TEXT, "version": "v1"}, "mutually exclusive"),
        ({"text": TEXT, "prompt_file": "p.txt"}, "mutually exclusive"),
        ({"version": "v1", "note": "x"}, "'note' applies only with 'text'"),
        ({"text": "  "}, "non-empty string"),
        ({"text": TEXT, "threshold": 2}, "between 0 and 1"),
        ({"text": TEXT, "labels": ["a", "a"]}, "distinct"),
        ({"version": "latest"}, "'default' or vN"),
        ({"version": "v1", "temperature": 0}, "Invalid parameters for rule 'ModelBasedRule'"),
    ],
)
def test_invalid_params_are_400_and_change_nothing(env, param, match):
    client, tmp_path, _ = env
    before = (tmp_path / "strategy.yaml").read_bytes()
    response = client.post(
        "/v1/strategies/Triage",
        json={
            "rules": [{"type": "ModelBasedRule", "param": param}],
            "provider_selector": {"label": {"0": "local", "1": "cloud"}},
        },
    )
    assert response.status_code == 400, response.text
    assert match in response.json()["detail"]
    assert (tmp_path / "strategy.yaml").read_bytes() == before
    assert _versions(tmp_path) == []


@pytest.mark.parametrize(
    "param", [{"model": "qwen9-100b", "text": TEXT}, {"model": "qwen9-100b"}, {"version": "v9"}]
)
def test_unknown_model_or_version_is_404(env, param):
    client, _, _ = env
    response = client.post(
        "/v1/strategies/Triage",
        json={
            "rules": [{"type": "ModelBasedRule", "param": param}],
            "provider_selector": {"label": {"0": "local", "1": "cloud"}},
        },
    )
    assert response.status_code == 404, response.text


def test_backbone_without_an_ir_is_422(env, monkeypatch):
    client, tmp_path, _ = env
    monkeypatch.delenv("IR_OV_MODEL")
    response = client.post("/v1/strategies/Triage", json=_text_body())
    assert response.status_code == 422
    assert "IR_OV_MODEL" in response.json()["detail"]
    assert _versions(tmp_path) == []


def test_failed_check_is_422_and_writes_nothing(env, monkeypatch):
    client, tmp_path, _ = env
    before = (tmp_path / "strategy.yaml").read_bytes()
    real = hard_version.fingerprint_rows  # pack a fingerprint the backbone cannot match
    monkeypatch.setattr(hard_version, "fingerprint_rows", lambda rt, probes: -real(rt, probes))
    response = client.post("/v1/strategies/Triage", json=_text_body())
    assert response.status_code == 422
    assert "L3" in response.json()["detail"]
    assert (tmp_path / "strategy.yaml").read_bytes() == before
    assert _versions(tmp_path) == []


def test_failed_activation_removes_the_new_version(env):
    client, tmp_path, _ = env
    before = (tmp_path / "strategy.yaml").read_bytes()
    with patch.object(
        DecisionEngine, "from_config",
        side_effect=ConfigurationError("policy 'X' references unknown strategy 'Y'"),
    ):
        response = client.post("/v1/strategies/Triage", json=_text_body())
    assert response.status_code == 400
    assert (tmp_path / "strategy.yaml").read_bytes() == before
    assert _versions(tmp_path) == []


def test_active_strategy_switches_and_reports_the_reconcile(env):
    client, _, registry = env
    response = client.post("/v1/strategies/ModelBasedRouting", json=_text_body())

    assert response.status_code == 200, response.text
    body = response.json()
    result = body["prompt_result"]
    assert (result["active"], result["previous"], result["version"]) == (True, "v1", "v2")
    assert result["warmup_ms"] is not None
    assert "qwen35-2b/v2" in body["reconcile"]["loaded"]
    assert (MODEL, "v2") in registry.published()


def test_version_reference_outside_the_active_policy_checks_format_l1_and_l2(env):
    client, _, _ = env
    response = client.post(
        "/v1/strategies/Pinned",
        json={
            "rules": [{"type": "ModelBasedRule", "param": {"version": "default"}}],
            "provider_selector": {"label": {"0": "local", "1": "cloud"}},
        },
    )
    assert response.status_code == 200, response.text
    result = response.json()["prompt_result"]
    assert result["version"] == "v1" and result["warmup_ms"] is None
    assert result["validation"] == {
        "format": "ok", "backbone": MODEL, "model_name": "Qwen/Qwen3.5-2B", "L1": "ok", "L2": "ok"
    }  # no L3: the backbone is not compiled for a strategy outside the active policy


def test_prompt_file_rules_and_other_strategies_have_no_prompt_result(env):
    client, _, _ = env
    plain = client.post("/v1/strategies/Cheap", json={"provider_selector": {"cost": 0}})
    assert plain.status_code == 200 and "prompt_result" not in plain.json()
    multi = client.post(
        "/v1/strategies/Multi",
        json={
            "rules": [{"type": "ModelBasedRule", "param": {"prompt_file": "p.txt"}}],
            "provider_selector": {"label": {"0": "local", "1": "cloud"}},
        },
    )
    assert multi.status_code == 200 and "prompt_result" not in multi.json()


def test_text_in_several_model_based_rules_is_400(env):
    client, tmp_path, _ = env
    rule = {"type": "ModelBasedRule", "param": {"text": TEXT}}
    response = client.post(
        "/v1/strategies/Triage",
        json={"rules": [rule, rule], "provider_selector": {"label": {"0": "local", "1": "cloud"}}},
    )
    assert response.status_code == 400
    assert _versions(tmp_path) == []


# ---------------------------------------------------------------------------
# GET: prompt_info and status
# ---------------------------------------------------------------------------


def _info(client, name: str) -> dict:
    body = client.get(f"/v1/strategies/{name}").json()
    (rule,) = [r for r in body["rules"] if r["type"] == "ModelBasedRule"]
    return rule["prompt_info"]


def test_get_shows_the_hard_prompt_as_written(env):
    client, _, _ = env
    client.post("/v1/strategies/Triage", json=_text_body(note="first try", threshold=0.6))
    body = client.get("/v1/strategies/Triage").json()
    info = next(
        rule["prompt_info"] for rule in body["rules"] if rule["type"] == "ModelBasedRule"
    )
    assert info["kind"] == "hard"
    assert (info["status"], info["effective"]) == ("unverified", None)  # not in the policy
    models = {item["model"]: item for item in body["classifier_options"]}
    assert set(models) == set(settings.KNOWN_BACKBONES)
    assert [version["version"] for version in models[MODEL]["versions"]] == ["v1", "v2"]
    v1, v2 = models[MODEL]["versions"]
    assert v1 == {"version": "v1", "kind": "hard", "text": "default"}
    assert v2 == {"version": "v2", "kind": "hard", "text": TEXT}


def test_get_result_edited_and_posted_back_reuses_the_version(env):
    client, tmp_path, _ = env
    client.post("/v1/strategies/Triage", json=_text_body())
    body = client.get("/v1/strategies/Triage").json()
    rule = body["rules"][0]
    model = next(option for option in body["classifier_options"] if option["model"] == MODEL)
    hard = next(version for version in model["versions"] if version["version"] == "v2")
    rule["param"] = {"text": hard["text"]}  # edit nothing, post back
    response = client.post("/v1/strategies/Triage", json=body)
    assert response.status_code == 200, response.text
    assert response.json()["prompt_result"]["created"] is False
    assert "prompt_info" not in _stored(tmp_path, "Triage")["rules"][0]
    assert _versions(tmp_path) == ["v2.rcv"]


def test_get_reports_an_active_version_as_ok(env):
    client, _, _ = env
    client.post("/v1/strategies/ModelBasedRouting", json=_text_body())  # activates v2
    info = _info(client, "ModelBasedRouting")
    assert (info["status"], info["effective"], info["reason"]) == ("ok", "v2", None)


def test_get_reports_a_degraded_version_and_its_fallback(env):
    client, tmp_path, registry = env
    doc = yaml.safe_load((tmp_path / "strategy.yaml").read_text(encoding="utf-8"))
    doc["strategies"][0]["rules"][0]["param"] = {"version": "v9"}  # edited by hand
    (tmp_path / "strategy.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")
    registry.effective(MODEL, "v9")  # what startup does: fall back to the default
    info = _info(client, "ModelBasedRouting")
    assert (info["status"], info["effective"]) == ("degraded", "v1")
    assert "v9" in info["reason"]


def test_get_lists_prompt_info_and_describes_prompt_file_rules(env):
    client, _, _ = env
    client.post(
        "/v1/strategies/Multi",
        json={
            "rules": [{"type": "ModelBasedRule", "param": {"prompt_file": "p.txt"}}],
            "provider_selector": {"label": {"0": "local", "1": "cloud"}},
        },
    )
    listed = {s["name"]: s for s in client.get("/v1/strategies").json()}
    assert "prompt_info" not in str(listed["ZeroCost"])
    assert "classifier_options" not in str(listed)
    multi = listed["Multi"]["rules"][0]["prompt_info"]
    assert (multi["kind"], multi["status"]) == ("prompt_file", "unverified")
    default = listed["ModelBasedRouting"]["rules"][0]["prompt_info"]
    assert (default["kind"], default["status"]) == ("hard", "ok")


def test_version_outside_the_active_policy_failing_l2_is_422(env):
    client, _, registry = env

    class OtherTokenizer(FakeRuntime):
        def encode(self, text):
            return super().encode(text) + 1

    registry._tokenizer_factory = lambda path: OtherTokenizer()
    response = client.post(
        "/v1/strategies/Pinned",
        json={
            "rules": [{"type": "ModelBasedRule", "param": {"version": "default"}}],
            "provider_selector": {"label": {"0": "local", "1": "cloud"}},
        },
    )
    assert response.status_code == 422
    assert "L2" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Policy switches reconcile classifiers
# ---------------------------------------------------------------------------


class _NoopOrchestrator:
    """Stands in for the rebuilt router: the switch itself is not under test."""

    def __init__(self, config, telemetry=None):
        self.config = config
        self.plugin_manager = None

    async def initialize(self):
        return None

    def shutdown(self):
        return None


def _add_pinned_policy(tmp_path: Path, version: str) -> None:
    strategies = yaml.safe_load((tmp_path / "strategy.yaml").read_text(encoding="utf-8"))
    strategies["strategies"].append(
        {
            "name": "Pinned",
            "rules": [{"type": "ModelBasedRule", "param": {"version": version}}],
            "provider_selector": {"label": {0: "local", 1: "cloud"}},
        }
    )
    (tmp_path / "strategy.yaml").write_text(yaml.safe_dump(strategies), encoding="utf-8")
    policies = yaml.safe_load((tmp_path / "policy.yaml").read_text(encoding="utf-8"))
    policies["policies"].append({"name": "PinnedPolicy", "criterion": "FirstMatch",
                                 "strategies": ["Pinned"]})
    (tmp_path / "policy.yaml").write_text(yaml.safe_dump(policies), encoding="utf-8")


def test_switching_to_a_policy_whose_version_fails_still_applies_and_degrades(env, monkeypatch):
    """IR_STRICT is gone: switching to a policy whose classifier version is
    broken applies the switch instead of rejecting it with 422. The broken
    version degrades -- at activation time it falls back to the packaged
    default, and requests without even that go to the fallback provider; the
    registry-level tests cover that chain in isolation."""
    client, tmp_path, registry = env
    monkeypatch.setattr(_config_runtime, "RouterOrchestrator", _NoopOrchestrator)
    bundle = build_hard_bundle(
        FakeRuntime(), model=MODEL, version="v2", text="x", labels=["local", "cloud"],
        threshold=0.7,
    )
    broken = hard_version.ClassifierBundle(
        kind=bundle.kind, prompt=bundle.prompt, head_weight=bundle.head_weight,
        head_bias=bundle.head_bias, fp_hidden=-bundle.fp_hidden, meta=dict(bundle.meta),
    )  # a fingerprint this backbone cannot match
    (tmp_path / "artifacts" / MODEL).mkdir(parents=True)
    write_rcv(tmp_path / "artifacts" / MODEL / "v2.rcv", broken)
    _add_pinned_policy(tmp_path, "v2")

    response = client.post("/v1/routing", json={"policy": "PinnedPolicy"})
    assert response.status_code == 200
    assert client.get("/v1/routing").json()["policy"] == "PinnedPolicy"

    # the noop orchestrator never loads anything: the version stays unloaded,
    # a real activation (or a request-time miss) is what surfaces the degrade
    assert registry.status("qwen35-2b", "v2") is None

def test_switching_policies_returns_the_selected_policy(env, monkeypatch):
    client, tmp_path, _ = env
    monkeypatch.setattr(_config_runtime, "RouterOrchestrator", _NoopOrchestrator)
    _add_pinned_policy(tmp_path, "default")
    response = client.post("/v1/routing", json={"policy": "PinnedPolicy"})
    assert response.status_code == 200, response.text
    assert response.json() == {"policy": "PinnedPolicy"}


def test_changing_the_active_policy_returns_the_policy(env):
    client, _, _ = env
    response = client.post(
        "/v1/policies/ModelBased",
        json={"criterion": "FirstMatch", "strategies": ["ModelBasedRouting", "ZeroCost"]},
    )
    assert response.status_code == 200, response.text
    assert response.json() == {
        "name": "ModelBased",
        "criterion": "FirstMatch",
        "strategies": ["ModelBasedRouting", "ZeroCost"],
    }
    other = client.post(
        "/v1/policies/Spare", json={"criterion": "FirstMatch", "strategies": ["ZeroCost"]}
    )
    assert other.status_code == 200
