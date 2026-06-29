# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Strategy module: named rule sets for provider ranking."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import yaml

from src.exceptions import ConfigurationError
from src.models import ChatCompletionRequest
from src.providers.base import ProviderAdapter
from src.rsd.rule import (
    ContextLengthRule,
    MessageContentRule,
    MetadataRule,
    ModelNameRule,
    QueryComplexityScoreRule,
    QueryComplexityZoneRule,
    Rule,
    ToolCallsRule,
)


RULE_CLASS_REGISTRY: Dict[str, type[Rule]] = {
    "ModelNameRule": ModelNameRule,
    "MessageContentRule": MessageContentRule,
    "ToolCallsRule": ToolCallsRule,
    "MetadataRule": MetadataRule,
    "QueryComplexityScoreRule": QueryComplexityScoreRule,
    "QueryComplexityZoneRule": QueryComplexityZoneRule,
    "ContextLengthRule": ContextLengthRule,
}


@dataclass
class RuleBinding:
    """A named rule entry used in a strategy rule set."""

    name: str
    rule: Rule


@dataclass
class SortCriterion:
    """Sort candidate providers by a provider metadata attribute."""

    provider_attribute: str
    descending: bool = False


@dataclass
class CapabilitySelector:
    """Provider capability selector criteria."""

    complexity: Optional[Union[float, Dict[int, float]]] = None
    tool_calling: Optional[bool] = None


@dataclass
class ProviderSelector:
    """Provider selector criteria used inside a strategy definition."""

    label: Optional[Union[str, Dict[int, str]]] = None
    cost: Optional[Union[float, Dict[int, float]]] = None
    capability: CapabilitySelector = field(default_factory=CapabilitySelector)


@dataclass
class StrategyDefinition:
    """Named strategy definition loaded from strategy.yaml."""

    name: str
    provider_selector: ProviderSelector
    description: str = ""
    rules: List[RuleBinding] = field(default_factory=list)
    sort: List[SortCriterion] = field(default_factory=list)
    require_healthy: bool = False
    limit: Optional[int] = None


@dataclass
class ProviderCandidate:
    """Ranked provider candidate returned by StrategyExecutor."""

    provider: ProviderAdapter
    metadata: Dict[str, Any]
    rule_outputs: Dict[str, Any]
    reason: str


