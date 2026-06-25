# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for decision policy loading and routing."""

import pytest

from src.models import ChatCompletionMessage, ChatCompletionRequest, ChatCompletionRole
from src.providers.base import ProviderAdapter, ProviderMetadata
from src.rsd.decision import DecisionEngine
from src.rsd.policy import DecisionPolicy, load_decision_policies


class MockProvider(ProviderAdapter):
    """Minimal provider for decision policy tests."""

    async def chat(self, request):
        raise NotImplementedError()

    async def chat_stream(self, request):
        raise NotImplementedError()

    async def list_models(self):
        return [{"id": self.name}]


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
@pytest.mark.asyncio
async def test_decision_engine_follows_policy_strategy_order():
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

    decision = await engine.route(request, providers)

    assert decision.provider.name == "policy-provider"
    assert decision.metadata["policy_name"] == "Balanced"
    assert decision.metadata["criterion"] == "FirstMatch"
    assert decision.metadata["strategy_name"] == "QueryComplexity"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_decision_engine_all_match_selects_common_provider():
    """AllMatch should select the first provider present in every strategy candidate list."""
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
            "context-only-provider",
            metadata=ProviderMetadata(capability={"complexity": 0.4}),
        ),
        MockProvider(
            "shared-provider",
            metadata=ProviderMetadata(capability={"complexity": 0.8}),
        ),
    ]
    engine = DecisionEngine(policy_name="Balanced")
    engine.policy = DecisionPolicy(
        name="AllMatchPolicy",
        criterion="AllMatch",
        strategies=["QueryComplexity", "ContextLengthQuality"],
    )
    engine.strategy_names = engine.policy.strategies

    decision = await engine.route(request, providers)

    assert decision.provider.name == "shared-provider"
    assert decision.metadata["policy_name"] == "AllMatchPolicy"
    assert decision.metadata["criterion"] == "AllMatch"
    assert decision.metadata["strategy_names"] == [
        "QueryComplexity",
        "ContextLengthQuality",
    ]
    assert decision.metadata["candidate_counts"] == {
        "QueryComplexity": 1,
        "ContextLengthQuality": 2,
    }
