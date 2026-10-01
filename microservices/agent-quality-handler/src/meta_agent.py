# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Meta-agent orchestration for the configured use case.

Supports two orchestration modes (controlled by ``AGENT_MODE``):

* **routing** (default) — A router node classifies severity from detection
  data, then conditionally dispatches to the subset of specialist agents
  required. In LLM mode the deep-agent runner delegates via
  ``create_deep_agent()``; in fallback mode the same rule-based agents run
  but only when the route includes them.

* **sequential** — The legacy linear chain that always runs every registered
  agent in dependency-safe registry order.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from typing import Any, Callable, Literal, TypedDict

from langgraph.graph import END, StateGraph

from .agents import analysis_agent, evidence_agent, policy_agent, ticketing_agent
from .agents.context import AgentContext
from .routing.agent_registry import (
    AgentSpec,
    load_registry,
    resolve_run_callable,
    topological_order,
)
from .routing.deep_agent_runner import run_deep_agent
from .routing.router import RoutingDecision, Severity, classify
from .utility.config_loader import get_use_case_id, load_config
from .utility.llm_client import is_fallback_mode
from .utility.runtime_config import load_runtime_settings

log = logging.getLogger(__name__)


_BUILTIN_RESULT_KEYS = {
    "policy": "policy_result",
    "analysis": "analysis_result",
    "evidence": "evidence_result",
    "ticketing": "ticket_result",
}
_ROUTE_END = "__end__"
_DEEP_AGENT_NODE = "deep_agent"


class AgentState(TypedDict):
    use_case_id: str
    config: dict
    prompts_dir: str | None
    min_id: int | None
    max_id: int | None
    routing_decision: dict
    policy_result: dict
    analysis_result: dict
    evidence_result: dict
    ticket_result: dict
    extra_agent_results: dict[str, dict]
    errors: list[dict[str, Any]]


GraphMode = Literal["sequential", "routing", "deep_agent"]
GraphKey = tuple[
    GraphMode,
    tuple[tuple[str, str, tuple[str, ...], str], ...],
]


def _failure(agent: str, exc: Exception) -> dict[str, Any]:
    return {
        "agent": agent,
        "status": "failed",
        "type": type(exc).__name__,
        "message": str(exc),
    }


def _validated_result(agent: str, result: Any) -> dict[str, Any]:
    if not isinstance(result, Mapping):
        raise TypeError(
            f"{agent.title()} agent returned {type(result).__name__}; expected a mapping"
        )
    return dict(result)


def _failed_dependencies(state: AgentState, spec: AgentSpec) -> AgentState | None:
    failed = [
        dependency
        for dependency in spec.depends_on
        if any(
            error["agent"] == dependency
            and error["status"] in {"failed", "skipped"}
            for error in state["errors"]
        )
    ]
    if not failed:
        return None

    detail = {
        "agent": spec.name,
        "status": "skipped",
        "type": "dependency_failure",
        "message": f"Skipped because prerequisites failed: {', '.join(failed)}",
        "dependencies": failed,
    }
    log.warning("%s agent skipped: failed prerequisites %s", spec.name.title(), failed)
    return {**state, "errors": [*state["errors"], detail]}


def _context(state: AgentState, upstream_results: dict[str, dict] | None = None) -> AgentContext:
    return AgentContext(
        use_case_id=state["use_case_id"],
        config=state["config"],
        prompts_dir=state.get("prompts_dir"),
        min_id=state.get("min_id"),
        max_id=state.get("max_id"),
        upstream_results=upstream_results or {},
    )


def _get_agent_result(state: AgentState, agent_name: str) -> dict[str, Any]:
    result_key = _BUILTIN_RESULT_KEYS.get(agent_name)
    if result_key is not None:
        result = state.get(result_key, {})
        return result if isinstance(result, dict) else {}

    extra_results = state.get("extra_agent_results", {})
    result = extra_results.get(agent_name, {})
    return result if isinstance(result, dict) else {}


