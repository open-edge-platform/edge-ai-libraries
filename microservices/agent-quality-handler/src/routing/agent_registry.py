# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Config-driven specialist-agent registry.

Phase 1 (route_utils.py) hardcoded the set of specialist agents
(``policy``/``analysis``/``evidence``/``ticketing``) and ticketing's
dependency on policy+analysis. This module generalizes that: the agent set,
each agent's implementation module, and its dependencies are declared in
``agents.yaml`` under an optional ``agent_registry`` key.

If ``agent_registry`` is absent (the common case today), :func:`load_registry`
returns :data:`DEFAULT_REGISTRY` — the same four built-in agents with their
existing dependency shape — so every existing deployment keeps working
unmodified with zero config changes.

This module only loads and validates the registry (schema, uniqueness,
dependency existence, cycle detection) and resolves each agent's ``run``
callable. Wiring it into the execution graph, route normalization, deep-agent
tool generation, and output storage happens in later phases.
"""

from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

log = logging.getLogger(__name__)


class AgentRegistryError(ValueError):
    """Raised when the configured agent registry is invalid."""


@dataclass(frozen=True)
class AgentSpec:
    """One registered specialist agent."""

    name: str
    module: str
    depends_on: tuple[str, ...] = field(default_factory=tuple)
    prompt_section: str = ""

    def __post_init__(self):
        if not self.prompt_section:
            object.__setattr__(self, "prompt_section", self.name.upper())


# The four built-in specialists, in their existing dependency shape:
# ticketing reads policy + analysis output; policy/analysis/evidence have no
# dependency on one another. Order here is insertion order only — actual
# execution order is derived via topological_order().
DEFAULT_REGISTRY: tuple[AgentSpec, ...] = (
    AgentSpec(name="policy", module="src.agents.policy_agent", depends_on=(), prompt_section="POLICY"),
    AgentSpec(name="analysis", module="src.agents.analysis_agent", depends_on=(), prompt_section="ANALYSIS"),
    AgentSpec(name="evidence", module="src.agents.evidence_agent", depends_on=(), prompt_section="EVIDENCE"),
    AgentSpec(
        name="ticketing",
        module="src.agents.ticketing_agent",
        depends_on=("policy", "analysis"),
        prompt_section="TICKETING",
    ),
)


def _parse_entry(entry: Any) -> AgentSpec:
    if not isinstance(entry, dict):
        raise AgentRegistryError(f"agent_registry entry must be a mapping, got {type(entry).__name__}")

    name = entry.get("name")
    if not isinstance(name, str) or not name.strip():
        raise AgentRegistryError("agent_registry entry is missing a non-empty 'name'")
    name = name.strip()

    module = entry.get("module")
    if not isinstance(module, str) or not module.strip():
        raise AgentRegistryError(f"agent_registry entry '{name}' is missing a non-empty 'module'")

    depends_on = entry.get("depends_on", [])
    if not isinstance(depends_on, list) or not all(isinstance(d, str) for d in depends_on):
        raise AgentRegistryError(f"agent_registry entry '{name}' has invalid 'depends_on' (must be a list of strings)")

    prompt_section = entry.get("prompt_section", "")
    if not isinstance(prompt_section, str):
        raise AgentRegistryError(f"agent_registry entry '{name}' has invalid 'prompt_section' (must be a string)")

    return AgentSpec(
        name=name,
        module=module.strip(),
        depends_on=tuple(d.strip() for d in depends_on),
        prompt_section=prompt_section.strip(),
    )


def _validate(specs: list[AgentSpec]) -> None:
    names = [spec.name for spec in specs]
    seen: set[str] = set()
    for name in names:
        if name in seen:
            raise AgentRegistryError(f"agent_registry has a duplicate agent name: '{name}'")
        seen.add(name)

    for spec in specs:
        unknown = [dep for dep in spec.depends_on if dep not in seen]
        if unknown:
            raise AgentRegistryError(
                f"agent_registry entry '{spec.name}' depends_on unknown agent(s): {unknown}"
            )
        if spec.name in spec.depends_on:
            raise AgentRegistryError(f"agent_registry entry '{spec.name}' cannot depend on itself")

    # Cycle detection is a side effect of requiring topological_order() to
    # succeed; run it here so invalid registries fail fast at load time.
    topological_order(specs)


def load_registry(config: dict[str, Any] | None) -> list[AgentSpec]:
    """Return the validated agent registry from ``config``.

    Returns :data:`DEFAULT_REGISTRY` (as a list) when ``config`` has no
    ``agent_registry`` key, preserving today's behavior with zero config
    changes required.
    """
    raw_entries = (config or {}).get("agent_registry")
    if not raw_entries:
        return list(DEFAULT_REGISTRY)

    if not isinstance(raw_entries, list):
        raise AgentRegistryError("agent_registry must be a list of agent entries")

    specs = [_parse_entry(entry) for entry in raw_entries]
    _validate(specs)
    return specs


def topological_order(specs: list[AgentSpec]) -> list[str]:
    """Return agent names ordered so each agent follows all of its dependencies.

    Ties (agents with no relative dependency) are broken by the order the
    specs were declared in, so behavior stays deterministic and matches
    declaration order when there's no dependency constraint to enforce.
    """
    spec_by_name = {spec.name: spec for spec in specs}
    order: list[str] = []
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(name: str) -> None:
        if name in visited:
            return
        if name in visiting:
            raise AgentRegistryError(f"agent_registry has a dependency cycle involving '{name}'")
        visiting.add(name)
        for dependency in spec_by_name[name].depends_on:
            visit(dependency)
        visiting.discard(name)
        visited.add(name)
        order.append(name)

    for spec in specs:
        visit(spec.name)
    return order


def resolve_run_callable(spec: AgentSpec) -> Callable[..., dict]:
    """Import ``spec.module`` and return its ``run`` callable.

    Raises :class:`AgentRegistryError` if the module cannot be imported or
    does not expose a callable ``run`` attribute.
    """
    try:
        module = importlib.import_module(spec.module)
    except ImportError as exc:
        raise AgentRegistryError(
            f"agent_registry entry '{spec.name}' has unimportable module '{spec.module}': {exc}"
        ) from exc

    run = getattr(module, "run", None)
    if not callable(run):
        raise AgentRegistryError(
            f"agent_registry entry '{spec.name}' module '{spec.module}' has no callable 'run'"
        )
    return run
