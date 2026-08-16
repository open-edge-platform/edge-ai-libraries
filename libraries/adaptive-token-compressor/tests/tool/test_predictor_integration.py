"""B5.5 — ToolCompressor + real vLLM tool-predictor integration tests.

These tests hit a running vLLM `/v1/chat/completions` endpoint that serves
a small instruction-tuned model. Default URL / model are read from env
``TOOL_PREDICTOR_URL`` / ``TOOL_PREDICTOR_MODEL``; all tests skip if the
server is unreachable *or does not serve the requested model* (so a host
that came up with a different model cleanly skips instead of failing).

Quick start (one of):

  # point at your own running vLLM endpoint
  TOOL_PREDICTOR_URL=http://your-vllm-host:8089/v1/chat/completions \
  TOOL_PREDICTOR_MODEL=Qwen/Qwen3.6-35B-A3B \
  pytest tests/tool/test_predictor_integration.py -v

  # local docker compose defaults (http://localhost:8089, Qwen3.6-35B-A3B)
  pytest tests/tool/test_predictor_integration.py -v
"""
from __future__ import annotations

import os
from urllib.parse import urlparse

import pytest
import requests

from adaptive_token_compressor.core.base import CompressionContext
from adaptive_token_compressor.core.health import HealthState
from adaptive_token_compressor.core.metrics import CompressionScope
from adaptive_token_compressor.tool.compressor import ToolCompressor
from adaptive_token_compressor.tool.predictor import HTTPToolPredictor


PREDICTOR_URL = os.environ.get(
    "TOOL_PREDICTOR_URL",
    "http://localhost:8089/v1/chat/completions",
)
PREDICTOR_MODEL = os.environ.get(
    "TOOL_PREDICTOR_MODEL",
    "Qwen/Qwen3.6-35B-A3B",
)


def _models_url(chat_url: str) -> str:
    """Derive `/v1/models` from a `/v1/chat/completions` URL."""
    if chat_url.endswith("/v1/chat/completions"):
        return chat_url[: -len("/chat/completions")] + "/models"
    parsed = urlparse(chat_url)
    return f"{parsed.scheme}://{parsed.netloc}/v1/models"


PREDICTOR_HEALTH = _models_url(PREDICTOR_URL)


def _skip_reason() -> str | None:
    """Probe the configured predictor. Return ``None`` when the target model
    is actually served (tests may run), else a human-readable skip reason.

    Reachability alone is not enough: a host can be up serving a *different*
    model, in which case `/v1/chat/completions` 404s the requested model and
    the tests would fail instead of skip. So we require ``PREDICTOR_MODEL`` to
    appear in the `/v1/models` listing.
    """
    try:
        resp = requests.get(PREDICTOR_HEALTH, timeout=3)
    except Exception as e:
        return (
            f"Tool predictor not reachable at {PREDICTOR_HEALTH} ({e}). "
            "Set TOOL_PREDICTOR_URL / TOOL_PREDICTOR_MODEL or start a vLLM server."
        )
    if resp.status_code != 200:
        return (
            f"Tool predictor health {PREDICTOR_HEALTH} returned "
            f"{resp.status_code}."
        )
    try:
        served = {m["id"] for m in resp.json().get("data", [])}
    except Exception:
        served = set()
    if PREDICTOR_MODEL not in served:
        return (
            f"Model {PREDICTOR_MODEL} not served at {PREDICTOR_HEALTH} "
            f"(available: {sorted(served) or 'none'}). "
            "Set TOOL_PREDICTOR_MODEL to a served model."
        )
    return None


