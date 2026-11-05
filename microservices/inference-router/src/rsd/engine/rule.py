# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Rule module: criteria for judging a ChatCompletionRequest.

Holds the rule base classes, :class:`RuleEngine` and the rule registry. Concrete
rules live in the two rule families — :mod:`src.rsd.rule_based.rules`
(heuristics) and :mod:`src.rsd.model_based.rule` (classifier-backed) — which
register themselves here via :func:`register_rule`; the engine never imports
them.

Three output types are supported:

* :class:`ValueRule` — ``evaluate()`` returns ``bool``.
* :class:`ScoreRule`     — ``evaluate()`` scores request and target, then returns ``bool``.
* :class:`ZoneRule`      — ``evaluate()`` returns an ``int`` zone index (or ``-1``).
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Any, Dict, Generic, List, Tuple, TypeVar

from src.models import ChatCompletionRequest, ChatCompletionRole

T = TypeVar("T")


def _content_text(content: Any) -> str:
    """Flatten message content to a single text string.

    Accepts the OpenAI content-parts array as well as a plain string;
    image_url and other non-text parts are ignored.
    """
    if not content:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text", "")))
        return "\n".join(parts)
    return ""


# ---------------------------------------------------------------------------
# Generic base
# ---------------------------------------------------------------------------

class Rule(ABC, Generic[T]):
    """Generic abstract base class for routing rules.

    Type parameter ``T`` is the return type of :meth:`evaluate`.
    """

    # When True, :meth:`evaluate` does blocking work (e.g. a model forward pass)
    # and the StrategyExecutor offloads just this rule to a worker thread so it
    # does not stall the event loop. Cheap rules leave this False and run inline.
    blocking_eval: bool = False

    @abstractmethod
    def evaluate(self, request: ChatCompletionRequest) -> T:
        """Evaluate the rule against *request* and return a typed result."""


# ---------------------------------------------------------------------------
# Typed abstract bases
# ---------------------------------------------------------------------------

class ValueRule(Rule[bool]):
    """Rule whose evaluation compares request data against a direct value target."""

    @abstractmethod
    def evaluate(self, request: ChatCompletionRequest) -> bool:
        """Return ``True`` if the request satisfies this rule's criteria."""


class MatchRule(ValueRule):
    """Value rule specialized for request/criteria matching."""

    @abstractmethod
    def evaluate(self, request: ChatCompletionRequest) -> bool:
        """Return ``True`` if the request matches this rule's criteria."""


class ScoreRule(Rule[bool]):
    """Rule whose evaluation compares request and target scores.

    Args:
        score_range: ``(min_score, max_score)`` inclusive bounds for the returned
                     scores.  Concrete implementations must honour this contract.
        target: Raw target value to be converted into a score.
        operator: Comparison operator: "gt", "gte", "lt", "lte", or "eq".
    """

    def __init__(
        self,
        score_range: Tuple[float, float],
        target: Any,
        operator: str = "gte",
    ) -> None:
        if score_range[0] > score_range[1]:
            raise ValueError(
                f"score_range min ({score_range[0]}) must be <= max ({score_range[1]})"
            )
        self.score_range = score_range
        self.target = target
        self.target_score = self._target_to_score(target)
        self.operator = operator

    def _clamp(self, value: float) -> float:
        """Clamp *value* to :attr:`score_range`."""
        return max(self.score_range[0], min(self.score_range[1], value))

    def _target_to_score(self, target: Any) -> float:
        """Convert a raw target into a score within :attr:`score_range`."""
        try:
            score = float(target)
        except (TypeError, ValueError) as exc:
            raise ValueError("target must be convertible to a score") from exc
        return self._clamp(score)

    @abstractmethod
    def _request_to_score(self, request: ChatCompletionRequest) -> float:
        """Convert request data into a score within :attr:`score_range`."""

    def evaluate(self, request: ChatCompletionRequest) -> bool:
        """Return whether the request score satisfies the target score."""
        score = self._request_to_score(request)
        return RuleEngine._compare(score, self.target_score, self.operator)


class ZoneRule(Rule[int]):
    """Rule whose evaluation maps a request metric to a zone index.

    Args:
        zones: Ordered list of ``(lower, upper)`` inclusive bounds.  The first
               zone whose range contains the computed metric value is returned.
               ``-1`` is returned when no zone matches.
    """

    def __init__(self, zones: List[Tuple[float, float]]) -> None:
        if not zones:
            raise ValueError("zones must not be empty")
        self.zones = zones

    def _find_zone(self, value: float) -> int:
        """Return the index of the first zone that contains *value*, or ``-1``."""
        for i, (lo, hi) in enumerate(self.zones):
            if lo <= value <= hi:
                return i
        return -1

    @abstractmethod
    def evaluate(self, request: ChatCompletionRequest) -> int:
        """Return the zone index for this request, or ``-1`` if none match."""


