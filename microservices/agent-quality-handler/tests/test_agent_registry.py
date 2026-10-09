# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for the config-driven agent registry (Phase 2, step 1)."""

import pytest

from src.routing.agent_registry import (
    AgentRegistryError,
    AgentSpec,
    DEFAULT_REGISTRY,
    load_registry,
    resolve_run_callable,
    topological_order,
)


# ── load_registry — default behavior ─────────────────────────────────────────

def test_load_registry_returns_defaults_when_key_absent():
    specs = load_registry({"use_case_id": "test-case"})
    assert specs == list(DEFAULT_REGISTRY)


def test_load_registry_returns_defaults_when_config_none():
    assert load_registry(None) == list(DEFAULT_REGISTRY)


def test_load_registry_returns_defaults_when_key_empty_list():
    assert load_registry({"agent_registry": []}) == list(DEFAULT_REGISTRY)


def test_default_registry_matches_existing_four_agents_and_dependencies():
    names = [spec.name for spec in DEFAULT_REGISTRY]
    assert names == ["policy", "analysis", "evidence", "ticketing"]
    by_name = {spec.name: spec for spec in DEFAULT_REGISTRY}
    assert by_name["ticketing"].depends_on == ("policy", "analysis")
    assert by_name["policy"].depends_on == ()
    assert by_name["analysis"].depends_on == ()
    assert by_name["evidence"].depends_on == ()


# ── load_registry — custom entries ───────────────────────────────────────────

def test_load_registry_parses_custom_entry():
    config = {
        "agent_registry": [
            {"name": "policy", "module": "src.agents.policy_agent"},
            {
                "name": "sensor_correlation",
                "module": "src.agents.sensor_correlation_agent",
                "depends_on": ["policy"],
                "prompt_section": "SENSOR_CORRELATION",
            },
        ]
    }
    specs = load_registry(config)
    assert [spec.name for spec in specs] == ["policy", "sensor_correlation"]
    assert specs[1].depends_on == ("policy",)
    assert specs[1].module == "src.agents.sensor_correlation_agent"
    assert specs[1].prompt_section == "SENSOR_CORRELATION"


def test_agent_spec_defaults_prompt_section_to_uppercase_name():
    spec = AgentSpec(name="evidence", module="src.agents.evidence_agent")
    assert spec.prompt_section == "EVIDENCE"


def test_load_registry_rejects_non_list():
    with pytest.raises(AgentRegistryError, match="must be a list"):
        load_registry({"agent_registry": {"name": "policy"}})


def test_load_registry_rejects_non_mapping_entry():
    with pytest.raises(AgentRegistryError, match="must be a mapping"):
        load_registry({"agent_registry": ["policy"]})


def test_load_registry_rejects_missing_name():
    with pytest.raises(AgentRegistryError, match="non-empty 'name'"):
        load_registry({"agent_registry": [{"module": "src.agents.policy_agent"}]})


def test_load_registry_rejects_missing_module():
    with pytest.raises(AgentRegistryError, match="non-empty 'module'"):
        load_registry({"agent_registry": [{"name": "policy"}]})


def test_load_registry_rejects_invalid_depends_on_type():
    with pytest.raises(AgentRegistryError, match="invalid 'depends_on'"):
        load_registry({
            "agent_registry": [
                {"name": "policy", "module": "m", "depends_on": "policy"},
            ]
        })


def test_load_registry_rejects_duplicate_names():
    with pytest.raises(AgentRegistryError, match="duplicate agent name"):
        load_registry({
            "agent_registry": [
                {"name": "policy", "module": "m1"},
                {"name": "policy", "module": "m2"},
            ]
        })


def test_load_registry_rejects_unknown_dependency():
    with pytest.raises(AgentRegistryError, match="unknown agent"):
        load_registry({
            "agent_registry": [
                {"name": "ticketing", "module": "m", "depends_on": ["policy"]},
            ]
        })


def test_load_registry_rejects_self_dependency():
    with pytest.raises(AgentRegistryError, match="cannot depend on itself"):
        load_registry({
            "agent_registry": [
                {"name": "policy", "module": "m", "depends_on": ["policy"]},
            ]
        })


def test_load_registry_rejects_dependency_cycle():
    with pytest.raises(AgentRegistryError, match="dependency cycle"):
        load_registry({
            "agent_registry": [
                {"name": "a", "module": "m", "depends_on": ["b"]},
                {"name": "b", "module": "m", "depends_on": ["a"]},
            ]
        })


# ── topological_order ────────────────────────────────────────────────────────

def test_topological_order_matches_default_execution_order():
    assert topological_order(list(DEFAULT_REGISTRY)) == [
        "policy", "analysis", "evidence", "ticketing",
    ]


def test_topological_order_respects_dependencies_regardless_of_declaration_order():
    specs = [
        AgentSpec(name="ticketing", module="m", depends_on=("policy", "analysis")),
        AgentSpec(name="analysis", module="m"),
        AgentSpec(name="policy", module="m"),
    ]
    order = topological_order(specs)
    assert order.index("policy") < order.index("ticketing")
    assert order.index("analysis") < order.index("ticketing")


def test_topological_order_preserves_declaration_order_for_independent_agents():
    specs = [
        AgentSpec(name="evidence", module="m"),
        AgentSpec(name="analysis", module="m"),
        AgentSpec(name="policy", module="m"),
    ]
    assert topological_order(specs) == ["evidence", "analysis", "policy"]


# ── resolve_run_callable ──────────────────────────────────────────────────────

def test_resolve_run_callable_finds_existing_agent_run():
    spec = AgentSpec(name="policy", module="src.agents.policy_agent")
    run = resolve_run_callable(spec)
    assert callable(run)
    import src.agents.policy_agent as policy_agent
    assert run is policy_agent.run


def test_resolve_run_callable_rejects_unimportable_module():
    spec = AgentSpec(name="ghost", module="src.agents.does_not_exist_agent")
    with pytest.raises(AgentRegistryError, match="unimportable module"):
        resolve_run_callable(spec)


def test_resolve_run_callable_rejects_module_without_run(monkeypatch):
    import types
    import sys

    fake_module = types.ModuleType("src.agents._fake_no_run_agent")
    monkeypatch.setitem(sys.modules, "src.agents._fake_no_run_agent", fake_module)

    spec = AgentSpec(name="fake", module="src.agents._fake_no_run_agent")
    with pytest.raises(AgentRegistryError, match="no callable 'run'"):
        resolve_run_callable(spec)