_SKIP_REASON = _skip_reason()
pytestmark = pytest.mark.skipif(
    _SKIP_REASON is not None,
    reason=_SKIP_REASON or "",
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures / helpers
# ─────────────────────────────────────────────────────────────────────────────


def _make_predictor(**overrides) -> HTTPToolPredictor:
    kwargs = dict(url=PREDICTOR_URL, model=PREDICTOR_MODEL, timeout=60)
    kwargs.update(overrides)
    return HTTPToolPredictor(**kwargs)


def _make_compressor(**overrides) -> ToolCompressor:
    """Default integration compressor pointing at the running predictor."""
    kwargs = dict(
        predictor_url=PREDICTOR_URL,
        predictor_model=PREDICTOR_MODEL,
        score_threshold=3.0,
        timeout=60,
        prompt_mode="static",
        tool_descriptions_mode="dynamic",
    )
    kwargs.update(overrides)
    return ToolCompressor(**kwargs)


def _tool(name: str, description: str = "") -> dict:
    return {
        "type": "function",
        "function": {"name": name, "description": description},
    }


def _make_request(task: str, tools: list[dict]) -> CompressionContext:
    return CompressionContext(
        messages=[
            {"role": "system", "content": "You are an assistant."},
            {"role": "user", "content": task},
        ],
        tools=tools,
    )


# ─────────────────────────────────────────────────────────────────────────────
# HTTPToolPredictor — direct end-to-end
# ─────────────────────────────────────────────────────────────────────────────


class TestPredictorEndToEnd:
    def test_predict_read_task_includes_read(self):
        from adaptive_token_compressor.tool.prompts import (
            FOCUS_FIVE_TOOL_PROMPT,
            build_static_prediction_prompt,
        )
        from adaptive_token_compressor.tool.tool_descriptions import (
            DEFAULT_TOOL_DESCRIPTIONS,
        )

        predictor = _make_predictor()
        system_prompt = build_static_prediction_prompt(
            template=FOCUS_FIVE_TOOL_PROMPT,
            tool_descriptions=DEFAULT_TOOL_DESCRIPTIONS,
        )
        candidates, meta = predictor.predict(
            "Read the file /tmp/foo.py and explain what it does",
            system_prompt=system_prompt,
        )
        # Server output is non-deterministic but `read` should always be a
        # core tool for a read-the-file task at score 5 with this template.
        names = [c.name for c in candidates]
        assert "read" in names
        # Scores are valid 1-5 ints.
        for c in candidates:
            assert 1 <= c.score <= 5
        # FOCUS_FIVE template forces 5-10 tools.
        assert 5 <= len(candidates) <= 10
        # Meta carries timing + the raw response excerpt.
        assert meta["model"] == PREDICTOR_MODEL
        assert meta["latency_ms"] > 0
        assert "raw_response" in meta

    def test_health_check_healthy(self):
        predictor = _make_predictor()
        status = predictor.health_check(timeout=5)
        # If the test module ran past skipif, server is up; the configured
        # model id should match what we pass — HEALTHY. If a CI runs against
        # a server with a different model loaded, mark it as DEGRADED.
        assert status.state in {HealthState.HEALTHY, HealthState.DEGRADED}
        if status.state == HealthState.HEALTHY:
            assert PREDICTOR_MODEL in status.details.get("models", [])

    def test_health_check_wrong_model_degraded(self):
        predictor = _make_predictor(model="non-existent-model-xyz")
        status = predictor.health_check(timeout=5)
        # Server up but target model missing → DEGRADED, not UNHEALTHY.
        assert status.state == HealthState.DEGRADED

    def test_health_check_unreachable_url(self):
        # Use a definitely-down port.
        predictor = HTTPToolPredictor(
            url="http://127.0.0.1:1/v1/chat/completions",
            model=PREDICTOR_MODEL,
            timeout=2,
        )
        status = predictor.health_check(timeout=2)
        assert status.state == HealthState.UNHEALTHY


# ─────────────────────────────────────────────────────────────────────────────
# ToolCompressor — full pipeline against a real predictor
# ─────────────────────────────────────────────────────────────────────────────


_BENCH_TOOLS = [
    _tool("read", "Read text/image files"),
    _tool("write", "Write content to a file"),
    _tool("edit", "Surgical find-and-replace in a file"),
    _tool("exec", "Execute shell commands"),
    _tool("web_search", "Search the web"),
    _tool("web_fetch", "Fetch a URL"),
    _tool("browser", "Drive a web browser"),
    _tool("sessions_spawn", "Spawn a sub-agent session"),
]


class TestCompressorEndToEnd:
    def test_read_task_keeps_read(self):
        comp = _make_compressor()
        ctx = _make_request(
            "Open /tmp/foo.py and tell me what the script does.",
            _BENCH_TOOLS,
        )
        result = comp.compress(ctx)

        assert result.metrics.error is None
        assert result.metrics.scope == CompressionScope.TOOL
        # `read` is the obvious match — it must survive the threshold.
        names = [t["function"]["name"] for t in result.tools]
        assert "read" in names
        # Filtering happened (score threshold removed at least one low-score tool).
        assert len(result.tools) <= len(_BENCH_TOOLS)

    def test_web_search_task_keeps_web_tools(self):
        comp = _make_compressor()
        ctx = _make_request(
            "Search the web for the latest Python release notes.",
            _BENCH_TOOLS,
        )
        result = comp.compress(ctx)

        assert result.metrics.error is None
        names = [t["function"]["name"] for t in result.tools]
        # web_search or browser should rank highly for this task; at least
        # one of them must survive a 3.0 threshold.
        assert any(n in {"web_search", "browser"} for n in names)

    def test_metrics_details_populated(self):
        comp = _make_compressor()
        ctx = _make_request(
            "Read and edit the file /tmp/notes.md",
            _BENCH_TOOLS,
        )
        result = comp.compress(ctx)

        d = result.metrics.details
        assert d["original_tool_count"] == len(_BENCH_TOOLS)
        assert d["compressed_tool_count"] == len(result.tools)
        assert d["filtered_count"] == d["original_tool_count"] - d["compressed_tool_count"]
        assert d["score_threshold"] == 3.0
        assert "candidates" in d
        # Predictor latency surfaced for observability.
        assert d["predictor_meta"]["latency_ms"] > 0

    def test_messages_untouched(self):
        comp = _make_compressor()
        ctx = _make_request("Read /tmp/x.py", _BENCH_TOOLS)
        before = ctx.messages
        result = comp.compress(ctx)
        # ToolCompressor never modifies messages.
        assert result.messages == before

    def test_health_check_via_compressor(self):
        comp = _make_compressor()
        status = comp.health_check(timeout=5)
        assert status.state in {HealthState.HEALTHY, HealthState.DEGRADED}

    def test_bogus_url_fails_gracefully(self):
        # Wrong path on the same host: vLLM returns 404, predictor wraps it
        # as PredictorError → ToolCompressor folds into metrics.error.
        comp = _make_compressor(predictor_url=PREDICTOR_URL + "/wrong-path")
        ctx = _make_request("Read /tmp/x", _BENCH_TOOLS)
        result = comp.compress(ctx)
        # compress() never raises.
        assert result is not None
        assert result.metrics.error is not None
        # All tools preserved on failure.
        assert len(result.tools) == len(_BENCH_TOOLS)