class StrategyExecutor:
    """Evaluate a request against a named rule set, then rank providers by metadata."""

    def evaluate_rules(
        self,
        request: ChatCompletionRequest,
        rule_set: List[RuleBinding],
    ) -> Dict[str, Any]:
        """Evaluate the full rule set and return named outputs."""
        return {binding.name: binding.rule.evaluate(request) for binding in rule_set}

    async def execute(
        self,
        request: ChatCompletionRequest,
        providers: List[ProviderAdapter],
        definition: StrategyDefinition,
    ) -> List[ProviderCandidate]:
        """Return sorted provider candidates for the given request."""
        rule_outputs = self.evaluate_rules(request, definition.rules)

        if not self._request_matches_rule_set(rule_outputs):
            return []

        candidates: List[ProviderCandidate] = []

        for provider in providers:
            metadata = {"name": provider.name, **provider.metadata.to_dict()}

            if definition.require_healthy and not await provider.health_check():
                continue

            if not self._matches_provider_selector(metadata, definition, rule_outputs):
                continue

            candidates.append(
                ProviderCandidate(
                    provider=provider,
                    metadata=metadata,
                    rule_outputs=rule_outputs,
                    reason=self._build_reason(metadata, definition),
                )
            )

        self._sort_candidates(candidates, definition)
        if definition.limit is not None:
            return candidates[: definition.limit]
        return candidates

    def _matches_provider_selector(
        self,
        provider_metadata: Dict[str, Any],
        definition: StrategyDefinition,
        rule_outputs: Dict[str, Any],
    ) -> bool:
        """Return True when a provider matches the strategy's provider selector."""
        provider_selector = definition.provider_selector
        return self._matches_label_selector(
            provider_metadata,
            provider_selector,
            rule_outputs,
        ) and self._matches_complexity_selector(
            provider_metadata,
            provider_selector,
            rule_outputs,
        ) and self._matches_cost_selector(
            provider_metadata,
            provider_selector,
            rule_outputs,
        ) and self._matches_tool_calling_selector(
            provider_metadata,
            provider_selector,
        )

    def _matches_label_selector(
        self,
        provider_metadata: Dict[str, Any],
        provider_selector: ProviderSelector,
        rule_outputs: Dict[str, Any],
    ) -> bool:
        required_label = self._resolve_label_requirement(
            provider_selector,
            rule_outputs,
        )
        if required_label is None:
            return provider_selector.label is None

        provider_labels = provider_metadata.get("labels")
        return isinstance(provider_labels, list) and required_label in provider_labels

    def _resolve_label_requirement(
        self,
        provider_selector: ProviderSelector,
        rule_outputs: Dict[str, Any],
    ) -> Optional[str]:
        label = provider_selector.label
        if label is None:
            return None
        if isinstance(label, str):
            return label

        zone_index = self._first_zone_output(rule_outputs)
        if zone_index is None:
            return None
        return label.get(zone_index)

    def _matches_complexity_selector(
        self,
        provider_metadata: Dict[str, Any],
        provider_selector: ProviderSelector,
        rule_outputs: Dict[str, Any],
    ) -> bool:
        required_complexity = self._resolve_complexity_requirement(
            provider_selector,
            rule_outputs,
        )
        if required_complexity is None:
            return True

        provider_complexity = self._resolve_attribute(provider_metadata, "capability.complexity")
        if not isinstance(provider_complexity, (int, float)):
            return False

        return provider_complexity >= required_complexity

    def _resolve_complexity_requirement(
        self,
        provider_selector: ProviderSelector,
        rule_outputs: Dict[str, Any],
    ) -> Optional[float]:
        complexity = provider_selector.capability.complexity
        if complexity is None:
            return None
        if isinstance(complexity, (int, float)):
            return float(complexity)

        zone_index = self._first_zone_output(rule_outputs)
        if zone_index is None:
            return None
        return complexity.get(zone_index)

    def _matches_cost_selector(
        self,
        provider_metadata: Dict[str, Any],
        provider_selector: ProviderSelector,
        rule_outputs: Dict[str, Any],
    ) -> bool:
        required_cost = self._resolve_cost_requirement(
            provider_selector,
            rule_outputs,
        )
        if required_cost is None:
            return provider_selector.cost is None

        provider_cost = provider_metadata.get("cost")
        if not isinstance(provider_cost, (int, float)):
            return False

        return provider_cost <= required_cost

    def _resolve_cost_requirement(
        self,
        provider_selector: ProviderSelector,
        rule_outputs: Dict[str, Any],
    ) -> Optional[float]:
        cost = provider_selector.cost
        if cost is None:
            return None
        if isinstance(cost, (int, float)):
            return float(cost)

        zone_index = self._first_zone_output(rule_outputs)
        if zone_index is None:
            return None
        return cost.get(zone_index)

    def _matches_tool_calling_selector(
        self,
        provider_metadata: Dict[str, Any],
        provider_selector: ProviderSelector,
    ) -> bool:
        required_tool_calling = provider_selector.capability.tool_calling
        if required_tool_calling is None:
            return True

        provider_tool_calling = self._resolve_attribute(
            provider_metadata,
            "capability.tool_calling",
        )
        if provider_tool_calling is None:
            provider_tool_calling = provider_metadata.get("tool_calling")

        return provider_tool_calling is required_tool_calling

    def _first_zone_output(self, rule_outputs: Dict[str, Any]) -> Optional[int]:
        for value in rule_outputs.values():
            if type(value) is int:
                return value
        return None

    def _request_matches_rule_set(self, rule_outputs: Dict[str, Any]) -> bool:
        """Return True when the request satisfies the configured rule set.

        Match, value, and score rules return ``bool`` outputs. Zone rules return
        an ``int`` zone index, where ``-1`` means no zone matched.
        """
        return all(self._rule_output_matches(value) for value in rule_outputs.values())

    def _rule_output_matches(self, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            return value != -1
        return False

    def _sort_candidates(
        self,
        candidates: List[ProviderCandidate],
        definition: StrategyDefinition,
    ) -> None:
        for criterion in reversed(definition.sort):
            candidates.sort(
                key=lambda candidate: self._sort_key(
                    self._resolve_attribute(candidate.metadata, criterion.provider_attribute)
                ),
                reverse=criterion.descending,
            )

    def _sort_key(self, value: Any) -> Tuple[int, Any]:
        return (value is None, value)

    def _build_reason(
        self,
        provider_metadata: Dict[str, Any],
        definition: StrategyDefinition,
    ) -> str:
        if definition.sort:
            ordered_by = ", ".join(item.provider_attribute for item in definition.sort)
            return (
                f"StrategyExecutor: strategy '{definition.name}' matched for provider "
                f"'{provider_metadata['name']}' and was ranked by {ordered_by}"
            )

        return f"StrategyExecutor: strategy '{definition.name}' matched for provider '{provider_metadata['name']}'"

    def _resolve_attribute(self, payload: Dict[str, Any], attribute_path: str) -> Any:
        node: Any = payload
        for part in attribute_path.split("."):
            if not isinstance(node, dict) or part not in node:
                return None
            node = node[part]
        return node


def resolve_strategy_file() -> Path:
    """Return the canonical path to the strategy YAML file."""
    return Path(__file__).with_name("strategy.yaml").expanduser().resolve()


def load_strategy_definitions(
    strategy_file: Optional[Path] = None,
) -> Dict[str, StrategyDefinition]:
    """Load named strategy definitions from strategy.yaml."""
    strategy_path = strategy_file or resolve_strategy_file()

    try:
        with open(strategy_path) as handle:
            payload = yaml.safe_load(handle) or {}
    except FileNotFoundError as exc:
        raise ConfigurationError(f"Strategy file not found: {strategy_path}") from exc
    except yaml.YAMLError as exc:
        raise ConfigurationError(f"Failed to parse strategy YAML: {exc}") from exc
    except OSError as exc:
        raise ConfigurationError(f"Failed to read strategy file: {exc}") from exc

    strategies_data = payload.get("strategies", [])
    if not isinstance(strategies_data, list):
        raise ConfigurationError("strategy.yaml must define a 'strategies' list")

    definitions: Dict[str, StrategyDefinition] = {}
    for strategy_data in strategies_data:
        definition = build_strategy_definition(strategy_data)
        definitions[definition.name] = definition

    return definitions


def build_strategy_definition(strategy_data: Dict[str, Any]) -> StrategyDefinition:
    """Build a StrategyDefinition from a parsed YAML mapping."""
    if not isinstance(strategy_data, dict):
        raise ConfigurationError("Each strategy entry must be a mapping")

    name = strategy_data.get("name")
    if not name:
        raise ConfigurationError("Strategy entry must have a 'name'")

    rules_data = strategy_data.get("rules", [])
    if not isinstance(rules_data, list):
        raise ConfigurationError(f"Strategy '{name}' must define a 'rules' list")

    rules = [build_rule_binding(rule_data) for rule_data in rules_data]
    provider_selector = build_provider_selector(strategy_data.get("provider_selector"), name)
    sort = [build_sort_criterion(sort_data) for sort_data in strategy_data.get("sort", [])]

    return StrategyDefinition(
        name=name,
        description=strategy_data.get("description", ""),
        rules=rules,
        provider_selector=provider_selector,
        sort=sort,
        require_healthy=strategy_data.get("require_healthy", False),
        limit=strategy_data.get("limit"),
    )


def build_provider_selector(
    selector_data: Dict[str, Any] | None,
    strategy_name: str,
) -> ProviderSelector:
    """Build a strategy-scoped provider selector definition."""
    if selector_data is None:
        raise ConfigurationError(
            f"Strategy '{strategy_name}' must define 'provider_selector'"
        )
    if not isinstance(selector_data, dict):
        raise ConfigurationError(
            f"Strategy '{strategy_name}' must define 'provider_selector' as a mapping"
        )

    _validate_no_top_level_capability_selectors(selector_data, strategy_name)

    return ProviderSelector(
        label=build_label_selector(selector_data.get("label"), strategy_name),
        cost=build_cost_selector(selector_data.get("cost"), strategy_name),
        capability=build_capability_selector(selector_data.get("capability"), strategy_name),
    )


def _validate_no_top_level_capability_selectors(
    selector_data: Dict[str, Any],
    strategy_name: str,
) -> None:
    """Reject capability selectors outside provider_selector.capability."""
    for field_name in ("complexity", "tool_calling"):
        if field_name in selector_data:
            raise ConfigurationError(
                f"Strategy '{strategy_name}' provider_selector.{field_name} must move "
                f"to provider_selector.capability.{field_name}"
            )


def build_capability_selector(
    capability_data: Any,
    strategy_name: str,
) -> CapabilitySelector:
    """Build provider capability selector data."""
    if capability_data is None:
        return CapabilitySelector()
    if not isinstance(capability_data, dict):
        raise ConfigurationError(
            f"Strategy '{strategy_name}' provider_selector.capability must be a mapping"
        )

    return CapabilitySelector(
        complexity=build_complexity_selector(
            capability_data.get("complexity"),
            strategy_name,
        ),
        tool_calling=build_tool_calling_selector(
            capability_data.get("tool_calling"),
            strategy_name,
        ),
    )


def build_label_selector(
    label_data: Any,
    strategy_name: str,
) -> Optional[Union[str, Dict[int, str]]]:
    """Build scalar or zone-indexed label selector data."""
    if label_data is None:
        return None
    if isinstance(label_data, str):
        return label_data
    if not isinstance(label_data, dict):
        raise ConfigurationError(
            f"Strategy '{strategy_name}' provider_selector.label must be a string or mapping"
        )

    label_by_zone: Dict[int, str] = {}
    for zone, label in label_data.items():
        if not isinstance(label, str) or not label:
            raise ConfigurationError(
                f"Strategy '{strategy_name}' provider_selector.label must map zone indexes to labels"
            )
        try:
            label_by_zone[int(zone)] = label
        except (TypeError, ValueError) as exc:
            raise ConfigurationError(
                f"Strategy '{strategy_name}' provider_selector.label must map zone indexes to labels"
            ) from exc

    return label_by_zone


def build_complexity_selector(
    complexity_data: Any,
    strategy_name: str,
) -> Optional[Union[float, Dict[int, float]]]:
    """Build scalar or zone-indexed complexity selector data."""
    if complexity_data is None:
        return None
    if isinstance(complexity_data, (int, float)):
        return float(complexity_data)
    if not isinstance(complexity_data, dict):
        raise ConfigurationError(
            f"Strategy '{strategy_name}' provider_selector.capability.complexity must be a number or mapping"
        )

    complexity_by_zone: Dict[int, float] = {}
    for zone, threshold in complexity_data.items():
        try:
            zone_index = int(zone)
            complexity_by_zone[zone_index] = float(threshold)
        except (TypeError, ValueError) as exc:
            raise ConfigurationError(
                f"Strategy '{strategy_name}' provider_selector.capability.complexity must map zone indexes to numbers"
            ) from exc

    return complexity_by_zone


def build_cost_selector(
    cost_data: Any,
    strategy_name: str,
) -> Optional[Union[float, Dict[int, float]]]:
    """Build scalar or zone-indexed cost selector data."""
    if cost_data is None:
        return None
    if isinstance(cost_data, (int, float)):
        return float(cost_data)
    if not isinstance(cost_data, dict):
        raise ConfigurationError(
            f"Strategy '{strategy_name}' provider_selector.cost must be a number or mapping"
        )

    cost_by_zone: Dict[int, float] = {}
    for zone, threshold in cost_data.items():
        try:
            zone_index = int(zone)
            cost_by_zone[zone_index] = float(threshold)
        except (TypeError, ValueError) as exc:
            raise ConfigurationError(
                f"Strategy '{strategy_name}' provider_selector.cost must map zone indexes to numbers"
            ) from exc

    return cost_by_zone


def build_tool_calling_selector(
    tool_calling_data: Any,
    strategy_name: str,
) -> Optional[bool]:
    """Build tool-calling capability selector data."""
    if tool_calling_data is None:
        return None
    if isinstance(tool_calling_data, bool):
        return tool_calling_data
    raise ConfigurationError(
        f"Strategy '{strategy_name}' provider_selector.capability.tool_calling must be a boolean"
    )


def build_rule_binding(rule_data: Dict[str, Any]) -> RuleBinding:
    """Build a RuleBinding from a parsed YAML mapping."""
    if not isinstance(rule_data, dict):
        raise ConfigurationError("Each rule entry must be a mapping")

    rule_name = rule_data.get("type")
    if not rule_name:
        raise ConfigurationError("Each rule entry must have a 'type'")

    params = rule_data.get("param", {}) or {}
    if not isinstance(params, dict):
        raise ConfigurationError(f"Rule '{rule_name}' must define a mapping under 'param'")

    rule = build_rule_instance(rule_name, params)
    return RuleBinding(name=rule_name, rule=rule)


def build_rule_instance(rule_name: str, params: Dict[str, Any]) -> Rule:
    """Instantiate and validate a configured rule."""
    rule_cls = RULE_CLASS_REGISTRY.get(rule_name)
    if rule_cls is None:
        raise ConfigurationError(f"Unknown rule class '{rule_name}'")

    return rule_cls(**params)


def build_sort_criterion(sort_data: Dict[str, Any]) -> SortCriterion:
    """Build a SortCriterion from a parsed YAML mapping."""
    if not isinstance(sort_data, dict):
        raise ConfigurationError("Each sort entry must be a mapping")

    provider_attribute = sort_data.get("provider_attribute")
    if not provider_attribute:
        raise ConfigurationError("Each sort entry must have a 'provider_attribute'")

    return SortCriterion(
        provider_attribute=provider_attribute,
        descending=sort_data.get("descending", False),
    )
