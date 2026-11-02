import sys
import types
from unittest.mock import patch

import pytest

from src.agentic import alert_agent as alert_agent_module


@pytest.fixture(autouse=True)
def reset_tool_registry(monkeypatch):
    monkeypatch.setattr(alert_agent_module, "_TOOL_MAP", {})
    monkeypatch.setattr(alert_agent_module, "_TOOL_SCHEMAS", [])


def test_alert_agent_uses_rule_based_mode_when_disabled():
    with patch.object(alert_agent_module.AlertActionAgent, "_init_adk") as init_adk:
        agent = alert_agent_module.AlertActionAgent(use_adk=False)

    init_adk.assert_not_called()
    assert agent._use_adk is False


def test_alert_agent_falls_back_to_rule_based_mode_when_llm_url_missing(monkeypatch):
    google_module = types.ModuleType("google")
    adk_module = types.ModuleType("google.adk")
    agents_module = types.ModuleType("google.adk.agents")
    tools_module = types.ModuleType("google.adk.tools")
    agents_module.LlmAgent = object
    tools_module.FunctionTool = object

    monkeypatch.setitem(sys.modules, "google", google_module)
    monkeypatch.setitem(sys.modules, "google.adk", adk_module)
    monkeypatch.setitem(sys.modules, "google.adk.agents", agents_module)
    monkeypatch.setitem(sys.modules, "google.adk.tools", tools_module)
    monkeypatch.setattr(alert_agent_module.settings, "LLM_URL", "")

    agent = alert_agent_module.AlertActionAgent(use_adk=True)

    assert agent._use_adk is False
    assert agent._adk_runner is None


@pytest.mark.parametrize("agent_mode", [True, False])
def test_alert_agent_respects_settings_when_use_adk_is_none(monkeypatch, agent_mode):
    monkeypatch.setattr(alert_agent_module.settings, "AGENT_MODE", agent_mode)

    with patch.object(alert_agent_module.AlertActionAgent, "_init_adk") as init_adk:
        agent = alert_agent_module.AlertActionAgent()

    assert agent._use_adk is agent_mode
    if agent_mode:
        init_adk.assert_called_once_with()
    else:
        init_adk.assert_not_called()
