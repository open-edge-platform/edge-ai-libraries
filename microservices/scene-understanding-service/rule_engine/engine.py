# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""
Core rule evaluation engine.

Operates on generic context dicts — no imports from the parent service.
This entire package can be extracted into a standalone service.
"""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .loader import load_rules
from .models import Action


# Supported comparison operators
_OPS = {
    "eq": lambda a, b: a == b,
    "ne": lambda a, b: a != b,
    "gt": lambda a, b: a is not None and a > b,
    "gte": lambda a, b: a is not None and a >= b,
    "lt": lambda a, b: a is not None and a < b,
    "lte": lambda a, b: a is not None and a <= b,
}

# Regex for dynamic key references: zone_visit_counts[region_id]
_BRACKET_RE = re.compile(r"^(\w+)\[(\w+)\]$")


class RuleEngine:
    """YAML-driven rule evaluator.

    Evaluates declarative rules against a flat context dict.
    Returns a list of Action objects — the caller decides how to execute them.

    This class has ZERO imports from the parent service.
    """

    def __init__(
        self,
        rules_path: Optional[Path] = None,
        variables: Optional[Dict[str, Any]] = None,
        rules: Optional[List[dict]] = None,
    ) -> None:
        """Initialize the rule engine.

        Args:
            rules_path: Path to rules.yaml file.
            variables: Variable values for ${var:default} resolution.
            rules: Pre-loaded rule dicts (bypasses file loading, useful for tests).
        """
        if rules is not None:
            self._rules = rules
        elif rules_path is not None:
            self._rules = load_rules(rules_path, variables or {})
        else:
            self._rules = []

    @property
    def rules(self) -> List[dict]:
        """Return loaded rules (read-only view for inspection)."""
        return list(self._rules)

    def get_rule(self, rule_id: str) -> Optional[dict]:
        """Return a single rule by ID, or None."""
        for rule in self._rules:
            if rule["id"] == rule_id:
                return dict(rule)
        return None

    def is_rule_enabled(self, rule_id: str) -> bool:
        """Check if a rule exists and is enabled."""
        rule = self.get_rule(rule_id)
        return rule is not None and rule.get("enabled", True)

    def evaluate(
        self,
        event_type: str,
        zone_type: str,
        context: Dict[str, Any],
    ) -> List[Action]:
        """Evaluate all matching rules and return actions.

        Args:
            event_type: Trigger event type ("zone_entry", "zone_exit").
            zone_type: Zone type string ("HIGH_VALUE", "RESTRICTED", etc.).
            context: Flat dict of facts for condition evaluation.
                     e.g. {"visited_checkout": False, "dwell_seconds": 150,
                           "visit_count": 4, "region_id": "r1"}

        Returns:
            List of Action objects from all matching rules.
        """
        actions: List[Action] = []

        for rule in self._rules:
            if not rule.get("enabled", True):
                continue

            trigger = rule.get("trigger", {})

            # Match trigger event_type
            if trigger.get("event_type") != event_type:
                continue

            # Match trigger zone_type
            if trigger.get("zone_type") and trigger["zone_type"] != zone_type:
                continue

            # Evaluate all conditions (AND logic)
            conditions = rule.get("conditions", [])
            if all(self._evaluate_condition(c, context) for c in conditions):
                for action_def in rule.get("actions", []):
                    actions.append(Action(
                        type=action_def["type"],
                        params=dict(action_def.get("params", {})),
                        rule_id=rule["id"],
                    ))

        return actions

    # ---- condition evaluation ------------------------------------------------

    @staticmethod
    def _evaluate_condition(cond: dict, context: Dict[str, Any]) -> bool:
        """Evaluate a single {field, op, value} condition against context."""
        field_val = RuleEngine._resolve_field(cond["field"], context)
        op_fn = _OPS.get(cond["op"])
        if op_fn is None:
            return False
        return op_fn(field_val, cond["value"])

    @staticmethod
    def _resolve_field(field_expr: str, context: Dict[str, Any]) -> Any:
        """Resolve a field expression against the flat context dict.

        Supports:
          - Simple keys: "visited_checkout" → context["visited_checkout"]
          - Bracket keys: "zone_visit_counts[region_id]"
              → context["zone_visit_counts"][context["region_id"]]
        """
        m = _BRACKET_RE.match(field_expr)
        if m:
            collection_key, index_key = m.groups()
            collection = context.get(collection_key)
            index = context.get(index_key)
            if isinstance(collection, dict) and index is not None:
                return collection.get(index, 0)
            return None

        return context.get(field_expr)
