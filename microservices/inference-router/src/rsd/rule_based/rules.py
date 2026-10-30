# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Policy-based (heuristic) rules: judge a request from its own features."""

from __future__ import annotations

import re
from typing import Any, List, Optional, Tuple

from src.models import ChatCompletionRequest
from src.rsd.engine.rule import (
    MatchRule,
    RuleEngine,
    ScoreRule,
    ZoneRule,
    _content_text,
    register_rule,
)


# ---------------------------------------------------------------------------
# Rule Definition
# ---------------------------------------------------------------------------
# MatchRules
# ---------------------------------------------------------------------------

class MessageContentRule(MatchRule):
    """Matches message content against a keyword or regex pattern.

    Args:
        pattern: Substring to search for (or regex when use_regex=True).
        use_regex: Compile pattern as a case-insensitive regular expression.
        roles: Restrict matching to messages with these roles (e.g. ["user"]).
               When None, all roles are checked.
    """

    def __init__(
        self,
        pattern: str,
        use_regex: bool = False,
        roles: Optional[List[str]] = None,
    ) -> None:
        self.pattern = pattern
        self.use_regex = use_regex
        self.roles: Optional[set] = {r.lower() for r in roles} if roles else None
        self._compiled: Optional[re.Pattern] = (
            re.compile(pattern, re.IGNORECASE) if use_regex else None
        )

    def evaluate(self, request: ChatCompletionRequest) -> bool:
        for msg in request.messages:
            if self.roles and msg.role.value not in self.roles:
                continue
            content = _content_text(msg.content)
            if self.use_regex:
                if self._compiled.search(content):
                    return True
            else:
                if self.pattern.lower() in content.lower():
                    return True
        return False


class ToolCallsRule(MatchRule):
    """Checks whether the request includes tool definitions.

    Args:
        require_tools: When True (default) rule passes if tools are present;
                       when False rule passes if tools are absent.
    """

    def __init__(self, require_tools: bool = True) -> None:
        self.require_tools = require_tools

    def evaluate(self, request: ChatCompletionRequest) -> bool:
        has_tools = bool(request.tools)
        return has_tools if self.require_tools else not has_tools


class MetadataRule(MatchRule):
    """Checks a key inside extra_body for an expected value.

    Supports dot-notation for nested keys, e.g. ``"routing.priority"``.

    Args:
        key: Dot-delimited path into extra_body.
        value: Expected value at that path.
    """

    def __init__(self, key: str, value: Any) -> None:
        self.key = key
        self.value = value

    def evaluate(self, request: ChatCompletionRequest) -> bool:
        body = request.extra_body or {}
        parts = self.key.split(".")
        node: Any = body
        for part in parts:
            if not isinstance(node, dict) or part not in node:
                return False
            node = node[part]
        return node == self.value


# ---------------------------------------------------------------------------
# Score (float) concrete rules
# ---------------------------------------------------------------------------

class QueryComplexityScoreRule(ScoreRule):
    """Compares a mocked query complexity score against a scored target.

    Args:
        score_range: ``(min_score, max_score)`` bounds for the mocked score.
        target: Raw target value converted into a target score.
        operator: Comparison operator: "gt", "gte", "lt", "lte", or "eq".
    """

    def __init__(
        self,
        score_range: Tuple[float, float],
        target: Any,
        operator: str = "gte",
    ) -> None:
        super().__init__(score_range, target, operator)

    def _request_to_score(self, request: ChatCompletionRequest) -> float:
        """Mock query complexity scoring hook."""
        return self._get_query_complexity_score(request)

    def _get_query_complexity_score(
        self,
        request: ChatCompletionRequest,
    ) -> float:
        """Mock query complexity scoring function."""
        lo, hi = self.score_range
        return lo + ((hi - lo) / 2)


# ---------------------------------------------------------------------------
# Zone (int) concrete rules
# ---------------------------------------------------------------------------

class QueryComplexityZoneRule(ZoneRule):
    """Maps last-user-message word count to a zone index.

    Args:
        zones: Ordered list of ``(lower_word_count, upper_word_count)`` inclusive
               bounds.  Example: ``[(0, 50), (51, 200), (201, float('inf'))]``.
    """

    def evaluate(self, request: ChatCompletionRequest) -> int:
        return self._find_zone(RuleEngine._last_user_word_count(request))


class ContextLengthRule(ZoneRule):
    """Maps total request message content length to a zone index."""

    def evaluate(self, request: ChatCompletionRequest) -> int:
        context_length = sum(len(_content_text(message.content)) for message in request.messages)
        return self._find_zone(context_length)


for _rule_cls in (
    MessageContentRule,
    ToolCallsRule,
    MetadataRule,
    QueryComplexityScoreRule,
    QueryComplexityZoneRule,
    ContextLengthRule,
):
    register_rule(_rule_cls)
