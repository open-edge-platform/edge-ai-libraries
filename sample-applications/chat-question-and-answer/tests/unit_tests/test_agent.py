# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for the LangGraph ReAct agent tools.

Tests:
  - calculator: math expressions, edge cases, disallowed operations
  - web_search: graceful fallback when duckduckgo is unavailable
  - vector_search: mocked retriever response
  - agent_health endpoint: returns tool list
  - agent_chat endpoint: empty question validation
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# calculator tests – no mocking needed, pure logic
# ---------------------------------------------------------------------------
from app.agent import calculator, web_search, TOOLS


class TestCalculator:
    def test_basic_addition(self):
        result = calculator.invoke({"expression": "2 + 3"})
        assert "5" in result

    def test_multiplication(self):
        result = calculator.invoke({"expression": "6 * 7"})
        assert "42" in result

    def test_power(self):
        result = calculator.invoke({"expression": "2 ** 10"})
        assert "1024" in result

    def test_float_division(self):
        result = calculator.invoke({"expression": "10 / 4"})
        assert "2.5" in result

    def test_math_function_sqrt(self):
        result = calculator.invoke({"expression": "sqrt(144)"})
        assert "12" in result

    def test_math_function_floor(self):
        result = calculator.invoke({"expression": "floor(3.9)"})
        assert "3" in result

    def test_zero_division(self):
        result = calculator.invoke({"expression": "1 / 0"})
        assert "zero" in result.lower()

    def test_disallowed_expression(self):
        # Should not allow arbitrary code
        result = calculator.invoke({"expression": "import os"})
        assert "Could not evaluate" in result or "Error" in result

    def test_empty_expression(self):
        result = calculator.invoke({"expression": ""})
        assert "Could not evaluate" in result or "Error" in result

    def test_nested_expression(self):
        result = calculator.invoke({"expression": "(3 + 4) * (2 - 1)"})
        assert "7" in result


# ---------------------------------------------------------------------------
# web_search tests – mock DDGS to avoid real network calls in CI
# ---------------------------------------------------------------------------
class TestWebSearch:
    def test_returns_results_when_ddgs_works(self):
        mock_result = [
            {
                "title": "GraphRAG paper",
                "body": "GraphRAG combines knowledge graphs with RAG.",
                "href": "https://example.com/graphrag",
            }
        ]
        with patch("app.agent.DDGS") as MockDDGS:
            MockDDGS.return_value.__enter__.return_value.text.return_value = mock_result
            result = web_search.invoke({"query": "what is GraphRAG"})
        assert "GraphRAG" in result
        assert "example.com" in result

    def test_graceful_when_no_results(self):
        with patch("app.agent.DDGS") as MockDDGS:
            MockDDGS.return_value.__enter__.return_value.text.return_value = []
            result = web_search.invoke({"query": "xyznonexistent12345"})
        assert "No web results" in result

    def test_graceful_when_duckduckgo_not_installed(self):
        with patch.dict("sys.modules", {"duckduckgo_search": None}):
            # Re-invoke in context where import fails
            result = web_search.invoke({"query": "test"})
        # Should return a helpful error, not raise
        assert isinstance(result, str)

    def test_handles_ddgs_exception(self):
        with patch("app.agent.DDGS") as MockDDGS:
            MockDDGS.return_value.__enter__.return_value.text.side_effect = Exception(
                "timeout"
            )
            result = web_search.invoke({"query": "test"})
        assert "error" in result.lower() or "Web search" in result


# ---------------------------------------------------------------------------
# TOOLS list sanity checks
# ---------------------------------------------------------------------------
class TestToolsRegistry:
    def test_three_tools_registered(self):
        assert len(TOOLS) == 3

    def test_tool_names(self):
        names = {t.name for t in TOOLS}
        assert names == {"vector_search", "web_search", "calculator"}

    def test_all_tools_have_descriptions(self):
        for t in TOOLS:
            assert t.description and len(t.description) > 10


# ---------------------------------------------------------------------------
# Server endpoint tests (agent_health + agent_chat)
# ---------------------------------------------------------------------------
@pytest.fixture
def test_client():
    """Reuse the app testclient from conftest if it exists, else create one."""
    # We patch chain module to prevent real DB init at import time
    with patch("app.chain.create_async_engine"), patch(
        "app.chain.EGAIEmbeddings"
    ), patch("app.chain.EGAIVectorDB"), patch("app.chain.EGAIVectorStoreRetriever"):
        from app.server import app

        with TestClient(app, raise_server_exceptions=False) as client:
            yield client


class TestAgentEndpoints:
    def test_agent_health_returns_tools(self, test_client):
        response = test_client.get("/agent/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        tool_names = [t["name"] for t in data["tools"]]
        assert "vector_search" in tool_names
        assert "web_search" in tool_names
        assert "calculator" in tool_names

    def test_agent_chat_empty_question(self, test_client):
        payload = {
            "conversation_messages": [{"role": "user", "content": ""}],
            "max_tokens": 256,
        }
        response = test_client.post("/agent/chat", json=payload)
        assert response.status_code == 422

    def test_agent_chat_whitespace_question(self, test_client):
        payload = {
            "conversation_messages": [{"role": "user", "content": "   "}],
            "max_tokens": 256,
        }
        response = test_client.post("/agent/chat", json=payload)
        assert response.status_code == 422

    def test_agent_chat_streams_on_valid_input(self, test_client):
        """Mock run_agent_stream to verify the endpoint streams correctly."""

        async def mock_stream(question, history=""):
            yield "data: [agent] 🔧 Using tool: **calculator**('2+2')\n\n"
            yield "data: The answer is 4.\n\n"

        with patch("app.server.run_agent_stream", side_effect=mock_stream):
            payload = {
                "conversation_messages": [{"role": "user", "content": "What is 2+2?"}],
                "max_tokens": 256,
            }
            response = test_client.post("/agent/chat", json=payload)
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
