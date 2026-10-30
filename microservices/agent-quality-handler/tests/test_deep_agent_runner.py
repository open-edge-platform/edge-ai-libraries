# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for the deep-agent runner's route execution and plan normalization."""

import sys
import types

from src.routing.deep_agent_runner import build_tools, _run_tools_directly, _run_with_deep_agent
from src.routing.router import RoutingDecision, Severity


# ── build_tools — schema stability and registry expansion ────────────────────

def test_build_tools_preserves_builtin_tool_schemas():
    tools = build_tools("case", {}, None, None, None)

    assert [
        (tool.name, list(tool.args.keys()), tool.description)
        for tool in tools
    ] == [
        (
            "run_policy_agent",
            ["reason"],
            "Run the policy agent to generate inspection policies from detection data.\n"
            "        Call this when the routing decision includes 'policy' in the route.",
        ),
        (
            "run_analysis_agent",
            ["policy_result_json"],
            "Run the analysis agent to produce a structured analysis report.\n"
            "        Call this when the routing decision includes 'analysis' in the route.\n"
            "        Pass the policy result JSON string from run_policy_agent if available.",
        ),
        (
            "run_evidence_agent",
            ["reason"],
            "Run the evidence agent to build an audit trail for compliance.\n"
            "        Call this when the routing decision includes 'evidence' in the route.",
        ),
        (
            "run_ticketing_agent",
            ["policy_result_json", "analysis_result_json"],
            "Run the ticketing agent to generate a maintenance ticket.\n"
            "        Call this when the routing decision includes 'ticketing' in the route.\n"
            "        Pass policy and analysis results as JSON strings.",
        ),
    ]


def test_build_tools_supports_registry_defined_agent(monkeypatch):
    import src.routing.deep_agent_runner as dar

    monkeypatch.setattr(dar.policy_agent, "run", lambda *a, **k: {"recommendation": "HALT_PIPELINE"})

    custom_module = types.ModuleType("tests.fake_followup_agent")
    captured = {}

    def fake_followup_run(context):
        captured["policy_result"] = context.upstream("policy")
        return {"followup": "queued"}

    custom_module.run = fake_followup_run
    monkeypatch.setitem(sys.modules, "tests.fake_followup_agent", custom_module)

    config = {
        "agent_registry": [
            {
                "name": "policy",
                "module": "src.agents.policy_agent",
                "depends_on": [],
                "prompt_section": "POLICY",
            },
            {
                "name": "followup",
                "module": "tests.fake_followup_agent",
                "depends_on": ["policy"],
                "prompt_section": "FOLLOWUP",
            },
        ]
    }

    tools = build_tools("case", config, None, None, None)
    assert [(tool.name, list(tool.args.keys())) for tool in tools] == [
        ("run_policy_agent", ["reason"]),
        ("run_followup_agent", ["policy_result_json"]),
    ]

    decision = RoutingDecision(
        severity=Severity.HIGH,
        reason="test",
        route=["policy", "followup"],
        summary={},
    )
    results = _run_tools_directly(decision, tools)

    assert captured["policy_result"] == {"recommendation": "HALT_PIPELINE"}
    assert results["followup"] == {"followup": "queued"}


def test_build_tools_resolves_run_callable_at_invocation_time(monkeypatch):
    import src.routing.deep_agent_runner as dar

    tools = build_tools("case", {}, None, None, None)
    monkeypatch.setattr(dar.policy_agent, "run", lambda *a, **k: {"late_patch": True})

    decision = RoutingDecision(
        severity=Severity.MEDIUM,
        reason="late patch",
        route=["policy"],
        summary={},
    )

    assert _run_tools_directly(decision, tools)["policy"] == {"late_patch": True}


# ── _run_tools_directly — data threading across agents ───────────────────────