# ---------------------------------------------------------------------------
# RuleEngine: evaluation and aggregation of rule collections
# ---------------------------------------------------------------------------

class RuleEngine:
    """Engine for evaluating collections of rules and aggregating results.

    Provides static helper methods for common rule evaluation operations
    and aggregation strategies.
    """

    @staticmethod
    def _compare(value: float, threshold: float, operator: str) -> bool:
        """Compare *value* against *threshold* using the given operator string.

        Args:
            value: The value to compare.
            threshold: The threshold to compare against.
            operator: One of "gt", "gte", "lt", "lte", "eq".

        Returns:
            True if the comparison succeeds, False otherwise.

        Raises:
            ValueError: If *operator* is not recognized.
        """
        ops: dict = {
            "gt": value > threshold,
            "gte": value >= threshold,
            "lt": value < threshold,
            "lte": value <= threshold,
            "eq": value == threshold,
        }
        if operator not in ops:
            raise ValueError(f"Unknown operator '{operator}'. Use one of: {list(ops)}")
        return ops[operator]

    @staticmethod
    def _last_user_word_count(request: ChatCompletionRequest) -> int:
        """Return the word count of the last user message, or 0 if none.

        Handles both space-delimited and CJK scripts: whitespace-delimited runs
        are counted by splitting, while each CJK ideograph counts as a single
        word (CJK text is not whitespace-delimited). Mixed text is summed, e.g.
        ``"deploy 部署 the app"`` -> 3 latin words + 2 CJK chars = 5.

        Args:
            request: The chat completion request.

        Returns:
            Word count of the last user message, or 0.
        """
        for msg in reversed(request.messages):
            if msg.role == ChatCompletionRole.USER and msg.content:
                text = _content_text(msg.content)
                # CJK ideographs (Han): main block, Extension A, compatibility
                # ideographs, and Extension B+. re caches the compiled pattern.
                cjk = re.compile(
                    r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff\U00020000-\U0002ffff]"
                )
                # Each CJK char counts as one word (CJK is not space-delimited);
                # blank them out so they don't merge adjacent Latin tokens, then
                # add the remaining whitespace-delimited word count.
                cjk_count = len(cjk.findall(text))
                latin_count = len(cjk.sub(" ", text).split())
                return cjk_count + latin_count
        return 0

    @staticmethod
    def evaluate_all(
        rules: List[ValueRule], request: ChatCompletionRequest
    ) -> bool:
        """Evaluate a collection of value rules; return True if all pass.

        Args:
            rules: List of :class:`ValueRule` instances to evaluate.
            request: The request to evaluate against.

        Returns:
            ``True`` if all rules evaluate to ``True``, ``False`` otherwise.
        """
        return all(rule.evaluate(request) for rule in rules)

    @staticmethod
    def evaluate_any(
        rules: List[ValueRule], request: ChatCompletionRequest
    ) -> bool:
        """Evaluate a collection of value rules; return True if any pass.

        Args:
            rules: List of :class:`ValueRule` instances to evaluate.
            request: The request to evaluate against.

        Returns:
            ``True`` if any rule evaluates to ``True``, ``False`` otherwise.
        """
        return any(rule.evaluate(request) for rule in rules)

    @staticmethod
    def aggregate_scores(
        rules: List[ScoreRule], request: ChatCompletionRequest
    ) -> dict:
        """Evaluate score rules and return a mapping of rule class name to result.

        Args:
            rules: List of :class:`ScoreRule` instances to evaluate.
            request: The request to evaluate against.

        Returns:
            Dict mapping each rule's class name to its computed result.
        """
        return {rule.__class__.__name__: rule.evaluate(request) for rule in rules}

    @staticmethod
    def aggregate_zones(
        rules: List[ZoneRule], request: ChatCompletionRequest
    ) -> list:
        """Evaluate zone rules and return the zone indices.

        Args:
            rules: List of :class:`ZoneRule` instances to evaluate.
            request: The request to evaluate against.

        Returns:
            List of zone indices (or ``-1`` for no match), one per rule.
        """
        return [rule.evaluate(request) for rule in rules]


# ---------------------------------------------------------------------------
# Rule registry: rule-type name (as written in strategy.yaml) -> rule class
# ---------------------------------------------------------------------------

RULE_CLASS_REGISTRY: Dict[str, type[Rule]] = {}


def register_rule(rule_cls: type[Rule], *aliases: str) -> type[Rule]:
    """Register ``rule_cls`` under its class name and any ``aliases``."""
    for name in (rule_cls.__name__, *aliases):
        RULE_CLASS_REGISTRY[name] = rule_cls
    return rule_cls
