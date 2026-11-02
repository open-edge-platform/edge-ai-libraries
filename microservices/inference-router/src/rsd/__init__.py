# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Rule-Strategy-Decision module exports.

Importing this package also imports both rule families, which registers their
rules into :data:`src.rsd.engine.rule.RULE_CLASS_REGISTRY`.
"""

from src.rsd.engine.decision import RouteDecision, DecisionEngine
from src.rsd.engine.policy import DecisionPolicy
from src.rsd.engine.rule import (
    Rule,
    ValueRule,
    MatchRule,
    ScoreRule,
    ZoneRule,
    RuleEngine,
)
from src.rsd.rule_based.rules import (
    MessageContentRule,
    ToolCallsRule,
    MetadataRule,
    QueryComplexityScoreRule,
    QueryComplexityZoneRule,
    ContextLengthRule,
)
from src.rsd.model_based.rule import ModelBasedRule
from src.rsd.engine.strategy import (
    RuleBinding,
    ProviderSelector,
    SortCriterion,
    StrategyDefinition,
    ProviderCandidate,
    StrategyExecutor,
)

__all__ = [
    # decision
    "RouteDecision",
    "DecisionEngine",
    "DecisionPolicy",
    # rule
    "Rule",
    "ValueRule",
    "MatchRule",
    "ScoreRule",
    "ZoneRule",
    "RuleEngine",
    "MessageContentRule",
    "ToolCallsRule",
    "MetadataRule",
    "QueryComplexityScoreRule",
    "QueryComplexityZoneRule",
    "ContextLengthRule",
    "ModelBasedRule",
    # strategy
    "RuleBinding",
    "ProviderSelector",
    "SortCriterion",
    "StrategyDefinition",
    "ProviderCandidate",
    "StrategyExecutor",
]