def _store_agent_result(
    state: AgentState,
    agent_name: str,
    result: dict[str, Any],
) -> AgentState:
    result_key = _BUILTIN_RESULT_KEYS.get(agent_name)
    if result_key is not None:
        return {**state, result_key: result}

    extra_results = dict(state.get("extra_agent_results", {}))
    extra_results[agent_name] = result
    return {**state, "extra_agent_results": extra_results}


def _make_agent_node(spec: AgentSpec) -> Callable[[AgentState], AgentState]:
    run_agent = resolve_run_callable(spec)

    def _run_agent_node(state: AgentState) -> AgentState:
        skipped = _failed_dependencies(state, spec)
        if skipped is not None:
            return skipped

        upstream_results = {
            dependency: _get_agent_result(state, dependency)
            for dependency in spec.depends_on
        }
        try:
            result = run_agent(_context(state, upstream_results))
            return _store_agent_result(
                state,
                spec.name,
                _validated_result(spec.name, result),
            )
        except Exception as exc:
            log.error("%s agent failed: %s", spec.name.title(), exc)
            return {**state, "errors": [*state["errors"], _failure(spec.name, exc)]}

    return _run_agent_node


# ---------------------------------------------------------------------------
# Router and deep-agent nodes
# ---------------------------------------------------------------------------


def _run_router(state: AgentState) -> AgentState:
    """Classify severity and store the routing decision."""
    try:
        decision = classify(
            state["use_case_id"],
            state["config"],
            state.get("prompts_dir"),
            state.get("min_id"),
            state.get("max_id"),
        )
        log.info(
            "Router classified severity=%s route=%s",
            decision.severity.value,
            decision.route,
        )
        return {**state, "routing_decision": decision.to_dict()}
    except Exception as exc:
        log.error("Router failed: %s — defaulting to full pipeline", exc)
        fallback_decision = RoutingDecision(
            severity=Severity.HIGH,
            reason=f"Router error ({exc}); defaulting to HIGH",
            route=["policy", "analysis", "evidence", "ticketing"],
            summary={},
        )
        return {
            **state,
            "routing_decision": fallback_decision.to_dict(),
            "errors": [*state["errors"], _failure("router", exc)],
        }


def _run_deep_agent_node(state: AgentState) -> AgentState:
    """Run the deep agent with routing-aware tool invocation."""
    routing_dict = state.get("routing_decision", {})
    decision = RoutingDecision(
        severity=Severity(routing_dict.get("severity", "HIGH")),
        reason=routing_dict.get("reason", ""),
        route=routing_dict.get("route", ["policy", "analysis", "evidence", "ticketing"]),
        summary={},
    )
    try:
        results = run_deep_agent(
            decision,
            state["use_case_id"],
            state["config"],
            state.get("prompts_dir"),
            state.get("min_id"),
            state.get("max_id"),
        )
        next_state = state
        for agent_name, state_key in _BUILTIN_RESULT_KEYS.items():
            next_state = {
                **next_state,
                state_key: results.get(agent_name, next_state.get(state_key, {})),
            }

        extra_results = dict(next_state.get("extra_agent_results", {}))
        for agent_name, result in results.items():
            if agent_name not in _BUILTIN_RESULT_KEYS and agent_name != "routing" and isinstance(result, dict):
                extra_results[agent_name] = result
        if extra_results != next_state.get("extra_agent_results", {}):
            next_state = {**next_state, "extra_agent_results": extra_results}
        return next_state
    except Exception as exc:
        log.error("Deep agent failed: %s", exc)
        return {**state, "errors": [*state["errors"], _failure("deep_agent", exc)]}


# ---------------------------------------------------------------------------
# Generic graph construction
# ---------------------------------------------------------------------------


def _route_targets(
    state: AgentState,
    allowed_names: Sequence[str],
) -> list[str]:
    allowed = set(allowed_names)
    route = state.get("routing_decision", {}).get("route", [])
    return [name for name in route if name in allowed]


def _make_route_selector(
    current_name: str | None,
    allowed_names: Sequence[str],
    *,
    default_target: str,
) -> Callable[[AgentState], str]:
    def _select_next(state: AgentState) -> str:
        route = _route_targets(state, allowed_names)
        if not route:
            return default_target
        if current_name is None:
            return route[0]
        try:
            index = route.index(current_name)
        except ValueError:
            return route[0]
        return route[index + 1] if index + 1 < len(route) else _ROUTE_END

    return _select_next


