# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for strategy execution and provider ranking."""

import pytest

from src.models import ChatCompletionMessage, ChatCompletionRequest, ChatCompletionRole
from src.providers.base import ProviderAdapter, ProviderMetadata
from src.rsd.strategy import (
    build_strategy_definition,
    CapabilitySelector,
    ProviderSelector,
    RuleBinding,
    SortCriterion,
    StrategyDefinition,
    StrategyExecutor,
)
from src.exceptions import ConfigurationError
from src.rsd.rule import ContextLengthRule, QueryComplexityScoreRule


class MockProvider(ProviderAdapter):
    """Minimal provider for strategy tests."""

    async def chat(self, request):
        raise NotImplementedError()

    async def chat_stream(self, request):
        raise NotImplementedError()

    async def list_models(self):
        return [{"id": self.name}]


@pytest.mark.unit
def test_strategy_loader_uses_type_as_rule_class():
    """Strategy rule entries should use type as the rule class selector."""
    definition = build_strategy_definition(
        {
            "name": "planning",
            "rules": [
                {
                    "type": "ContextLengthRule",
                    "param": {"zones": [(0, 4000), (4001, 16000)]},
                }
            ],
            "provider_selector": {"capability": {"complexity": {0: 0.3, 1: 0.5}}},
        }
    )

    assert definition.rules[0].name == "ContextLengthRule"
    assert isinstance(definition.rules[0].rule, ContextLengthRule)


