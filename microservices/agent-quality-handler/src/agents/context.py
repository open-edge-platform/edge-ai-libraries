# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Shared execution context passed to every specialist agent's ``run``.

Phase 2 of the agent registry work standardizes each specialist agent
(built-in or registered via ``agent_registry`` in ``agents.yaml``) on a
single-argument ``run(context: AgentContext) -> dict`` signature. This is
what allows the execution graph, the deep-agent tool factory, and the
registry loader to invoke any agent generically, regardless of which
upstream agents' output it needs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AgentContext:
    """Everything a specialist agent needs to run once.

    ``upstream_results`` holds the outputs of agents this one depends on
    (per the registry's ``depends_on``), keyed by agent name — e.g. the
    built-in ``ticketing`` agent reads
    ``upstream_results.get("policy", {})`` and
    ``upstream_results.get("analysis", {})``.
    """

    use_case_id: str
    config: dict[str, Any]
    prompts_dir: str | None = None
    min_id: int | None = None
    max_id: int | None = None
    upstream_results: dict[str, dict] = field(default_factory=dict)

    def upstream(self, agent_name: str) -> dict:
        """Return the named upstream agent's result, or ``{}`` if absent."""
        result = self.upstream_results.get(agent_name, {})
        return result if isinstance(result, dict) else {}