def _build_graph(mode: GraphMode, specs: list[AgentSpec]) -> Any:
    ordered_names = topological_order(specs)
    spec_by_name = {spec.name: spec for spec in specs}
    g = StateGraph(AgentState)

    if mode == "sequential":
        for agent_name in ordered_names:
            g.add_node(agent_name, _make_agent_node(spec_by_name[agent_name]))
        g.set_entry_point(ordered_names[0])
        for current_name, next_name in zip(ordered_names, ordered_names[1:]):
            g.add_edge(current_name, next_name)
        g.add_edge(ordered_names[-1], END)
        return g.compile()

    g.add_node("router", _run_router)
    g.set_entry_point("router")

    if mode == "deep_agent":
        g.add_node(_DEEP_AGENT_NODE, _run_deep_agent_node)
        g.add_edge("router", _DEEP_AGENT_NODE)
        g.add_edge(_DEEP_AGENT_NODE, END)
        return g.compile()

    for agent_name in ordered_names:
        g.add_node(agent_name, _make_agent_node(spec_by_name[agent_name]))

    default_target = ordered_names[-1]
    targets = {name: name for name in ordered_names}
    targets[_ROUTE_END] = END
    g.add_conditional_edges(
        "router",
        _make_route_selector(None, ordered_names, default_target=default_target),
        targets,
    )
    for agent_name in ordered_names:
        g.add_conditional_edges(
            agent_name,
            _make_route_selector(agent_name, ordered_names, default_target=_ROUTE_END),
            targets,
        )
    return g.compile()


# Module-level compiled graphs — loaded once per mode+registry shape.
_graphs: dict[GraphKey, Any] = {}


def _graph_mode(mode: str) -> GraphMode:
    if mode == "sequential":
        return "sequential"
    if mode == "routing" and not is_fallback_mode():
        return "deep_agent"
    return "routing"


def _graph_key(mode: GraphMode, specs: list[AgentSpec]) -> GraphKey:
    return (
        mode,
        tuple(
            (spec.name, spec.module, tuple(spec.depends_on), spec.prompt_section)
            for spec in specs
        ),
    )


def get_graph(mode: str | None = None, config: dict[str, Any] | None = None):
    """Return the compiled graph for the requested orchestration mode."""
    if mode is None:
        settings = load_runtime_settings()
        mode = settings.agent_mode

    specs = load_registry(config)
    graph_mode = _graph_mode(mode)
    key = _graph_key(graph_mode, specs)
    if key not in _graphs:
        _graphs[key] = _build_graph(graph_mode, specs)
    return _graphs[key]


def run_pipeline(
    config_path: str | None = None,
    prompts_dir: str | None = None,
    min_id: int | None = None,
    max_id: int | None = None,
) -> dict[str, Any]:
    """Run the full multi-agent pipeline and return all agent outputs."""
    config = load_config(config_path)
    use_case_id = get_use_case_id(config)

    initial_state: AgentState = {
        "use_case_id": use_case_id,
        "config": config,
        "prompts_dir": prompts_dir,
        "min_id": min_id,
        "max_id": max_id,
        "routing_decision": {},
        "policy_result": {},
        "analysis_result": {},
        "evidence_result": {},
        "ticket_result": {},
        "extra_agent_results": {},
        "errors": [],
    }

    graph = get_graph(config=config)
    final_state = graph.invoke(initial_state)
    errors = final_state.get("errors", [])
    result = {
        "use_case_id": use_case_id,
        "routing": final_state.get("routing_decision", {}),
        "policy": final_state.get("policy_result", {}),
        "analysis": final_state.get("analysis_result", {}),
        "evidence": final_state.get("evidence_result", {}),
        "ticket": final_state.get("ticket_result", {}),
        "errors": errors,
        # Retained as a compatibility alias; structured details live in errors.
        "error": errors[0]["message"] if errors else None,
    }
    extra_agents = final_state.get("extra_agent_results", {})
    if extra_agents:
        result["extra_agents"] = extra_agents
    return result
