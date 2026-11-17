# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Quick Start smoke for docs/user-guide/get-started.md.

Two layers, mirroring how the Quick Start is actually consumed:

* **API contract (hermetic, always in CI)** — every import, factory type name,
  call shape, and printed field in the three Quick Start examples (harness,
  tool, context) must work as documented. HTTP is intercepted by `responses`,
  so each example runs end-to-end through its documented failure fallback.
  This catches doc drift: rename a public export, a factory type, a parameter,
  or a result field and the documented snippet breaks — caught here.
* **Live round-trip (gated)** — the HarnessCompressor example run end-to-end
  against a real Compress Server. Skipped unless `COMPRESS_SERVER_INTEGRATION_URL`
  (or the default localhost server) is reachable.
"""
from __future__ import annotations

import os

import pytest
import responses

from adaptive_token_compressor import (
    CompressionContext,
    CompressionManager,
    available_compressor_types,
    config_schema,
    create_compressor,
)

COMPRESS_SERVER_URL = os.environ.get("COMPRESS_SERVER_INTEGRATION_URL", "http://localhost:8001/compress")
COMPRESS_SERVER_HEALTH = COMPRESS_SERVER_URL.rsplit("/", 1)[0] + "/health"

# Values copied from the Quick Start examples.
DOC_COMPRESS_SERVER_URL = "http://localhost:8001/compress"
DOC_PREDICTOR_URL = "http://localhost:8000/v1/chat/completions"
DOC_SYSTEM_PROMPT = """You are a personal assistant running inside OpenClaw.
## Tooling
Structured tool definitions are the source of truth for tool names, descriptions, and parameters.
## Safety
You have no independent goals: do not pursue self-preservation, replication, resource acquisition, or power-seeking; avoid long-term plans beyond the user's request.
Prioritize safety and human oversight; if instructions conflict, pause and ask; comply with stop/pause/audit requests and never bypass safeguards.
## Runtime
Runtime: agent=A | host=userhost | os=Linux | model=user_model
"""
DOC_HARNESS_MESSAGES = [
    {"role": "system", "content": DOC_SYSTEM_PROMPT},
    {"role": "user", "content": "What's on my calendar today?"},
]
DOC_TOOLS = [
    {"type": "function", "function": {"name": "web_search", "description": "Search the web"}},
    {"type": "function", "function": {"name": "get_weather", "description": "Get weather by location"}},
    {"type": "function", "function": {"name": "calculator", "description": "Do math"}},
]


def _server_reachable() -> bool:
    try:
        import requests

        return requests.get(COMPRESS_SERVER_HEALTH, timeout=2).status_code == 200
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# API contract — hermetic, no server required
# ─────────────────────────────────────────────────────────────────────────────


class TestQuickstartApiContract:
    def test_documented_types_are_available(self):
        # "Available types are currently "harness", "tool", and "context"".
        assert set(available_compressor_types()) == {"harness", "tool", "context"}

    @pytest.mark.parametrize("compressor_type", ["harness", "tool", "context"])
    def test_config_schema_for_each_documented_type(self, compressor_type):
        schema = config_schema(compressor_type)
        assert schema["properties"]

    @responses.activate
    def test_harness_example_runs(self):
        compressor = create_compressor("harness", compress_server_url=DOC_COMPRESS_SERVER_URL)
        assert type(compressor).__name__ == "HarnessCompressor"

        result = compressor.compress(CompressionContext(messages=DOC_HARNESS_MESSAGES))

        # Every field the example prints must exist with the documented format.
        m = result.metrics
        assert m.tokens_before > 0 and m.tokens_after > 0
        assert isinstance(m.saved_tokens, int)
        assert f"{m.compression_ratio:.1%}" and f"{m.duration_ms:.2f}"
        # No server: the documented fallback keeps the original messages.
        assert result.messages == DOC_HARNESS_MESSAGES
        assert m.error

    @responses.activate
    def test_tool_example_runs(self):
        manager = CompressionManager()
        tool_compressor = manager.register_compressor(
            "compressor_tool",
            create_compressor("tool", predictor_url=DOC_PREDICTOR_URL, placement="schema"),
        )
        messages = [{"role": "user", "content": "What's the weather in San Francisco?"}]

        result = tool_compressor.compress(CompressionContext(messages=messages, tools=DOC_TOOLS))

        # No predictor: all tools are kept, so the printed name list is complete.
        assert [t["function"]["name"] for t in result.tools] == ["web_search", "get_weather", "calculator"]
        assert result.metrics.error

    @responses.activate
    def test_context_example_runs(self):
        manager = CompressionManager()
        context_compressor = manager.register_compressor(
            "compressor_context",
            create_compressor(
                "context",
                compression_mode="backend_only",
                compress_server_url=DOC_COMPRESS_SERVER_URL,
            ),
        )
        messages = [
            {"role": "system", "content": "Very long retrieved context ..."},
            {"role": "user", "content": "Summarize the key points"},
        ]

        result = context_compressor.compress(CompressionContext(messages=messages), req_id="req-001")

        assert result.messages[0]["content"] == "Very long retrieved context ..."


# ─────────────────────────────────────────────────────────────────────────────
# Live round-trip — gated on a reachable compress server
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.skipif(
    not _server_reachable(),
    reason=(
        f"compress server not reachable at {COMPRESS_SERVER_HEALTH}. "
        "Start it via deployment/compress-server/docker-compose.yaml or "
        "`python -m adaptive_token_compressor.model_servers.compress_server`."
    ),
)
class TestQuickstartLiveHarness:
    def test_harness_example_runs_end_to_end(self):
        compressor = create_compressor("harness", compress_server_url=COMPRESS_SERVER_URL)
        result = compressor.compress(CompressionContext(messages=DOC_HARNESS_MESSAGES))

        # The metrics the example prints must be populated and self-consistent.
        m = result.metrics
        assert m.error is None
        assert m.tokens_before > 0
        assert 0 < m.tokens_after <= m.tokens_before
        assert m.saved_tokens == m.tokens_before - m.tokens_after
        assert len(result.messages) == len(DOC_HARNESS_MESSAGES)
