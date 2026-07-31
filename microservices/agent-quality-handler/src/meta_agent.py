# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Meta-agent orchestration for the configured use case."""

import logging
from collections.abc import Mapping
from typing import Any, TypedDict

from langgraph.graph import StateGraph, END

from .agents import policy_agent, analysis_agent, evidence_agent, ticketing_agent
from .utility.config_loader import load_config, get_use_case_id

log = logging.getLogger(__name__)


class AgentState(TypedDict):
    use_case_id: str
    config: dict
    prompts_dir: str | None
    min_id: int | None
    max_id: int | None
    policy_result: dict
    analysis_result: dict
    evidence_result: dict
    ticket_result: dict
    errors: list[dict[str, Any]]


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


def _failed_dependencies(
    state: AgentState, agent: str, dependencies: tuple[str, ...]
) -> AgentState | None:
    failed = [
        dependency
        for dependency in dependencies
        if any(
            error["agent"] == dependency
            and error["status"] in {"failed", "skipped"}
            for error in state["errors"]
        )
    ]
    if not failed:
        return None

    detail = {
        "agent": agent,
        "status": "skipped",
        "type": "dependency_failure",
        "message": f"Skipped because prerequisites failed: {', '.join(failed)}",
        "dependencies": failed,
    }
    log.warning("%s agent skipped: failed prerequisites %s", agent.title(), failed)
    return {**state, "errors": [*state["errors"], detail]}


def _run_policy(state: AgentState) -> AgentState:
    try:
        result = policy_agent.run(
            state["use_case_id"],
            state["config"],
            state.get("prompts_dir"),
            state.get("min_id"),
            state.get("max_id"),
        )
        return {**state, "policy_result": _validated_result("policy", result)}
    except Exception as exc:
        log.error("Policy agent failed: %s", exc)
        return {**state, "errors": [*state["errors"], _failure("policy", exc)]}


def _run_analysis(state: AgentState) -> AgentState:
    try:
        result = analysis_agent.run(
            state["use_case_id"],
            state["config"],
            state.get("prompts_dir"),
            None,
            state.get("min_id"),
            state.get("max_id"),
        )
        return {**state, "analysis_result": _validated_result("analysis", result)}
    except Exception as exc:
        log.error("Analysis agent failed: %s", exc)
        return {**state, "errors": [*state["errors"], _failure("analysis", exc)]}


def _run_evidence(state: AgentState) -> AgentState:
    try:
        result = evidence_agent.run(
            state["use_case_id"],
            state["config"],
            state.get("prompts_dir"),
            state.get("min_id"),
            state.get("max_id"),
        )
        return {**state, "evidence_result": _validated_result("evidence", result)}
    except Exception as exc:
        log.error("Evidence agent failed: %s", exc)
        return {**state, "errors": [*state["errors"], _failure("evidence", exc)]}


def _run_ticketing(state: AgentState) -> AgentState:
    skipped = _failed_dependencies(state, "ticketing", ("policy", "analysis"))
    if skipped is not None:
        return skipped
    try:
        result = ticketing_agent.run(
            state["use_case_id"],
            state["config"],
            state["policy_result"],
            state["analysis_result"],
            state.get("prompts_dir"),
        )
        return {**state, "ticket_result": _validated_result("ticketing", result)}
    except Exception as exc:
        log.error("Ticketing agent failed: %s", exc)
        return {**state, "errors": [*state["errors"], _failure("ticketing", exc)]}


def _build_graph() -> Any:
    g = StateGraph(AgentState)
    g.add_node("policy",   _run_policy)
    g.add_node("analysis", _run_analysis)
    g.add_node("evidence", _run_evidence)
    g.add_node("ticketing", _run_ticketing)

    # Keep independent work running after failures; ticketing validates its
    # explicit prerequisites before it executes.
    g.set_entry_point("policy")
    g.add_edge("policy",   "analysis")
    g.add_edge("analysis", "evidence")
    g.add_edge("evidence", "ticketing")
    g.add_edge("ticketing", END)
    return g.compile()


# Module-level compiled graph — loaded once at startup.
_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = _build_graph()
    return _graph


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
        "policy_result": {},
        "analysis_result": {},
        "evidence_result": {},
        "ticket_result": {},
        "errors": [],
    }

    graph = get_graph()
    final_state = graph.invoke(initial_state)
    errors = final_state.get("errors", [])
    return {
        "use_case_id": use_case_id,
        "policy":   final_state.get("policy_result", {}),
        "analysis": final_state.get("analysis_result", {}),
        "evidence": final_state.get("evidence_result", {}),
        "ticket":   final_state.get("ticket_result", {}),
        "errors": errors,
        # Retained as a compatibility alias; structured details live in errors.
        "error": errors[0]["message"] if errors else None,
    }
