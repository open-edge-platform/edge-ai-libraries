# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Focused tests for graph results, failures, and dependency handling."""

import pytest

from src import meta_agent


@pytest.fixture(autouse=True)
def reset_graph(monkeypatch):
    monkeypatch.setattr(meta_agent, "_graph", None)
    monkeypatch.setattr(meta_agent, "load_config", lambda _path: {"use_case_id": "case"})


def _install_successful_agents(monkeypatch):
    monkeypatch.setattr(meta_agent.policy_agent, "run", lambda *args: {"policy": True})
    monkeypatch.setattr(meta_agent.analysis_agent, "run", lambda *args: {"analysis": True})
    monkeypatch.setattr(meta_agent.evidence_agent, "run", lambda *args: {"evidence": True})
    monkeypatch.setattr(meta_agent.ticketing_agent, "run", lambda *args: {"ticket": True})


def test_successful_graph_returns_consistent_results(monkeypatch):
    _install_successful_agents(monkeypatch)

    result = meta_agent.run_pipeline()

    assert result == {
        "use_case_id": "case",
        "policy": {"policy": True},
        "analysis": {"analysis": True},
        "evidence": {"evidence": True},
        "ticket": {"ticket": True},
        "errors": [],
        "error": None,
    }


def test_bounds_are_passed_to_all_reading_agents(monkeypatch):
    calls = []
    monkeypatch.setattr(
        meta_agent.policy_agent,
        "run",
        lambda *args: calls.append(("policy", args[-2:])) or {},
    )
    monkeypatch.setattr(
        meta_agent.analysis_agent,
        "run",
        lambda *args: calls.append(("analysis", args[-2:])) or {},
    )
    monkeypatch.setattr(
        meta_agent.evidence_agent,
        "run",
        lambda *args: calls.append(("evidence", args[-2:])) or {},
    )
    monkeypatch.setattr(meta_agent.ticketing_agent, "run", lambda *args: {})

    meta_agent.run_pipeline(min_id=10, max_id=20)

    assert calls == [
        ("policy", (10, 20)),
        ("analysis", (10, 20)),
        ("evidence", (10, 20)),
    ]


def test_analysis_failure_preserves_independent_outputs_and_skips_ticket(monkeypatch):
    calls = []
    monkeypatch.setattr(meta_agent.policy_agent, "run", lambda *args: {"policy": True})

    def fail_analysis(*args):
        raise RuntimeError("analysis unavailable")

    monkeypatch.setattr(meta_agent.analysis_agent, "run", fail_analysis)
    monkeypatch.setattr(
        meta_agent.evidence_agent,
        "run",
        lambda *args: calls.append("evidence") or {"evidence": True},
    )
    monkeypatch.setattr(
        meta_agent.ticketing_agent, "run", lambda *args: calls.append("ticket")
    )

    result = meta_agent.run_pipeline()

    assert result["policy"] == {"policy": True}
    assert result["analysis"] == {}
    assert result["evidence"] == {"evidence": True}
    assert result["ticket"] == {}
    assert calls == ["evidence"]
    assert [(e["agent"], e["status"]) for e in result["errors"]] == [
        ("analysis", "failed"),
        ("ticketing", "skipped"),
    ]
    assert result["errors"][1]["dependencies"] == ["analysis"]


def test_policy_failure_keeps_independent_partial_outputs(monkeypatch):
    def fail_policy(*args):
        raise ValueError("policy unavailable")

    monkeypatch.setattr(meta_agent.policy_agent, "run", fail_policy)
    monkeypatch.setattr(meta_agent.analysis_agent, "run", lambda *args: {"count": 4})
    monkeypatch.setattr(meta_agent.evidence_agent, "run", lambda *args: {"frames": [1]})
    monkeypatch.setattr(
        meta_agent.ticketing_agent,
        "run",
        lambda *args: pytest.fail("ticket must be skipped"),
    )

    result = meta_agent.run_pipeline()

    assert result["analysis"] == {"count": 4}
    assert result["evidence"] == {"frames": [1]}
    assert result["ticket"] == {}
    assert [(e["agent"], e["status"]) for e in result["errors"]] == [
        ("policy", "failed"),
        ("ticketing", "skipped"),
    ]


def test_evidence_failure_does_not_block_ticketing(monkeypatch):
    def fail_evidence(*args):
        raise RuntimeError("evidence unavailable")

    monkeypatch.setattr(meta_agent.policy_agent, "run", lambda *args: {"policy": True})
    monkeypatch.setattr(meta_agent.analysis_agent, "run", lambda *args: {"count": 4})
    monkeypatch.setattr(meta_agent.evidence_agent, "run", fail_evidence)
    monkeypatch.setattr(
        meta_agent.ticketing_agent, "run", lambda *args: {"ticket": True}
    )

    result = meta_agent.run_pipeline()

    assert result["ticket"] == {"ticket": True}
    assert [(e["agent"], e["status"]) for e in result["errors"]] == [
        ("evidence", "failed"),
    ]


def test_invalid_agent_output_is_attributed_and_skips_dependents(monkeypatch):
    monkeypatch.setattr(meta_agent.policy_agent, "run", lambda *args: {"policy": True})
    monkeypatch.setattr(meta_agent.analysis_agent, "run", lambda *args: None)
    monkeypatch.setattr(
        meta_agent.evidence_agent, "run", lambda *args: {"evidence": True}
    )
    monkeypatch.setattr(
        meta_agent.ticketing_agent,
        "run",
        lambda *args: pytest.fail("ticket must be skipped"),
    )

    result = meta_agent.run_pipeline()

    assert result["analysis"] == {}
    assert result["evidence"] == {"evidence": True}
    assert result["errors"][0] == {
        "agent": "analysis",
        "status": "failed",
        "type": "TypeError",
        "message": "Analysis agent returned NoneType; expected a mapping",
    }
    assert result["errors"][1]["agent"] == "ticketing"
    assert result["errors"][1]["status"] == "skipped"
