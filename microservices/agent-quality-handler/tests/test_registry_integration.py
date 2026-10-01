# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Cross-module integration tests for the config-driven agent registry."""

from __future__ import annotations

import json
import sys
from types import ModuleType

import pytest
import yaml

from src import main, meta_agent
from src.routing.agent_registry import AgentRegistryError
from src.routing.deep_agent_runner import build_tools, _run_tools_directly
from src.routing.router import RoutingDecision, Severity


@pytest.fixture(autouse=True)
def reset_graphs(monkeypatch):
    monkeypatch.setattr(meta_agent, "_graphs", {})


def _write_config(tmp_path, registry: list[dict[str, object]]) -> str:
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "agents.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "use_case_id": "fused-vision-sensor",
                "agent_registry": registry,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return str(path)


def _registry(custom_module: str) -> list[dict[str, object]]:
    return [
        {
            "name": "policy",
            "module": "src.agents.policy_agent",
            "depends_on": [],
            "prompt_section": "POLICY",
        },
        {
            "name": "sensor_correlation",
            "module": custom_module,
            "depends_on": ["policy"],
            "prompt_section": "SENSOR_CORRELATION",
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


def _install_sensor_module(monkeypatch, module_name: str, run):
    module = ModuleType(module_name)
    module.run = run
    monkeypatch.setitem(sys.modules, module_name, module)


def _install_builtin_success_agents(monkeypatch, calls: list[str]):
    monkeypatch.setattr(
        meta_agent.policy_agent,
        "run",
        lambda _context: calls.append("policy") or {"policy": "allow"},
    )
    monkeypatch.setattr(
        meta_agent.analysis_agent,
        "run",
        lambda _context: calls.append("analysis") or {"analysis": "triaged"},
    )
    monkeypatch.setattr(
        meta_agent.evidence_agent,
        "run",
        lambda _context: calls.append("evidence") or {"evidence": ["frame-7"]},
    )
    monkeypatch.setattr(
        meta_agent.ticketing_agent,
        "run",
        lambda _context: calls.append("ticketing") or {"ticket": "INC-42"},
    )


@pytest.mark.parametrize(
    ("mode", "llm_mode", "route"),
    [
        ("sequential", "fallback", None),
        (
            "routing",
            "fallback",
            ["policy", "sensor_correlation", "analysis", "evidence", "ticketing"],
        ),
    ],
)
def test_run_pipeline_executes_custom_agent_end_to_end_and_preserves_builtin_shape(
    monkeypatch,
    tmp_path,
    mode,
    llm_mode,
    route,
):
    calls: list[str] = []
    upstream_policy: list[dict] = []
    module_name = f"tests.fake_sensor_agent_{mode}"
    _install_sensor_module(
        monkeypatch,
        module_name,
        lambda context: (
            calls.append("sensor_correlation"),
            upstream_policy.append(context.upstream("policy")),
            {
                "summary": "vision and sensor anomalies correlated",
                "policy_seen": context.upstream("policy"),
            },
        )[-1],
    )
    config_path = _write_config(tmp_path, _registry(module_name))

    monkeypatch.setenv("AGENT_MODE", mode)
    monkeypatch.setenv("LLM_MODE", llm_mode)
    if route is not None:
        monkeypatch.setattr(
            meta_agent,
            "classify",
            lambda *_args: RoutingDecision(
                severity=Severity.HIGH,
                reason="correlate vision and sensor anomalies",
                route=route,
                summary={},
            ),
        )
    _install_builtin_success_agents(monkeypatch, calls)

    result = meta_agent.run_pipeline(config_path=config_path)

    assert calls == [
        "policy",
        "sensor_correlation",
        "analysis",
        "evidence",
        "ticketing",
    ]
    assert upstream_policy == [{"policy": "allow"}]
    assert result == {
        "use_case_id": "fused-vision-sensor",
        "routing": (
            {}
            if mode == "sequential"
            else {
                "severity": "HIGH",
                "reason": "correlate vision and sensor anomalies",
                "route": route,
            }
        ),
        "policy": {"policy": "allow"},
        "analysis": {"analysis": "triaged"},
        "evidence": {"evidence": ["frame-7"]},
        "ticket": {"ticket": "INC-42"},
        "errors": [],
        "error": None,
        "extra_agents": {
            "sensor_correlation": {
                "summary": "vision and sensor anomalies correlated",
                "policy_seen": {"policy": "allow"},
            }
        },
    }


@pytest.mark.parametrize(
    ("mode", "llm_mode", "route"),
    [
        ("sequential", "fallback", None),
        (
            "routing",
            "fallback",
            ["policy", "sensor_correlation", "analysis", "evidence", "ticketing"],
        ),
    ],
)
def test_run_pipeline_skips_custom_agent_when_policy_fails(
    monkeypatch,
    tmp_path,
    mode,
    llm_mode,
    route,
):
    module_name = f"tests.fake_sensor_skip_{mode}"
    _install_sensor_module(
        monkeypatch,
        module_name,
        lambda _context: pytest.fail("sensor_correlation should be skipped"),
    )
    config_path = _write_config(tmp_path, _registry(module_name))

    monkeypatch.setenv("AGENT_MODE", mode)
    monkeypatch.setenv("LLM_MODE", llm_mode)
    if route is not None:
        monkeypatch.setattr(
            meta_agent,
            "classify",
            lambda *_args: RoutingDecision(
                severity=Severity.HIGH,
                reason="correlate vision and sensor anomalies",
                route=route,
                summary={},
            ),
        )

    def fail_policy(_context):
        raise RuntimeError("policy unavailable")

    monkeypatch.setattr(meta_agent.policy_agent, "run", fail_policy)
    monkeypatch.setattr(meta_agent.analysis_agent, "run", lambda _context: {"analysis": "triaged"})
    monkeypatch.setattr(meta_agent.evidence_agent, "run", lambda _context: {"evidence": ["frame-7"]})
    monkeypatch.setattr(
        meta_agent.ticketing_agent,
        "run",
        lambda _context: pytest.fail("ticketing should be skipped"),
    )

    result = meta_agent.run_pipeline(config_path=config_path)

    assert result["policy"] == {}
    assert result["analysis"] == {"analysis": "triaged"}
    assert result["evidence"] == {"evidence": ["frame-7"]}
    assert result["ticket"] == {}
    assert "extra_agents" not in result
    assert [(error["agent"], error["status"]) for error in result["errors"]] == [
        ("policy", "failed"),
        ("sensor_correlation", "skipped"),
        ("ticketing", "skipped"),
    ]
    assert result["errors"][1]["dependencies"] == ["policy"]


def test_llm_routing_pipeline_keeps_custom_route_and_executes_custom_agent_once(
    monkeypatch,
    tmp_path,
):
    calls: list[str] = []
    upstream_policy: list[dict] = []
    module_name = "tests.fake_sensor_llm_pipeline"

    def run_sensor(context):
        calls.append("sensor_correlation")
        upstream_policy.append(context.upstream("policy"))
        return {"summary": "sensor fusion complete"}

    _install_sensor_module(monkeypatch, module_name, run_sensor)
    config_path = _write_config(tmp_path, _registry(module_name))

    monkeypatch.setenv("AGENT_MODE", "routing")
    monkeypatch.setenv("LLM_MODE", "llm")
    monkeypatch.setattr(
        "src.routing.router.storage_client.get_summary",
        lambda **_kwargs: {"by_class": []},
    )
    monkeypatch.setattr(
        "src.routing.router.prompt_loader.get_section",
        lambda *_args, **_kwargs: "prompt",
    )
    monkeypatch.setattr(
        "src.routing.router.llm_client.call_llm",
        lambda **_kwargs: json.dumps(
            {
                "severity": "HIGH",
                "reason": "sensor correlation required",
                "route": [
                    "policy",
                    "sensor_correlation",
                    "analysis",
                    "evidence",
                    "ticketing",
                ],
            }
        ),
    )
    monkeypatch.setattr(
        "src.routing.deep_agent_runner._run_with_deep_agent",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ImportError("exercise direct tools")),
    )
    _install_builtin_success_agents(monkeypatch, calls)

    result = meta_agent.run_pipeline(config_path=config_path)

    assert calls == [
        "policy",
        "sensor_correlation",
        "analysis",
        "evidence",
        "ticketing",
    ]
    assert upstream_policy == [{"policy": "allow"}]
    assert result["routing"]["route"] == [
        "policy",
        "sensor_correlation",
        "analysis",
        "evidence",
        "ticketing",
    ]
    assert result["extra_agents"] == {
        "sensor_correlation": {"summary": "sensor fusion complete"}
    }
    assert result["ticket"] == {"ticket": "INC-42"}


def test_deep_agent_tools_execute_full_custom_route_end_to_end(monkeypatch):
    captured = {}
    module_name = "tests.fake_sensor_tool"

    def run_sensor(context):
        captured["policy"] = context.upstream("policy")
        return {"summary": "sensor correlation queued"}

    _install_sensor_module(
        monkeypatch,
        module_name,
        run_sensor,
    )

    config = {"agent_registry": _registry(module_name)}
    monkeypatch.setattr(
        meta_agent.policy_agent,
        "run",
        lambda _context: {"policy": "allow"},
    )
    monkeypatch.setattr(
        meta_agent.analysis_agent,
        "run",
        lambda _context: {"analysis": "triaged"},
    )
    monkeypatch.setattr(
        meta_agent.evidence_agent,
        "run",
        lambda _context: {"evidence": ["frame-7"]},
    )
    monkeypatch.setattr(
        meta_agent.ticketing_agent,
        "run",
        lambda _context: {"ticket": "INC-42"},
    )

    tools = build_tools("fused-vision-sensor", config, None, 10, 20)
    decision = RoutingDecision(
        severity=Severity.HIGH,
        reason="sensor correlation required",
        route=["policy", "sensor_correlation", "analysis", "evidence", "ticketing"],
        summary={},
    )

    results = _run_tools_directly(decision, tools)

    assert [(tool.name, list(tool.args)) for tool in tools] == [
        ("run_policy_agent", ["reason"]),
        ("run_sensor_correlation_agent", ["policy_result_json"]),
        ("run_analysis_agent", ["policy_result_json"]),
        ("run_evidence_agent", ["reason"]),
        ("run_ticketing_agent", ["policy_result_json", "analysis_result_json"]),
    ]
    assert captured["policy"] == {"policy": "allow"}
    assert results == {
        "policy": {"policy": "allow"},
        "sensor_correlation": {"summary": "sensor correlation queued"},
        "analysis": {"analysis": "triaged"},
        "evidence": {"evidence": ["frame-7"]},
        "ticketing": {"ticket": "INC-42"},
    }


def test_invalid_registry_fails_fast_in_pipeline_and_startup(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENT_MODE", "sequential")
    monkeypatch.setenv("LLM_MODE", "fallback")

    cycle_path = _write_config(
        tmp_path,
        [
            {"name": "policy", "module": "src.agents.policy_agent", "depends_on": ["sensor_correlation"]},
            {"name": "sensor_correlation", "module": "src.agents.evidence_agent", "depends_on": ["policy"]},
        ],
    )
    bad_module_path = _write_config(
        tmp_path / "bad",
        [
            {"name": "policy", "module": "src.agents.policy_agent", "depends_on": []},
            {
                "name": "sensor_correlation",
                "module": "tests.does_not_exist_sensor_agent",
                "depends_on": ["policy"],
            },
        ],
    )

    with pytest.raises(AgentRegistryError, match="dependency cycle"):
        meta_agent.run_pipeline(config_path=cycle_path)
    with pytest.raises(AgentRegistryError, match="dependency cycle"):
        main._build_output_store(cycle_path)
    with pytest.raises(AgentRegistryError, match="unimportable module"):
        meta_agent.run_pipeline(config_path=bad_module_path)
    with pytest.raises(AgentRegistryError, match="unimportable module"):
        main._build_output_store(bad_module_path)
