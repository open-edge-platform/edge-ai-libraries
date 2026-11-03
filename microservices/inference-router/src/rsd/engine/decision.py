# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Decision module: loads named strategies and produces route decisions."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from src.config.base import RoutingConfig
from src.exceptions import ConfigurationError, RoutingError
from src.models import ChatCompletionRequest
from src.providers.base import ProviderAdapter
from src.rsd.engine.policy import (
    DecisionPolicy,
    load_decision_policies,
    resolve_policy_file,
)
from src.rsd.engine.strategy import (
    ProviderCandidate,
    StrategyExecutor,
    load_strategy_definitions,
    resolve_strategy_file,
)
from src.rsd.model_based.registry import ReconcileResult, get_registry

logger = logging.getLogger(__name__)


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

    def reconcile_classifiers(self) -> ReconcileResult:
        """Prepare explicit classifier versions used by the active policy.

        Runs on the calling thread, not the rule-eval worker: backbone runtimes
        are thread-safe, so requests keep being served by the current engine
        while this one loads.
        """
        rules = [
            binding.rule
            for strategy_name in self.strategy_names
            for binding in self.strategy_definitions[strategy_name].rules
        ]
        versioned = [
            rule for rule in rules if getattr(rule, "registry_requirement", None) is not None
        ]
        requirements = [rule.registry_requirement for rule in versioned]
        registry = get_registry()
        result = registry.reconcile(requirements)
        for rule in versioned:
            classifier = result.bindings[rule.registry_requirement].classifier
            rule.bind_classifier(classifier)
            if classifier is not None:
                self._check_classifier_zones(rule, classifier)
        return result

    def release_classifiers(self) -> None:
        """Detach the active policy's versioned rules (unload_first swap).

        Together with :meth:`.registry.ClassifierRegistry.release_versions`
        this leaves nothing holding the old runtimes, so loading the new
        policy starts from one backbone instead of two. Requests in the
        window answer -1: the documented unload_first trade-off.
        """
        registry = get_registry()
        keys = []
        for rule in self._versioned_rules():
            release = getattr(rule, "release_classifier", None)
            if release is not None:
                release()
                keys.append(rule.registry_requirement)
        registry.release_versions(key for key in keys if key is not None)

    def rebind_classifiers(self) -> None:
        """Re-attach classifiers after a failed swap.

        Resolves actively on purpose: the swap may already have dropped the
        old versions from the registry, so a passive lookup would find nothing
        and the detached rules would answer -1 until the next successful
        activation. Non-strict :meth:`effective` re-publishes them. Best
        effort: logs, never raises.
        """
        registry = get_registry()
        for rule in self._versioned_rules():
            requirement = getattr(rule, "registry_requirement", None)
            if requirement is None:
                continue
            try:
                ready = registry.effective(*requirement)
            except Exception as exc:  # noqa: BLE001 - best-effort restore
                logger.warning(
                    "Could not restore classifier %s/%s after the failed swap: %s",
                    *requirement,
                    exc,
                )
                continue
            if ready.classifier is not None:
                rule.bind_classifier(ready.classifier)

    def _versioned_rules(self) -> List[Any]:
        """Rules of the active policy that load a classifier version."""
        return [
            binding.rule
            for strategy_name in self.strategy_names
            for binding in self.strategy_definitions[strategy_name].rules
            if getattr(binding.rule, "registry_requirement", None) is not None
        ]

    def _check_classifier_zones(self, rule: Any, classifier: Any) -> None:
        """Warn when a strategy's zone-indexed selectors don't match its version's zones.

        ``provider_selector.label``, ``capability.complexity`` and ``cost`` may each
        be keyed by zone index. Indices the version never produces are dead
        entries; zones without an entry match no provider here, so their requests
        move on to the next strategy -- sometimes intended, often an omission.
        Fixed (non-indexed) selectors are not checked. Best-effort: never raises.
        """
        zone_count = len(classifier.bundle.zone_names)
        zones = set(range(zone_count))
        for strategy_name in self.strategy_names:
            definition = self.strategy_definitions[strategy_name]
            if not any(binding.rule is rule for binding in definition.rules):
                continue
            selector = definition.provider_selector
            indexed = {
                "label": selector.label,
                "capability.complexity": selector.capability.complexity,
                "cost": selector.cost,
            }
            for field_name, mapping in indexed.items():
                if not isinstance(mapping, dict):
                    continue
                extra = sorted(set(mapping) - zones)
                missing = sorted(zones - set(mapping))
                if extra:
                    logger.warning(
                        "Strategy '%s': provider_selector.%s maps zone(s) %s, but its "
                        "classifier version produces only zones 0..%d (%s).",
                        strategy_name,
                        field_name,
                        extra,
                        zone_count - 1,
                        ", ".join(classifier.bundle.zone_names),
                    )
                if missing:
                    logger.warning(
                        "Strategy '%s': provider_selector.%s has no entry for zone(s) %s "
                        "(%s); requests classified there match no provider in this "
                        "strategy and move on to the next one.",
                        strategy_name,
                        field_name,
                        missing,
                        ", ".join(classifier.bundle.zone_names[z] for z in missing),
                    )

    def preload_classifiers(self) -> int:
        """Load the classifiers of the active policy's rules; return how many distinct ones.

        Only strategies in the active policy are considered: the engine also
        instantiates rules of inactive strategies, and those must not load models.
        Loading runs on the calling thread while requests keep being served (a
        new engine may share a backbone runtime with the current one; runtimes
        are thread-safe). Call before swapping this engine in, so it starts warm.
        """
        reconciliation = self.reconcile_classifiers()
        classifiers: Dict[int, Any] = {
            id(binding.classifier): binding.classifier
            for binding in reconciliation.bindings.values()
            if binding.classifier is not None
        }
        for strategy_name in self.strategy_names:
            for binding in self.strategy_definitions[strategy_name].rules:
                if getattr(binding.rule, "registry_requirement", None) is not None:
                    continue
                ensure = getattr(binding.rule, "ensure_classifier", None)
                if ensure is None:
                    continue
                classifier = ensure()
                if classifier is not None:
                    classifiers[id(classifier)] = classifier
        return len(classifiers)

    def validate_against_providers(self, providers: List[ProviderAdapter]) -> None:
        """Warn about ``provider_selector.label`` values no provider carries.

        A request routed to such a label gets no candidates from that strategy;
        if no other strategy matches, it goes to the provider marked
        ``fallback: true``, or is rejected when none is (see
        :meth:`_fallback_decision`) -- a silent misconfiguration. Best-effort:
        logs, never raises. Call once the provider set is known (startup /
        engine rebuild).
        """
        available = set()
        for provider in providers:
            available.update(getattr(provider.metadata, "labels", None) or [])

        for strategy_name in self.strategy_names:
            label_selector = self.strategy_definitions[strategy_name].provider_selector.label
            if isinstance(label_selector, str):
                required = [label_selector]
            elif isinstance(label_selector, dict):
                required = list(label_selector.values())
            else:
                continue
            for label in required:
                if label not in available:
                    logger.warning(
                        "Strategy '%s' routes to provider label '%s', but no available "
                        "provider carries it; requests classified into it match no provider "
                        "in this strategy and, if no later strategy matches, go to the "
                        "provider marked 'fallback: true' (rejected if there is none). Add "
                        "the label to a provider's metadata or fix provider_selector.label.",
                        strategy_name,
                        label,
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

    @staticmethod
    def _fallback_provider(
        providers: List[ProviderAdapter],
    ) -> Optional[ProviderAdapter]:
        """Return the provider explicitly marked ``fallback: true``, or None.

        First match wins if several providers set it. Returns ``None`` when no
        provider is designated as the fallback — the caller then rejects the
        request rather than silently routing to an arbitrary provider.
        """
        for provider in providers:
            if getattr(provider, "fallback", False):
                return provider
        return None

    def _fallback_decision(
        self,
        request: ChatCompletionRequest,
        providers: List[ProviderAdapter],
        strategy_candidates: Optional[Dict[str, List[ProviderCandidate]]] = None,
    ) -> RouteDecision:
        provider = self._fallback_provider(providers)
        if provider is None:
            # No provider cleared the policy and none is marked as the
            # fallback: reject the request instead of guessing a provider.
            raise RoutingError(
                f"No provider satisfied routing policy '{self.policy.name}' and "
                f"no fallback provider is configured; rejecting the request. "
                f"Mark a provider with 'fallback: true' in config.yaml to handle "
                f"this case."
            )

        candidate_counts = {
            strategy_name: len(candidates)
            for strategy_name, candidates in (strategy_candidates or {}).items()
        }
        return RouteDecision(
            provider=provider,
            reason=(
                f"DecisionEngine: policy '{self.policy.name}' matched no providers, "
                f"falling back to designated fallback provider '{provider.name}'"
            ),
            metadata={
                "provider_name": provider.name,
                "policy_name": self.policy.name,
                "criterion": self.policy.criterion,
                "strategy_names": self.strategy_names,
                "candidate_count": 0,
                "candidate_counts": candidate_counts,
                "model": request.model,
                "fallback": True,
                "designated_fallback": True,
            },
        )
