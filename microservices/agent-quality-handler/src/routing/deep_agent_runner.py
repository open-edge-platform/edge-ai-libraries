# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Deep Agent runner — wraps specialist agents as LangChain tools and uses an
OVMS structured-output plan (rather than native LLM tool-calling, which small
locally-served models often fail to emit) to drive LLM-mode routing.

The deep agent receives a routing decision (severity + route) and directly
invokes the selected specialist agents, guaranteeing they run.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from langchain_core.tools import tool

from ..agents import policy_agent, analysis_agent, evidence_agent, ticketing_agent
from ..agents.context import AgentContext
from .agent_registry import AgentSpec, load_registry, resolve_run_callable
from .route_utils import normalize_route
from .router import RoutingDecision

log = logging.getLogger(__name__)

_BUILTIN_TOOL_DOCSTRINGS: dict[str, str] = {
    "policy": (
        "Run the policy agent to generate inspection policies from detection data.\n"
        "        Call this when the routing decision includes 'policy' in the route."
    ),
    "analysis": (
        "Run the analysis agent to produce a structured analysis report.\n"
        "        Call this when the routing decision includes 'analysis' in the route.\n"
        "        Pass the policy result JSON string from run_policy_agent if available."
    ),
    "evidence": (
        "Run the evidence agent to build an audit trail for compliance.\n"
        "        Call this when the routing decision includes 'evidence' in the route."
    ),
    "ticketing": (
        "Run the ticketing agent to generate a maintenance ticket.\n"
        "        Call this when the routing decision includes 'ticketing' in the route.\n"
        "        Pass policy and analysis results as JSON strings."
    ),
}

_BUILTIN_TOOL_PARAMS: dict[str, tuple[str, ...]] = {
    "policy": ("reason",),
    "analysis": ("policy_result_json",),
    "evidence": ("reason",),
    "ticketing": ("policy_result_json", "analysis_result_json"),
}


def _tool_param_names(spec: AgentSpec) -> tuple[str, ...]:
    """Return the LLM-facing parameter names for ``spec``'s tool."""
    builtin = _BUILTIN_TOOL_PARAMS.get(spec.name)
    if builtin is not None:
        return builtin
    if spec.depends_on:
        return tuple(f"{dependency}_result_json" for dependency in spec.depends_on)
    return ("reason",)


def _tool_docstring(spec: AgentSpec) -> str:
    """Return the tool docstring for ``spec``."""
    builtin = _BUILTIN_TOOL_DOCSTRINGS.get(spec.name)
    if builtin is not None:
        return builtin

    title = spec.name.replace("_", " ")
    lines = [
        f"Run the {title} agent.",
        f"        Call this when the routing decision includes '{spec.name}' in the route.",
    ]
    if spec.depends_on:
        dependencies = ", ".join(spec.depends_on)
        lines.append(f"        Pass {dependencies} result JSON strings if available.")
    return "\n".join(lines)


def _build_tool_callable(tool_name: str, param_names: tuple[str, ...], docstring: str, runner):
    """Create a callable with the exact name/signature/docstring we need."""
    signature = ", ".join(
        f'{name}: str = {"" if name == "reason" else "{}"!r}' for name in param_names
    )
    arguments = ", ".join(f"{name}={name}" for name in param_names)
    source = (
        f"def _generated_tool({signature}) -> str:\n"
        f"    {docstring!r}\n"
        f"    return _runner({arguments})\n"
    )
    namespace = {"_runner": runner}
    exec(source, namespace)
    generated = namespace["_generated_tool"]
    generated.__name__ = tool_name
    return generated


def _make_agent_tool(
    spec: AgentSpec,
    use_case_id: str,
    config: dict,
    prompts_dir: str | None,
    min_id: int | None,
    max_id: int | None,
):
    """Create a bound LangChain tool for a registered specialist agent."""

    def _runner(**tool_inputs: str) -> str:
        try:
            upstream_results = {
                match.group("dependency"): json.loads(raw_value) if raw_value else {}
                for param_name, raw_value in tool_inputs.items()
                if (match := re.fullmatch(r"(?P<dependency>.+)_result_json", param_name))
            }
            context = AgentContext(
                use_case_id=use_case_id,
                config=config,
                prompts_dir=prompts_dir,
                min_id=min_id,
                max_id=max_id,
                upstream_results=upstream_results,
                agent_name=spec.name,
                prompt_section=spec.prompt_section,
            )
            result = resolve_run_callable(spec)(context)
            return json.dumps(result, default=str)
        except Exception as exc:
            log.error("%s agent tool failed: %s", spec.name.capitalize(), exc)
            return json.dumps({"error": str(exc), "agent": spec.name})

    tool_name = f"run_{spec.name}_agent"
    tool_callable = _build_tool_callable(
        tool_name=tool_name,
        param_names=_tool_param_names(spec),
        docstring=_tool_docstring(spec),
        runner=_runner,
    )
    return tool(tool_name)(tool_callable)


def build_tools(
    use_case_id: str,
    config: dict,
    prompts_dir: str | None,
    min_id: int | None,
    max_id: int | None,
) -> list:
    """Build LangChain tool list for the specialist agents."""
    return [
        _make_agent_tool(spec, use_case_id, config, prompts_dir, min_id, max_id)
        for spec in load_registry(config)
    ]


