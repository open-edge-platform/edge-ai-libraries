# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for registry-driven graph construction in meta_agent."""

from __future__ import annotations

import sys
from types import ModuleType

import pytest

from src import meta_agent
from src.routing.router import RoutingDecision, Severity


@pytest.fixture(autouse=True)
def reset_graphs(monkeypatch):
    monkeypatch.setattr(meta_agent, "_graphs", {})


def _custom_registry(module: str) -> list[dict[str, object]]:
    return [
        {
            "name": "policy",
            "module": "src.agents.policy_agent",
            "depends_on": [],
            "prompt_section": "POLICY",
        },
        {
            "name": "correlation",
            "module": module,
            "depends_on": ["policy"],
            "prompt_section": "CORRELATION",
        },
        {
            "name": "analysis",
            "module": "src.agents.analysis_agent",
            "depends_on": [],
            "prompt_section": "ANALYSIS",
        },
        {
            "name": "evidence",
            "module": "src.agents.evidence_agent",
            "depends_on": [],
            "prompt_section": "EVIDENCE",
        },
        {
            "name": "ticketing",
            "module": "src.agents.ticketing_agent",
            "depends_on": ["policy", "analysis"],
            "prompt_section": "TICKETING",
        },
    ]


def test_sequential_custom_registry_runs_extra_agent_and_stores_in_extra_bucket(monkeypatch):
    calls: list[str] = []
    module_name = "tests.fake_correlation_agent"
    module = ModuleType(module_name)

    def run(context):
        calls.append("correlation")
        return {
            "score": 0.91,
            "upstream_policy": context.upstream("policy"),
        }

    module.run = run
    monkeypatch.setitem(sys.modules, module_name, module)
    monkeypatch.setattr(
        meta_agent,
        "load_config",
        lambda _path: {"use_case_id": "case", "agent_registry": _custom_registry(module_name)},
    )
    monkeypatch.setenv("AGENT_MODE", "sequential")
    monkeypatch.setattr(meta_agent.policy_agent, "run", lambda *_args: calls.append("policy") or {"policy": True})
    monkeypatch.setattr(meta_agent.analysis_agent, "run", lambda *_args: calls.append("analysis") or {"analysis": True})
    monkeypatch.setattr(meta_agent.evidence_agent, "run", lambda *_args: calls.append("evidence") or {"evidence": True})
    monkeypatch.setattr(meta_agent.ticketing_agent, "run", lambda *_args: calls.append("ticketing") or {"ticket": True})

    result = meta_agent.run_pipeline()

    assert calls == ["policy", "correlation", "analysis", "evidence", "ticketing"]
    assert result["extra_agents"] == {
        "correlation": {
            "score": 0.91,
            "upstream_policy": {"policy": True},
        }
    }
    assert result["policy"] == {"policy": True}
    assert result["ticket"] == {"ticket": True}


def test_sequential_custom_registry_skips_extra_agent_when_dependency_failed(monkeypatch):
    module_name = "tests.fake_correlation_agent_skip"
    module = ModuleType(module_name)
    module.run = lambda _context: pytest.fail("correlation should be skipped")
    monkeypatch.setitem(sys.modules, module_name, module)
    monkeypatch.setattr(
        meta_agent,
        "load_config",
        lambda _path: {"use_case_id": "case", "agent_registry": _custom_registry(module_name)},
    )
    monkeypatch.setenv("AGENT_MODE", "sequential")

    def fail_policy(*_args):
        raise RuntimeError("policy unavailable")

    monkeypatch.setattr(meta_agent.policy_agent, "run", fail_policy)
    monkeypatch.setattr(meta_agent.analysis_agent, "run", lambda *_args: {"analysis": True})
    monkeypatch.setattr(meta_agent.evidence_agent, "run", lambda *_args: {"evidence": True})
    monkeypatch.setattr(
        meta_agent.ticketing_agent,
        "run",
        lambda *_args: pytest.fail("ticketing should be skipped"),
    )

    result = meta_agent.run_pipeline()

    assert "extra_agents" not in result
    assert result["analysis"] == {"analysis": True}
    assert result["evidence"] == {"evidence": True}
    assert [(error["agent"], error["status"]) for error in result["errors"]] == [
        ("policy", "failed"),
        ("correlation", "skipped"),
        ("ticketing", "skipped"),
    ]
    assert result["errors"][1]["dependencies"] == ["policy"]


@pytest.mark.parametrize(
    ("mode", "fallback_mode"),
    [("sequential", True), ("routing", True), ("routing", False)],
)
def test_default_registry_keeps_legacy_result_shape_across_modes(
    monkeypatch,
    mode,
    fallback_mode,
):
    monkeypatch.setattr(meta_agent, "load_config", lambda _path: {"use_case_id": "case"})
    monkeypatch.setenv("AGENT_MODE", mode)
    monkeypatch.setattr(meta_agent, "is_fallback_mode", lambda: fallback_mode)

    if mode == "sequential":
        monkeypatch.setattr(meta_agent.policy_agent, "run", lambda *_args: {"policy": True})
        monkeypatch.setattr(meta_agent.analysis_agent, "run", lambda *_args: {"analysis": True})
        monkeypatch.setattr(meta_agent.evidence_agent, "run", lambda *_args: {"evidence": True})
        monkeypatch.setattr(meta_agent.ticketing_agent, "run", lambda *_args: {"ticket": True})
        expected_routing = {}
    elif fallback_mode:
        monkeypatch.setattr(
            meta_agent,
            "classify",
            lambda *_args: RoutingDecision(
                severity=Severity.HIGH,
                reason="fallback",
                route=["policy", "analysis", "evidence", "ticketing"],
                summary={},
            ),
        )
        monkeypatch.setattr(meta_agent.policy_agent, "run", lambda *_args: {"policy": True})
        monkeypatch.setattr(meta_agent.analysis_agent, "run", lambda *_args: {"analysis": True})
        monkeypatch.setattr(meta_agent.evidence_agent, "run", lambda *_args: {"evidence": True})
        monkeypatch.setattr(meta_agent.ticketing_agent, "run", lambda *_args: {"ticket": True})
        expected_routing = {
            "severity": "HIGH",
            "reason": "fallback",
            "route": ["policy", "analysis", "evidence", "ticketing"],
        }
    else:
        monkeypatch.setattr(
            meta_agent,
            "classify",
            lambda *_args: RoutingDecision(
                severity=Severity.HIGH,
                reason="deep",
                route=["policy", "analysis", "evidence", "ticketing"],
                summary={},
            ),
        )
        monkeypatch.setattr(
            meta_agent,
            "run_deep_agent",
            lambda *_args: {
                "policy": {"policy": True},
                "analysis": {"analysis": True},
                "evidence": {"evidence": True},
                "ticketing": {"ticket": True},
            },
        )
        expected_routing = {
            "severity": "HIGH",
            "reason": "deep",
            "route": ["policy", "analysis", "evidence", "ticketing"],
        }

    result = meta_agent.run_pipeline()

    assert result == {
        "use_case_id": "case",
        "routing": expected_routing,
        "policy": {"policy": True},
        "analysis": {"analysis": True},
        "evidence": {"evidence": True},
        "ticket": {"ticket": True},
        "errors": [],
        "error": None,
    }
