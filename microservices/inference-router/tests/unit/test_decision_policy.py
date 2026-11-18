# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for decision policy loading and routing."""

import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

import pytest

from src.exceptions import RoutingError
from src.models import ChatCompletionMessage, ChatCompletionRequest, ChatCompletionRole
from src.providers.base import ProviderAdapter, ProviderMetadata
from src.rsd.engine.decision import DecisionEngine
from src.rsd.engine.policy import DecisionPolicy, load_decision_policies
from src.rsd.model_based.registry import EffectiveClassifier, ReconcileResult


class MockProvider(ProviderAdapter):
    """Minimal provider for decision policy tests."""

    async def chat(self, request):
        raise NotImplementedError()

    async def chat_stream(self, request):
        raise NotImplementedError()

    async def list_models(self):
        return [{"id": self.name}]


def _reconcile(requirements):
    classifier = SimpleNamespace(bundle=SimpleNamespace(zone_names=["local", "cloud"]))
    bindings = {
        requirement: EffectiveClassifier(
            classifier,
            requirement,
            (requirement[0], "v1"),
            "ready",
        )
        for requirement in requirements
    }
    return ReconcileResult(
        bindings,
        loaded=len(bindings),
        released=0,
        elapsed_ms=0.0,
    )


@pytest.mark.unit
def test_preload_classifiers_only_loads_active_policy_rules():
    registry = Mock()
    registry.reconcile.side_effect = lambda requirements: _reconcile(requirements)
    with patch("src.rsd.engine.decision.get_registry", return_value=registry):
        # Every strategy's rules are instantiated (ModelBasedRouting included), but
        # Balanced does not use ModelBasedRule, so nothing is loaded.
        assert DecisionEngine(policy_name="Balanced").preload_classifiers() == 0
        assert DecisionEngine(policy_name="ModelBased").preload_classifiers() == 1

    assert registry.reconcile.call_args_list == [
        call([]),
        call([("qwen35-2b", "v1")]),
    ]


@pytest.mark.unit
def test_preload_leaves_the_rule_eval_worker_free():
    # Runtimes are thread-safe, so loading runs on the caller's thread and the
    # rule-eval worker keeps serving the current engine's requests meanwhile.
    from src.rsd.engine.strategy import _RULE_EVAL_EXECUTOR

    seen = []

    def reconcile(requirements):
        seen.append(threading.current_thread().name)
        seen.append(_RULE_EVAL_EXECUTOR.submit(lambda: "served").result(timeout=5))
        return _reconcile(requirements)

    registry = Mock()
    registry.reconcile.side_effect = reconcile
    with patch("src.rsd.engine.decision.get_registry", return_value=registry):
        DecisionEngine(policy_name="ModelBased").preload_classifiers()
    assert not seen[0].startswith("rule-eval") and seen[1] == "served"


@pytest.mark.unit
def test_validate_against_providers_warns_on_missing_label(caplog):
    engine = DecisionEngine(policy_name="ModelBased")  # ModelBasedRouting: {0: local, 1: cloud}
    providers = [MockProvider("local-1", metadata=ProviderMetadata(labels=["local"]))]

    with caplog.at_level("WARNING"):
        engine.validate_against_providers(providers)

    warnings = [rec.message for rec in caplog.records if "routes to provider label" in rec.message]
    assert len(warnings) == 1 and "'cloud'" in warnings[0]


@pytest.mark.unit
def test_validate_against_providers_silent_when_all_labels_present(caplog):
    engine = DecisionEngine(policy_name="ModelBased")
    providers = [
        MockProvider("local-1", metadata=ProviderMetadata(labels=["local"])),
        MockProvider("cloud-1", metadata=ProviderMetadata(labels=["cloud"])),
    ]

    with caplog.at_level("WARNING"):
        engine.validate_against_providers(providers)

    assert not any("routes to provider label" in rec.message for rec in caplog.records)