def run_deep_agent(
    routing_decision: RoutingDecision,
    use_case_id: str,
    config: dict,
    prompts_dir: str | None,
    min_id: int | None,
    max_id: int | None,
) -> dict[str, Any]:
    """Execute the deep agent with routing-aware tool invocation.

    Asks the LLM for a structured execution plan (via OVMS structured output)
    and then directly invokes the specialist-agent tools for every agent in
    the routing decision's route, guaranteeing they run even if the model's
    plan is incomplete or malformed.

    Falls back to plain direct sequential execution if anything unexpected
    (e.g. import errors) prevents the structured-plan path from running.
    """
    tools = build_tools(use_case_id, config, prompts_dir, min_id, max_id)

    try:
        return _run_with_deep_agent(routing_decision, tools, config)
    except ImportError:
        log.warning(
            "langchain_openai not available; falling back to direct tool execution"
        )
        return _run_tools_directly(routing_decision, tools)


def _run_with_deep_agent(
    routing_decision: RoutingDecision,
    tools: list,
    config: dict,
) -> dict[str, Any]:
    """Execute the deep agent's plan using OVMS structured output.

    Small, locally-served models frequently fail to emit OpenAI-style
    ``tool_calls`` (e.g. they answer conversationally or use a model-specific
    tag format the server's tool parser isn't configured for), so
    ``create_deep_agent()``'s native tool-calling loop can silently invoke no
    subagents at all.

    Instead, we ask the model for a structured execution plan using OVMS's
    guided/structured output (``response_format`` json-schema enforcement, see
    https://docs.openvino.ai/2025/model-server/ovms_structured_output.html),
    which is reliably honored even by small models. We then invoke the
    specialist-agent tools ourselves, guaranteeing every agent in the routing
    decision's route actually runs regardless of what the model returns.
    """
    from langchain_openai import ChatOpenAI
    from pydantic import BaseModel, Field

    from ..utility.runtime_config import load_runtime_settings

    settings = load_runtime_settings()

    model = ChatOpenAI(
        model=settings.llm_model_name,
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
    )

    route_list = ", ".join(routing_decision.route)

    class AgentInvocation(BaseModel):
            agent: str = Field(description=f"One of: {route_list}")
            reason: str = Field(default="", description="Why this agent runs next")

    class AgentExecutionPlan(BaseModel):
            calls: list[AgentInvocation] = Field(
                description="Ordered list of agents to invoke"
            )

    prompt = (
        f"You are an agentic predictive maintenance system. "
        f"A detection batch has been classified as {routing_decision.severity.value} severity.\n"
        f"Reason: {routing_decision.reason}\n\n"
        f"The allowed agents to execute, in the required order, are: {route_list}.\n"
        f"Return the execution plan as an ordered list of agent calls."
    )

    ordered_agents: list[str] = []
    try:
        plan = model.with_structured_output(AgentExecutionPlan).invoke(prompt)
        allowed = set(routing_decision.route)
        for call in plan.calls:
            if call.agent in allowed and call.agent not in ordered_agents:
                ordered_agents.append(call.agent)
    except Exception as exc:
        log.warning(
            "Structured execution plan generation failed (%s); using routing order",
            exc,
        )

    # Guarantee every agent in the routing decision runs, even if the model's
    # plan omitted some or structured output generation failed entirely.
    for agent_name in routing_decision.route:
        if agent_name not in ordered_agents:
            ordered_agents.append(agent_name)

    # Normalize: dedupe (already implied above, but kept for safety) and
    # guarantee ticketing runs after policy/analysis regardless of the order
    # the model's plan requested.
    normalized_agents = normalize_route(ordered_agents, load_registry(config))
    if normalized_agents != ordered_agents:
        log.info(
            "Deep-agent execution plan normalized for dependency-safety: "
            "plan_order=%s effective_order=%s",
            ordered_agents,
            normalized_agents,
        )
    ordered_agents = normalized_agents or routing_decision.route

    forced_route = RoutingDecision(
        severity=routing_decision.severity,
        reason=routing_decision.reason,
        route=ordered_agents,
        summary=routing_decision.summary,
    )
    results = _run_tools_directly(forced_route, tools)
    return {"routing": routing_decision.to_dict(), **results}


def _run_tools_directly(
    routing_decision: RoutingDecision,
    tools: list,
) -> dict[str, Any]:
    """Direct sequential execution as a fallback when deepagents is unavailable."""
    tool_map = {t.name: t for t in tools}
    results: dict[str, Any] = {}

    for agent_name in routing_decision.route:
        tool_name = f"run_{agent_name}_agent"
        tool_fn = tool_map.get(tool_name)
        if tool_fn is None:
            continue

        tool_inputs: dict[str, str] = {}
        for param_name in tool_fn.args:
            if param_name == "reason":
                tool_inputs[param_name] = routing_decision.reason
            elif param_name.endswith("_result_json"):
                dependency_name = param_name[: -len("_result_json")]
                tool_inputs[param_name] = json.dumps(
                    results.get(dependency_name, {}), default=str
                )

        raw = tool_fn.invoke(tool_inputs)

        try:
            results[agent_name] = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            results[agent_name] = {"raw": raw}

    return results
