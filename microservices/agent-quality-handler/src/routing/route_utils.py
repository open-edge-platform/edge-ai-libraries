# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Shared helpers for normalizing LLM-produced agent routes.

Both ``router.py`` (severity classification) and ``deep_agent_runner.py``
(execution planning) let an LLM choose which specialist agents run and in
what order. Neither the router's route nor the deep agent's plan is
guaranteed to be well-formed: the model may return unknown agent names,
duplicate an agent, or place an agent before results it depends on.
``normalize_route`` fixes all three cases while otherwise preserving the
model's intended ordering (for example, independent agents such as
``evidence`` can still run before or after ``analysis``).
"""

from __future__ import annotations

from heapq import heappop, heappush

from .agent_registry import (
    DEFAULT_REGISTRY,
    AgentRegistryError,
    AgentSpec,
    topological_order,
)


def _validated_spec_map(specs: list[AgentSpec]) -> dict[str, AgentSpec]:
    """Return ``specs`` keyed by name after validating the registry shape."""
    spec_by_name: dict[str, AgentSpec] = {}
    for spec in specs:
        if spec.name in spec_by_name:
            raise AgentRegistryError(
                f"route_utils received duplicate agent spec name: '{spec.name}'"
            )
        spec_by_name[spec.name] = spec

    for spec in specs:
        unknown = [dep for dep in spec.depends_on if dep not in spec_by_name]
        if unknown:
            raise AgentRegistryError(
                f"route_utils received unknown dependency target(s) for '{spec.name}': {unknown}"
            )

    topological_order(specs)
    return spec_by_name


def _dependency_safe_order(
    route: list[str], spec_by_name: dict[str, AgentSpec]
) -> list[str]:
    """Return a stable topological ordering for the agents present in ``route``."""
    present = set(route)
    indegree = {name: 0 for name in route}
    dependents: dict[str, list[str]] = {name: [] for name in route}

    for name in route:
        for dependency in spec_by_name[name].depends_on:
            if dependency not in present:
                continue
            indegree[name] += 1
            dependents[dependency].append(name)

    original_index = {name: index for index, name in enumerate(route)}
    available: list[tuple[int, str]] = []
    for name in route:
        if indegree[name] == 0:
            heappush(available, (original_index[name], name))

    ordered: list[str] = []
    while available:
        _, name = heappop(available)
        ordered.append(name)
        for dependent in dependents[name]:
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                heappush(available, (original_index[dependent], dependent))

    if len(ordered) != len(route):
        raise AgentRegistryError(
            "route_utils could not normalize route because the registry contains a dependency cycle"
        )

    return ordered


def normalize_route(route: list[str], specs: list[AgentSpec] | None = None) -> list[str]:
    """Return a deduplicated, dependency-safe copy of ``route``.

    - Unknown agent names are dropped based on ``specs``.
    - Duplicates are removed, keeping each agent's first occurrence.
    - Any agent whose dependencies are also present is moved after them,
      transitively, while agents with no dependency relationship keep their
      relative order from the input route.

    When ``specs`` is omitted, :data:`DEFAULT_REGISTRY` is used so existing
    call sites preserve today's behavior with no changes.
    """
    registry = list(DEFAULT_REGISTRY) if specs is None else specs
    spec_by_name = _validated_spec_map(registry)

    deduped: list[str] = []
    seen: set[str] = set()
    for agent in route:
        if agent in spec_by_name and agent not in seen:
            seen.add(agent)
            deduped.append(agent)

    if len(deduped) < 2:
        return deduped

    return _dependency_safe_order(deduped, spec_by_name)
