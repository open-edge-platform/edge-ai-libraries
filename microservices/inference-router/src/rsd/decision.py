# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Decision module: loads named strategies and produces route decisions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from src.config.base import RoutingConfig
from src.exceptions import ConfigurationError, RoutingError
from src.models import ChatCompletionRequest
from src.providers.base import ProviderAdapter
from src.rsd.policy import (
    DecisionPolicy,
    load_decision_policies,
    resolve_policy_file,
)
from src.rsd.strategy import (
    ProviderCandidate,
    StrategyDefinition,
    StrategyExecutor,
    load_strategy_definitions,
    resolve_strategy_file,
)


@dataclass
class RouteDecision:
    """Represents a route selection decision for a request."""

    provider: ProviderAdapter
    reason: str
    metadata: Dict[str, Any]


class DecisionEngine:
    """Loads strategies from YAML and routes requests to ranked providers."""

    def __init__(
        self,
        strategy_name: Optional[str] = None,
        policy_name: Optional[str] = None,
    ) -> None:
        self.strategy_file = resolve_strategy_file()
        self.strategy_definitions = load_strategy_definitions(self.strategy_file)
        if not self.strategy_definitions:
            raise ConfigurationError(
                f"No strategies found in strategy file: {self.strategy_file}"
            )

        self.policy_file = resolve_policy_file()
        self.policy_definitions = load_decision_policies(self.policy_file)
        self.policy = self._select_policy(policy_name, strategy_name)
        self.strategy_names = self.policy.strategies
        self._validate_policy_strategies(self.policy)
        self.executor = StrategyExecutor()

    @classmethod
    def from_config(cls, routing_config: RoutingConfig) -> "DecisionEngine":
        """Build a DecisionEngine from routing config."""
        return cls(
            strategy_name=routing_config.strategy,
            policy_name=routing_config.policy,
        )

    def _select_policy(
        self,
        policy_name: Optional[str],
        strategy_name: Optional[str],
    ) -> DecisionPolicy:
        if policy_name:
            if policy_name not in self.policy_definitions:
                raise ConfigurationError(
                    f"Policy '{policy_name}' not found in {self.policy_file}"
                )
            return self.policy_definitions[policy_name]

        if strategy_name:
            return DecisionPolicy(name="DirectStrategy", strategies=[strategy_name])

        if self.policy_definitions:
            return next(iter(self.policy_definitions.values()))

        return DecisionPolicy(name="DirectStrategy", strategies=[next(iter(self.strategy_definitions))])

    def _validate_policy_strategies(self, policy: DecisionPolicy) -> None:
        for strategy_name in policy.strategies:
            if strategy_name not in self.strategy_definitions:
                raise ConfigurationError(
                    f"Policy '{policy.name}' references unknown strategy '{strategy_name}' in {self.strategy_file}"
                )

    async def route(
        self,
        request: ChatCompletionRequest,
        providers: List[ProviderAdapter],
    ) -> RouteDecision:
        if not providers:
            raise RoutingError("No providers available for routing")

        if self.policy.criterion == "AllMatch":
            return await self._route_all_match(request, providers)

        return await self._route_first_match(request, providers)

    async def _route_first_match(
        self,
        request: ChatCompletionRequest,
        providers: List[ProviderAdapter],
    ) -> RouteDecision:
        """Select the first provider from the first strategy that returns candidates."""

        for strategy_name in self.strategy_names:
            candidates = await self._strategy_candidates(strategy_name, request, providers)

            if candidates:
                winner = candidates[0]
                return RouteDecision(
                    provider=winner.provider,
                    reason=winner.reason,
                    metadata={
                        "provider_name": winner.provider.name,
                        "policy_name": self.policy.name,
                        "criterion": self.policy.criterion,
                        "strategy_name": strategy_name,
                        "candidate_count": len(candidates),
                        "model": request.model,
                    },
                )

        return self._fallback_decision(request, providers)

    async def _route_all_match(
        self,
        request: ChatCompletionRequest,
        providers: List[ProviderAdapter],
    ) -> RouteDecision:
        """Select the first provider that appears in every strategy candidate list."""
        strategy_candidates: Dict[str, List[ProviderCandidate]] = {}

        for strategy_name in self.strategy_names:
            candidates = await self._strategy_candidates(strategy_name, request, providers)
            strategy_candidates[strategy_name] = candidates
            if not candidates:
                return self._fallback_decision(request, providers, strategy_candidates)

        winner = self._first_all_match_candidate(strategy_candidates)
        if winner is None:
            return self._fallback_decision(request, providers, strategy_candidates)

        candidate_counts = {
            strategy_name: len(candidates)
            for strategy_name, candidates in strategy_candidates.items()
        }
        return RouteDecision(
            provider=winner.provider,
            reason=(
                f"DecisionEngine: policy '{self.policy.name}' selected provider "
                f"'{winner.provider.name}' because it matched all strategies"
            ),
            metadata={
                "provider_name": winner.provider.name,
                "policy_name": self.policy.name,
                "criterion": self.policy.criterion,
                "strategy_names": self.strategy_names,
                "candidate_counts": candidate_counts,
                "model": request.model,
            },
        )

    async def _strategy_candidates(
        self,
        strategy_name: str,
        request: ChatCompletionRequest,
        providers: List[ProviderAdapter],
    ) -> List[ProviderCandidate]:
        strategy = self.strategy_definitions[strategy_name]
        return await self.executor.execute(
            request=request,
            providers=providers,
            definition=strategy,
        )

    def _first_all_match_candidate(
        self,
        strategy_candidates: Dict[str, List[ProviderCandidate]],
    ) -> Optional[ProviderCandidate]:
        first_strategy_name = self.strategy_names[0]
        common_provider_names = {
            candidate.provider.name
            for candidate in strategy_candidates[first_strategy_name]
        }

        for strategy_name in self.strategy_names[1:]:
            common_provider_names &= {
                candidate.provider.name
                for candidate in strategy_candidates[strategy_name]
            }

        for candidate in strategy_candidates[first_strategy_name]:
            if candidate.provider.name in common_provider_names:
                return candidate

        return None

    def _fallback_decision(
        self,
        request: ChatCompletionRequest,
        providers: List[ProviderAdapter],
        strategy_candidates: Optional[Dict[str, List[ProviderCandidate]]] = None,
    ) -> RouteDecision:
        provider = providers[0]
        candidate_counts = {
            strategy_name: len(candidates)
            for strategy_name, candidates in (strategy_candidates or {}).items()
        }
        return RouteDecision(
            provider=provider,
            reason=(
                f"DecisionEngine: policy '{self.policy.name}' matched no providers, "
                f"falling back to first available provider"
            ),
            metadata={
                "provider_name": provider.name,
                "policy_name": self.policy.name,
                "criterion": self.policy.criterion,
                "strategy_names": self.strategy_names,
                "candidate_count": 0,
                "candidate_counts": candidate_counts,
                "model": request.model,
            },
        )
