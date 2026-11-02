# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""
rule_engine — self-contained, YAML-driven rule evaluation package.

No imports from the parent service. Operates on generic context dicts
so it can be extracted into a standalone service later.
"""

from .engine import RuleEngine
from .models import Action

__all__ = ["RuleEngine", "Action"]