@pytest.mark.unit
def test_load_decision_policies(tmp_path):
    """Policy YAML should load named ordered strategy lists."""
    policy_file = tmp_path / "policy.yaml"
    policy_file.write_text(
        "policies:\n"
        "  - name: TestPolicy\n"
        "    criterion: AllMatch\n"
        "    strategies:\n"
        "      - PlanningStrategy\n"
        "      - QueryComplexity\n"
    )

    policies = load_decision_policies(policy_file)

    assert policies["TestPolicy"].strategies == ["PlanningStrategy", "QueryComplexity"]
    assert policies["TestPolicy"].criterion == "AllMatch"


@pytest.mark.unit
def test_decision_engine_follows_policy_strategy_order():
    """DecisionEngine should try policy strategies in order until one matches."""
    request = ChatCompletionRequest(
        model="test-model",
        messages=[
            ChatCompletionMessage(
                role=ChatCompletionRole.USER,
                content="explain routing tradeoffs",
            )
        ],
    )
    providers = [
        MockProvider(
            "policy-provider",
            metadata=ProviderMetadata(capability={"complexity": 0.8}),
        )
    ]
    engine = DecisionEngine(policy_name="Balanced")

    decision = asyncio.run(engine.route(request, providers))

    assert decision.provider.name == "policy-provider"
    assert decision.metadata["policy_name"] == "Balanced"
    assert decision.metadata["criterion"] == "FirstMatch"
    assert decision.metadata["strategy_name"] == "ContextLengthQuality"


@pytest.mark.unit
def test_decision_engine_all_match_selects_common_provider():
    """AllMatch should select the first provider present in every strategy candidate list."""
    request = ChatCompletionRequest(
        model="test-model",
        messages=[
            ChatCompletionMessage(
                role=ChatCompletionRole.USER,
                content="help me plan routing tradeoffs",
            )
        ],
    )
    providers = [
        MockProvider(
            "context-only-provider",
            metadata=ProviderMetadata(labels=["general"], capability={"complexity": 0.4}),
        ),
        MockProvider(
            "shared-provider",
            metadata=ProviderMetadata(labels=["planning"], capability={"complexity": 0.8}),
        ),
    ]
    engine = DecisionEngine(policy_name="Balanced")
    engine.policy = DecisionPolicy(
        name="AllMatchPolicy",
        criterion="AllMatch",
        strategies=["Planning", "ContextLengthQuality"],
    )
    engine.strategy_names = engine.policy.strategies

    decision = asyncio.run(engine.route(request, providers))

    assert decision.provider.name == "shared-provider"
    assert decision.metadata["policy_name"] == "AllMatchPolicy"
    assert decision.metadata["criterion"] == "AllMatch"
    assert decision.metadata["strategy_names"] == [
        "Planning",
        "ContextLengthQuality",
    ]
    assert decision.metadata["candidate_counts"] == {
        "Planning": 1,
        "ContextLengthQuality": 2,
    }


@pytest.mark.unit
def test_fallback_decision_prefers_designated_provider():
    """When the policy matches nothing, route to the provider marked fallback."""
    request = ChatCompletionRequest(
        model="auto",
        messages=[
            ChatCompletionMessage(role=ChatCompletionRole.USER, content="hi")
        ],
    )
    providers = [
        MockProvider("primary"),
        MockProvider("backup", fallback=True),
    ]
    engine = DecisionEngine(policy_name="Balanced")

    decision = engine._fallback_decision(request, providers)

    assert decision.provider.name == "backup"
    assert decision.metadata["fallback"] is True
    assert decision.metadata["designated_fallback"] is True
    assert "designated fallback provider 'backup'" in decision.reason


@pytest.mark.unit
def test_fallback_decision_rejects_when_no_fallback_configured():
    """Absent any designated fallback, the request is rejected with a RoutingError."""
    request = ChatCompletionRequest(
        model="auto",
        messages=[
            ChatCompletionMessage(role=ChatCompletionRole.USER, content="hi")
        ],
    )
    providers = [MockProvider("primary"), MockProvider("secondary")]
    engine = DecisionEngine(policy_name="Balanced")

    with pytest.raises(RoutingError):
        engine._fallback_decision(request, providers)