def test_run_tools_directly_threads_policy_and_analysis_into_ticketing(monkeypatch):
    import src.routing.deep_agent_runner as dar

    monkeypatch.setattr(
        dar.policy_agent, "run",
        lambda *args, **kwargs: {"recommendation": "HALT_PIPELINE"},
    )
    monkeypatch.setattr(
        dar.analysis_agent, "run",
        lambda *args, **kwargs: {"total_detections": 12},
    )
    captured_ticket_inputs = {}

    def fake_ticketing_run(context):
        captured_ticket_inputs["policy_result"] = context.upstream("policy")
        captured_ticket_inputs["analysis_result"] = context.upstream("analysis")
        return {"ticket_id": "T-1"}

    monkeypatch.setattr(dar.ticketing_agent, "run", fake_ticketing_run)

    tools = build_tools("case", {}, None, None, None)
    decision = RoutingDecision(
        severity=Severity.HIGH,
        reason="test",
        route=["policy", "analysis", "ticketing"],
        summary={},
    )
    results = _run_tools_directly(decision, tools)

    assert results["policy"] == {"recommendation": "HALT_PIPELINE"}
    assert results["analysis"] == {"total_detections": 12}
    assert results["ticketing"] == {"ticket_id": "T-1"}
    assert captured_ticket_inputs["policy_result"] == {"recommendation": "HALT_PIPELINE"}
    assert captured_ticket_inputs["analysis_result"] == {"total_detections": 12}


def test_run_tools_directly_ticketing_first_gets_empty_context(monkeypatch):
    """Documents that _run_tools_directly executes routes verbatim — it does
    not self-correct dependency ordering. Safety must come from
    normalize_route() being applied before this function is called (see
    _run_with_deep_agent and router._llm_classify)."""
    import src.routing.deep_agent_runner as dar

    monkeypatch.setattr(dar.policy_agent, "run", lambda *a, **k: {"p": 1})
    captured = {}

    def fake_ticketing_run(context):
        captured["policy_result"] = context.upstream("policy")
        return {"ticket_id": "T-2"}

    monkeypatch.setattr(dar.ticketing_agent, "run", fake_ticketing_run)

    tools = build_tools("case", {}, None, None, None)
    decision = RoutingDecision(
        severity=Severity.HIGH,
        reason="test",
        route=["ticketing", "policy"],  # deliberately unsafe order
        summary={},
    )
    _run_tools_directly(decision, tools)

    assert captured["policy_result"] == {}


# ── _run_with_deep_agent — plan normalization ────────────────────────────────

class _FakeCall:
    def __init__(self, agent):
        self.agent = agent


class _FakePlan:
    def __init__(self, agents):
        self.calls = [_FakeCall(a) for a in agents]


class _FakeStructuredModel:
    def __init__(self, plan):
        self._plan = plan

    def invoke(self, prompt):
        return self._plan


class _FakeChatOpenAI:
    plan_agents: list[str] = []

    def __init__(self, *args, **kwargs):
        pass

    def with_structured_output(self, schema):
        return _FakeStructuredModel(_FakePlan(self.plan_agents))


class _FakeSettings:
    llm_model_name = "fake-model"
    llm_base_url = "http://fake"
    llm_api_key = "fake-key"


def test_run_with_deep_agent_normalizes_unsafe_plan_order(monkeypatch):
    import src.routing.deep_agent_runner as dar

    # The model's plan puts ticketing before policy/analysis — normalize_route
    # must reorder this before execution.
    _FakeChatOpenAI.plan_agents = ["ticketing", "policy", "analysis"]
    monkeypatch.setattr("langchain_openai.ChatOpenAI", _FakeChatOpenAI)
    monkeypatch.setattr(
        "src.utility.runtime_config.load_runtime_settings",
        lambda: _FakeSettings(),
    )

    monkeypatch.setattr(dar.policy_agent, "run", lambda *a, **k: {"p": 1})
    monkeypatch.setattr(dar.analysis_agent, "run", lambda *a, **k: {"a": 1})
    captured = {}

    def fake_ticketing_run(context):
        captured["policy_result"] = context.upstream("policy")
        captured["analysis_result"] = context.upstream("analysis")
        return {"ticket_id": "T-3"}

    monkeypatch.setattr(dar.ticketing_agent, "run", fake_ticketing_run)

    tools = build_tools("case", {}, None, None, None)
    decision = RoutingDecision(
        severity=Severity.HIGH,
        reason="test",
        route=["policy", "analysis", "ticketing"],
        summary={},
    )
    result = _run_with_deep_agent(decision, tools, {})

    # Ticketing must have executed after policy/analysis despite the model's
    # plan ordering it first — proof normalize_route() was applied.
    assert captured["policy_result"] == {"p": 1}
    assert captured["analysis_result"] == {"a": 1}
    assert result["ticketing"] == {"ticket_id": "T-3"}
