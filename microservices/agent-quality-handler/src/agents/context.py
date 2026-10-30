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

    ``agent_name`` and ``prompt_section`` identify which registry entry is
    being executed (populated from the matching ``AgentSpec``). The 4
    built-in agents ignore them (they already know who they are), but a
    shared, config-only implementation — :mod:`src.agents.generic_prompt_agent`
    — relies on them to find its own prompt text and config block, so a new
    agent can be registered purely via ``agents.yaml`` with no new Python
    file at all.
    """

    use_case_id: str
    config: dict[str, Any]
    prompts_dir: str | None = None
    min_id: int | None = None
    max_id: int | None = None
    upstream_results: dict[str, dict] = field(default_factory=dict)
    agent_name: str = ""
    prompt_section: str = ""

    def upstream(self, agent_name: str) -> dict:
        """Return the named upstream agent's result, or ``{}`` if absent."""
        result = self.upstream_results.get(agent_name, {})
        return result if isinstance(result, dict) else {}

    def agent_config(self) -> dict[str, Any]:
        """Return this agent's own config block (``config[self.agent_name]``).

        Lets a registry-only agent (e.g. :mod:`generic_prompt_agent`) read
        its per-agent settings the same way built-in agents read
        ``config.get("policy", {})`` etc., without needing a hardcoded key.
        """
        block = self.config.get(self.agent_name, {}) if self.agent_name else {}
        return block if isinstance(block, dict) else {}