@pytest.mark.unit
def test_strategy_loader_requires_rule_type():
    """Strategy rule entries should not use name as the rule class selector."""
    with pytest.raises(ConfigurationError, match="Each rule entry must have a 'type'"):
        build_strategy_definition(
            {
                "name": "planning",
                "rules": [
                    {
                        "name": "ContextLengthRule",
                        "param": {"zones": [(0, 4000), (4001, 16000)]},
                    }
                ],
                "provider_selector": {"capability": {"complexity": {0: 0.3, 1: 0.5}}},
            }
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_strategy_executor_matches_rule_set_and_sorts_candidates():
    """Executor should gate by rule set and rank providers by metadata."""
    request = ChatCompletionRequest(
        model="test-model",
        messages=[
            ChatCompletionMessage(
                role=ChatCompletionRole.USER,
                content="explain the tradeoffs between two inference backends",
            )
        ],
        max_tokens=2048,
    )

    executor = StrategyExecutor()
    rule_set = [
        RuleBinding(
            "required_complexity",
            QueryComplexityScoreRule((0.0, 1.0), target=0.5),
        ),
        RuleBinding(
            "required_capability",
            QueryComplexityScoreRule((0.0, 1.0), target=0.5),
        ),
    ]
    providers = [
        MockProvider(
            "cheap-fast",
            metadata=ProviderMetadata(
                cost=0.05,
                performance=0.91,
                capability={"complexity": 0.70},
            ),
        ),
        MockProvider(
            "premium",
            metadata=ProviderMetadata(
                cost=0.20,
                performance=0.98,
                capability={"complexity": 0.95},
            ),
        ),
        MockProvider(
            "too-weak",
            metadata=ProviderMetadata(
                cost=0.01,
                performance=0.60,
                capability={"complexity": 0.20},
            ),
        ),
    ]
    definition = StrategyDefinition(
        name="strategy_name1",
        provider_selector=ProviderSelector(),
        rules=rule_set,
        sort=[
            SortCriterion("cost", descending=False),
            SortCriterion("performance", descending=True),
        ],
    )

    candidates = await executor.execute(request, providers, definition)

    assert [candidate.provider.name for candidate in candidates] == ["too-weak", "cheap-fast", "premium"]
    assert candidates[0].rule_outputs["required_complexity"] is True
    assert candidates[0].rule_outputs["required_capability"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_strategy_executor_ranks_lowest_cost_first():
    """StrategyExecutor should return ranked candidates by configured sort."""
    request = ChatCompletionRequest(
        model="test-model",
        messages=[
            ChatCompletionMessage(
                role=ChatCompletionRole.USER,
                content="explain inference router scoring",
            )
        ],
        max_tokens=128,
    )
    providers = [
        MockProvider(
            "p1",
            metadata=ProviderMetadata(cost=0.2, performance=1.0),
        ),
        MockProvider(
            "p2",
            metadata=ProviderMetadata(cost=0.1, performance=1.0),
        ),
    ]
    executor = StrategyExecutor()
    rule_set = [
        RuleBinding(
            "needs_performance",
            QueryComplexityScoreRule((0.0, 1.0), target=0.5),
        )
    ]
    candidates = await executor.execute(
        request=request,
        providers=providers,
        definition=StrategyDefinition(
            name="strategy_name2",
            provider_selector=ProviderSelector(),
            rules=rule_set,
            sort=[SortCriterion("cost")],
        ),
    )

    assert [candidate.provider.name for candidate in candidates] == ["p2", "p1"]
    assert "ranked by cost" in candidates[0].reason


@pytest.mark.unit
@pytest.mark.asyncio
async def test_strategy_executor_filters_providers_by_label_selector():
    """StrategyExecutor should only consider providers allowed by label selector."""
    request = ChatCompletionRequest(
        model="test-model",
        messages=[
            ChatCompletionMessage(
                role=ChatCompletionRole.USER,
                content="please help me plan this migration",
            )
        ],
    )
    providers = [
        MockProvider(
            "p1",
            metadata=ProviderMetadata(labels=["planning"], cost=0.2),
        ),
        MockProvider(
            "p2",
            metadata=ProviderMetadata(labels=["general"], cost=0.1),
        ),
    ]
    executor = StrategyExecutor()
    definition = StrategyDefinition(
        name="planning_only",
        description="Only providers labeled for planning",
        rules=[
            RuleBinding(
                "intent_score",
                QueryComplexityScoreRule((0.0, 1.0), target=0.5),
            )
        ],
        provider_selector=ProviderSelector(label="planning"),
        sort=[SortCriterion("cost")],
    )

    candidates = await executor.execute(request, providers, definition)

    assert [candidate.provider.name for candidate in candidates] == ["p1"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_strategy_executor_filters_providers_by_complexity_selector():
    """StrategyExecutor should only consider providers with enough complexity capability."""
    request = ChatCompletionRequest(
        model="test-model",
        messages=[
            ChatCompletionMessage(
                role=ChatCompletionRole.USER,
                content="compare architecture tradeoffs for a migration plan",
            )
        ],
    )
    providers = [
        MockProvider(
            "p1",
            metadata=ProviderMetadata(cost=0.2, capability={"complexity": 0.8}),
        ),
        MockProvider(
            "p2",
            metadata=ProviderMetadata(cost=0.1, capability={"complexity": 0.4}),
        ),
    ]
    executor = StrategyExecutor()
    definition = StrategyDefinition(
        name="complexity_capable",
        description="Only providers capable enough for complex prompts",
        rules=[
            RuleBinding(
                "intent_score",
                QueryComplexityScoreRule((0.0, 1.0), target=0.5),
            )
        ],
        provider_selector=ProviderSelector(capability=CapabilitySelector(complexity=0.7)),
        sort=[SortCriterion("cost")],
    )

    candidates = await executor.execute(request, providers, definition)

    assert [candidate.provider.name for candidate in candidates] == ["p1"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_strategy_executor_matches_context_length_zone_rule():
    """StrategyExecutor should gate candidates with context length zone rules."""
    request = ChatCompletionRequest(
        model="test-model",
        messages=[
            ChatCompletionMessage(
                role=ChatCompletionRole.USER,
                content="compare inference routing options",
            )
        ],
    )
    providers = [
        MockProvider(
            "p1",
            metadata=ProviderMetadata(cost=0.2, capability={"complexity": 0.8}),
        )
    ]
    executor = StrategyExecutor()
    definition = StrategyDefinition(
        name="context_length",
        description="Context length zone routing",
        rules=[
            RuleBinding(
                "context_length_zone",
                ContextLengthRule(zones=[(0, 4000), (4001, 16000)]),
            )
        ],
        provider_selector=ProviderSelector(capability=CapabilitySelector(complexity=0.7)),
        sort=[SortCriterion("cost")],
    )

    candidates = await executor.execute(request, providers, definition)

    assert [candidate.provider.name for candidate in candidates] == ["p1"]
    assert candidates[0].rule_outputs["context_length_zone"] == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_strategy_executor_uses_zone_complexity_selector():
    """StrategyExecutor should map a zone output to the required complexity."""
    request = ChatCompletionRequest(
        model="test-model",
        messages=[
            ChatCompletionMessage(
                role=ChatCompletionRole.USER,
                content="compare inference routing options",
            )
        ],
    )
    providers = [
        MockProvider(
            "low-complexity",
            metadata=ProviderMetadata(cost=0.1, capability={"complexity": 0.2}),
        ),
        MockProvider(
            "zone-capable",
            metadata=ProviderMetadata(cost=0.2, capability={"complexity": 0.4}),
        ),
    ]
    executor = StrategyExecutor()
    definition = StrategyDefinition(
        name="context_length_zone_selector",
        provider_selector=ProviderSelector(
            capability=CapabilitySelector(complexity={0: 0.3, 1: 0.5})
        ),
        rules=[
            RuleBinding(
                "context_length_zone",
                ContextLengthRule(zones=[(0, 4000), (4001, 16000)]),
            )
        ],
        sort=[SortCriterion("cost")],
    )

    candidates = await executor.execute(request, providers, definition)

    assert [candidate.provider.name for candidate in candidates] == ["zone-capable"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_strategy_executor_uses_zone_label_selector():
    """StrategyExecutor should map a zone output to the required provider label."""
    request = ChatCompletionRequest(
        model="test-model",
        messages=[
            ChatCompletionMessage(
                role=ChatCompletionRole.USER,
                content="compare inference routing options",
            )
        ],
    )
    providers = [
        MockProvider(
            "wrong-label",
            metadata=ProviderMetadata(labels=["general"], cost=0.1),
        ),
        MockProvider(
            "zone-labeled",
            metadata=ProviderMetadata(labels=["local"], cost=0.2),
        ),
    ]
    executor = StrategyExecutor()
    definition = StrategyDefinition(
        name="context_length_label_selector",
        provider_selector=ProviderSelector(label={0: "local", 1: "long-context"}),
        rules=[
            RuleBinding(
                "context_length_zone",
                ContextLengthRule(zones=[(0, 4000), (4001, 16000)]),
            )
        ],
        sort=[SortCriterion("cost")],
    )

    candidates = await executor.execute(request, providers, definition)

    assert [candidate.provider.name for candidate in candidates] == ["zone-labeled"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_strategy_executor_filters_providers_by_cost_selector():
    """StrategyExecutor should only consider providers below a scalar cost threshold."""
    request = ChatCompletionRequest(
        model="test-model",
        messages=[
            ChatCompletionMessage(
                role=ChatCompletionRole.USER,
                content="compare inference routing options",
            )
        ],
    )
    providers = [
        MockProvider("expensive", metadata=ProviderMetadata(cost=0.2)),
        MockProvider("cheap", metadata=ProviderMetadata(cost=0.05)),
    ]
    executor = StrategyExecutor()
    definition = StrategyDefinition(
        name="cost_cap",
        provider_selector=ProviderSelector(cost=0.1),
        rules=[
            RuleBinding(
                "cost_score",
                QueryComplexityScoreRule((0.0, 1.0), target=0.5),
            )
        ],
        sort=[SortCriterion("cost")],
    )

    candidates = await executor.execute(request, providers, definition)

    assert [candidate.provider.name for candidate in candidates] == ["cheap"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_strategy_executor_filters_providers_by_tool_calling_selector():
    """StrategyExecutor should only consider providers with matching tool capability."""
    request = ChatCompletionRequest(
        model="test-model",
        messages=[
            ChatCompletionMessage(
                role=ChatCompletionRole.USER,
                content="retrieve documents with a tool",
            )
        ],
    )
    providers = [
        MockProvider(
            "tool-capable",
            metadata=ProviderMetadata(capability={"tool_calling": True}),
        ),
        MockProvider(
            "no-tools",
            metadata=ProviderMetadata(capability={"tool_calling": False}),
        ),
    ]
    executor = StrategyExecutor()
    definition = StrategyDefinition(
        name="tool_calling_required",
        provider_selector=ProviderSelector(
            capability=CapabilitySelector(tool_calling=True)
        ),
        rules=[
            RuleBinding(
                "tool_score",
                QueryComplexityScoreRule((0.0, 1.0), target=0.5),
            )
        ],
    )

    candidates = await executor.execute(request, providers, definition)

    assert [candidate.provider.name for candidate in candidates] == ["tool-capable"]


@pytest.mark.unit
def test_strategy_loader_rejects_non_boolean_tool_calling_selector():
    """tool_calling selector values must be explicit booleans."""
    with pytest.raises(
        ConfigurationError,
        match="provider_selector.capability.tool_calling must be a boolean",
    ):
        build_strategy_definition(
            {
                "name": "tool_calling",
                "rules": [],
                "provider_selector": {"capability": {"tool_calling": "true"}},
            }
        )


@pytest.mark.unit
def test_strategy_loader_rejects_top_level_capability_selector():
    """Capability selectors should use the same nested shape as provider metadata."""
    with pytest.raises(
        ConfigurationError,
        match="provider_selector.complexity must move to provider_selector.capability.complexity",
    ):
        build_strategy_definition(
            {
                "name": "legacy_complexity",
                "rules": [],
                "provider_selector": {"complexity": 0.7},
            }
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_strategy_executor_uses_zone_cost_selector():
    """StrategyExecutor should map a zone output to the allowed provider cost."""
    request = ChatCompletionRequest(
        model="test-model",
        messages=[
            ChatCompletionMessage(
                role=ChatCompletionRole.USER,
                content="compare inference routing options",
            )
        ],
    )
    providers = [
        MockProvider("too-expensive", metadata=ProviderMetadata(cost=0.2)),
        MockProvider("zone-priced", metadata=ProviderMetadata(cost=0.04)),
    ]
    executor = StrategyExecutor()
    definition = StrategyDefinition(
        name="context_length_cost_selector",
        provider_selector=ProviderSelector(cost={0: 0.05, 1: 0.1}),
        rules=[
            RuleBinding(
                "context_length_zone",
                ContextLengthRule(zones=[(0, 4000), (4001, 16000)]),
            )
        ],
        sort=[SortCriterion("cost")],
    )

    candidates = await executor.execute(request, providers, definition)

    assert [candidate.provider.name for candidate in candidates] == ["zone-priced"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_strategy_executor_rejects_false_boolean_rule_output():
    """StrategyExecutor should reject match/value/score rules that return False."""
    request = ChatCompletionRequest(
        model="test-model",
        messages=[
            ChatCompletionMessage(
                role=ChatCompletionRole.USER,
                content="short prompt",
            )
        ],
    )
    providers = [MockProvider("p1", metadata=ProviderMetadata(cost=0.2))]
    executor = StrategyExecutor()
    definition = StrategyDefinition(
        name="score_threshold_not_met",
        provider_selector=ProviderSelector(),
        rules=[
            RuleBinding(
                "score_threshold",
                QueryComplexityScoreRule((0.0, 1.0), target=0.8),
            )
        ],
    )

    candidates = await executor.execute(request, providers, definition)

    assert candidates == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_strategy_executor_rejects_unmatched_zone_rule_output():
    """StrategyExecutor should reject zone rules that return -1."""
    request = ChatCompletionRequest(
        model="test-model",
        messages=[
            ChatCompletionMessage(
                role=ChatCompletionRole.USER,
                content="this context is outside the only configured zone",
            )
        ],
    )
    providers = [MockProvider("p1", metadata=ProviderMetadata(cost=0.2))]
    executor = StrategyExecutor()
    definition = StrategyDefinition(
        name="context_length_unmatched",
        provider_selector=ProviderSelector(),
        rules=[
            RuleBinding(
                "context_length_zone",
                ContextLengthRule(zones=[(0, 3)]),
            )
        ],
    )

    candidates = await executor.execute(request, providers, definition)

    assert candidates == []