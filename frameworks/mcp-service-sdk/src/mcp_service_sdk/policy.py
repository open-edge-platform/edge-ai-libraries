"""Policy gate (walkthrough §9) — deterministic code, NOT the LLM, decides
whether a proposed action may touch the store.

Every action tool is registered with a ``GateLevel``. Actions not on the
allow-list are BLOCKED. Rate limits and approval gates are enforced here, in
plain auditable code — never inside the model.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable


class GateLevel(str, Enum):
    AUTOMATIC = "automatic"        # executes immediately
    NOTIFY = "notify"              # surfaces to operator, never acts
    NEEDS_APPROVAL = "needs_approval"  # waits for explicit human yes
    BLOCKED = "blocked"            # refused and logged


@dataclass
class ActionSpec:
    """Declares one action tool and how the gate must treat it."""

    name: str
    level: GateLevel
    # Optional rate limit: at most ``max_calls`` within ``per_seconds``.
    max_calls: int | None = None
    per_seconds: float = 60.0
    _calls: deque[float] = field(default_factory=deque, repr=False)


@dataclass
class PolicyDecision:
    allowed: bool
    level: GateLevel
    reason: str


class PolicyGate:
    """Holds the action allow-list and renders a decision per proposed action."""

    def __init__(self, approver: Callable[[str, dict], bool] | None = None) -> None:
        self._actions: dict[str, ActionSpec] = {}
        # Injected human-approval callback; default denies until wired.
        self._approver = approver or (lambda name, args: False)

    def register(self, spec: ActionSpec) -> None:
        self._actions[spec.name] = spec

    def evaluate(self, action_name: str, args: dict) -> PolicyDecision:
        spec = self._actions.get(action_name)
        if spec is None:
            return PolicyDecision(False, GateLevel.BLOCKED, "not on allow-list")

        if spec.level is GateLevel.BLOCKED:
            return PolicyDecision(False, GateLevel.BLOCKED, "action is blocked")

        if spec.level is GateLevel.NOTIFY:
            return PolicyDecision(False, GateLevel.NOTIFY, "notify-only, no action")

        if not self._within_rate_limit(spec):
            return PolicyDecision(False, spec.level, "rate limit exceeded")

        if spec.level is GateLevel.NEEDS_APPROVAL:
            if self._approver(action_name, args):
                return PolicyDecision(True, spec.level, "human approved")
            return PolicyDecision(False, spec.level, "awaiting human approval")

        return PolicyDecision(True, GateLevel.AUTOMATIC, "auto-approved")

    def _within_rate_limit(self, spec: ActionSpec) -> bool:
        if spec.max_calls is None:
            return True
        now = time.monotonic()
        window_start = now - spec.per_seconds
        while spec._calls and spec._calls[0] < window_start:
            spec._calls.popleft()
        if len(spec._calls) >= spec.max_calls:
            return False
        spec._calls.append(now)
        return True
