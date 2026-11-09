"""Shared fixtures for context/ tests.

Both JSON fixtures contain captured conversation and tool-result payloads:
  - conversation_history.json : the 24-msg request chatcmpl-55c8aaa9
  - tavily_web_search.json    : one real Tavily tool-result payload
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

_FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def conversation_history() -> list[dict]:
    """The 24-msg conversation (system/user/assistant/tool) from cuddly-prism."""
    return json.loads((_FIXTURES / "conversation_history.json").read_text())


@pytest.fixture
def tavily_payload() -> dict:
    """A real Tavily web_search result dict (query + results[])."""
    return json.loads((_FIXTURES / "tavily_web_search.json").read_text())


@pytest.fixture
def tavily_content(tavily_payload) -> str:
    """The Tavily payload serialized as a tool message `content` string."""
    return json.dumps(tavily_payload, ensure_ascii=False)
