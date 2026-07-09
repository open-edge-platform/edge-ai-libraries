# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Data models for the rule engine — no parent-service imports."""

from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class Action:
    """Generic action returned by rule evaluation."""
    type: str                       # "alert" or "escalate"
    params: Dict[str, Any] = field(default_factory=dict)
    rule_id: str = ""
