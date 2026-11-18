# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for the generic, config-only prompt-driven agent."""

import json

import pytest

from src.agents import generic_prompt_agent as gpa
from src.agents.context import AgentContext


def _context(**overrides) -> AgentContext:
    defaults = dict(
        use_case_id="test-case",
        config={},
        agent_name="sensor_correlation",
        prompt_section="SENSOR_CORRELATION",
    )
    defaults.update(overrides)
    return AgentContext(**defaults)


def test_fallback_mode_returns_deterministic_echo(monkeypatch):
    monkeypatch.setattr(gpa.llm_client, "is_fallback_mode", lambda: True)
    monkeypatch.setattr(
        gpa.storage_client, "get_summary", lambda **kwargs: {"by_class": [{"label": "Vibration"}]}
    )

    context = _context(upstream_results={"policy": {"recommendation": "MONITOR"}})
    result = gpa.run(context)

    assert result["agent"] == "sensor_correlation"
    assert result["mode"] == "fallback"
    assert result["summary"] == {"by_class": [{"label": "Vibration"}]}
    assert result["upstream_used"] == ["policy"]
    assert "note" in result


def test_llm_mode_uses_prompt_section_and_threads_upstream_results(monkeypatch):
    monkeypatch.setattr(gpa.llm_client, "is_fallback_mode", lambda: False)
    monkeypatch.setattr(gpa.storage_client, "get_summary", lambda **kwargs: {"by_class": []})

    sections = {
        "SYSTEM": "You are a QA assistant.",
        "SENSOR_CORRELATION": "Correlate vibration sensor spikes with vision defects.",
    }
    monkeypatch.setattr(
        gpa.prompt_loader,
        "get_section",
        lambda use_case_id, section, prompts_dir=None: sections[section],
    )

    captured = {}

    def fake_call_llm(system_prompt, user_message, max_tokens=512, **kwargs):
        captured["system_prompt"] = system_prompt
        captured["user_message"] = user_message
        captured["max_tokens"] = max_tokens
        return json.dumps({"correlated": True})

    monkeypatch.setattr(gpa.llm_client, "call_llm", fake_call_llm)

    context = _context(
        config={"sensor_correlation": {"max_tokens": 256}},
        upstream_results={"policy": {"recommendation": "HALT_PIPELINE"}},
    )
    result = gpa.run(context)

    assert captured["system_prompt"] == "You are a QA assistant."
    assert "Correlate vibration sensor spikes" in captured["user_message"]
    assert "HALT_PIPELINE" in captured["user_message"]
    assert captured["max_tokens"] == 256
    assert result == {
        "agent": "sensor_correlation",
        "mode": "llm",
        "output": {"correlated": True},
        "summary": {"by_class": []},
        "upstream_used": ["policy"],
    }


def test_missing_prompt_section_falls_back_to_configured_instructions(monkeypatch):
    monkeypatch.setattr(gpa.llm_client, "is_fallback_mode", lambda: False)
    monkeypatch.setattr(gpa.storage_client, "get_summary", lambda **kwargs: {})

    def get_section(use_case_id, section, prompts_dir=None):
        if section == "SYSTEM":
            return "You are a QA assistant."
        raise KeyError(f"Section [{section}] not found")

    monkeypatch.setattr(gpa.prompt_loader, "get_section", get_section)

    captured = {}

    def fake_call_llm(system_prompt, user_message, **kwargs):
        captured["user_message"] = user_message
        return "plain text answer"

    monkeypatch.setattr(gpa.llm_client, "call_llm", fake_call_llm)

    context = _context(
        config={"sensor_correlation": {"instructions": "Use the configured fallback instructions."}}
    )
    result = gpa.run(context)

    assert "Use the configured fallback instructions." in captured["user_message"]
    # Non-JSON LLM output is returned as-is rather than raising.
    assert result["output"] == "plain text answer"


def test_agent_name_defaults_when_not_set_by_caller(monkeypatch):
    monkeypatch.setattr(gpa.llm_client, "is_fallback_mode", lambda: True)
    monkeypatch.setattr(gpa.storage_client, "get_summary", lambda **kwargs: {})

    context = AgentContext(use_case_id="test-case", config={})
    result = gpa.run(context)

    assert result["agent"] == "generic_prompt_agent"


def test_agent_context_agent_config_reads_own_block():
    context = AgentContext(
        use_case_id="test-case",
        config={"sensor_correlation": {"max_tokens": 128}, "policy": {"x": 1}},
        agent_name="sensor_correlation",
    )
    assert context.agent_config() == {"max_tokens": 128}

    unnamed = AgentContext(use_case_id="test-case", config={"policy": {"x": 1}})
    assert unnamed.agent_config() == {}
