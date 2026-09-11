# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Meta-agent — LangGraph orchestrator coordinating the four worker agents."""

import logging
from typing import Any, TypedDict

from langgraph.graph import StateGraph, END

from .agents import policy_agent, analysis_agent, evidence_agent, ticketing_agent
from .utility.config_loader import load_config, get_use_case_id

log = logging.getLogger(__name__)


class AgentState(TypedDict):
    use_case_id: str
    config: dict
    prompts_dir: str | None
    policy_result: dict
    analysis_result: dict
    evidence_result: dict
    ticket_result: dict
    error: str | None


def _run_policy(state: AgentState) -> AgentState:
    try:
        result = policy_agent.run(
            state["use_case_id"], state["config"], state.get("prompts_dir")
        )
        return {**state, "policy_result": result}
    except Exception as exc:
        log.error("Policy agent failed: %s", exc)
        return {**state, "policy_result": {}, "error": str(exc)}


def _run_analysis(state: AgentState) -> AgentState:
    try:
        min_conf = state["config"].get("analysis", {}).get("min_confidence", 0.5)
        result = analysis_agent.run(
            state["use_case_id"], state["config"], state.get("prompts_dir"), min_conf
        )
        return {**state, "analysis_result": result}
    except Exception as exc:
        log.error("Analysis agent failed: %s", exc)
        return {**state, "analysis_result": {}, "error": str(exc)}


def _run_evidence(state: AgentState) -> AgentState:
    try:
        result = evidence_agent.run(
            state["use_case_id"], state["config"], state.get("prompts_dir")
        )
        return {**state, "evidence_result": result}
    except Exception as exc:
        log.error("Evidence agent failed: %s", exc)
        return {**state, "evidence_result": {}, "error": str(exc)}


def _run_ticketing(state: AgentState) -> AgentState:
    try:
        result = ticketing_agent.run(
            state["use_case_id"],
            state["config"],
            state["policy_result"],
            state["analysis_result"],
            state.get("prompts_dir"),
        )
        return {**state, "ticket_result": result}
    except Exception as exc:
        log.error("Ticketing agent failed: %s", exc)
        return {**state, "ticket_result": {}, "error": str(exc)}


def _build_graph() -> Any:
    g = StateGraph(AgentState)
    g.add_node("policy",   _run_policy)
    g.add_node("analysis", _run_analysis)
    g.add_node("evidence", _run_evidence)
    g.add_node("ticketing", _run_ticketing)

    # Policy and analysis run first (they can be parallel in future);
    # evidence runs after analysis; ticketing is last (needs policy + analysis).
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
) -> dict[str, Any]:
    """Run the full multi-agent pipeline and return all agent outputs."""
    config = load_config(config_path)
    use_case_id = get_use_case_id(config)

    initial_state: AgentState = {
        "use_case_id": use_case_id,
        "config": config,
        "prompts_dir": prompts_dir,
        "policy_result": {},
        "analysis_result": {},
        "evidence_result": {},
        "ticket_result": {},
        "error": None,
    }

    graph = get_graph()
    final_state = graph.invoke(initial_state)
    return {
        "use_case_id": use_case_id,
        "policy":   final_state.get("policy_result", {}),
        "analysis": final_state.get("analysis_result", {}),
        "evidence": final_state.get("evidence_result", {}),
        "ticket":   final_state.get("ticket_result", {}),
        "error":    final_state.get("error"),
    }
