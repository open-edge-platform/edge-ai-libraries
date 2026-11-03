"""Tests for context/compressor.py — the ContextCompressor assembly.

Covers §13 row `context/compressor` + prefix-cache T1/T3/T4/T8.

Two backend paths are exercised (B6 gate):
  ① FakeBackend via `comp._backend = FakeBackend(...)` — token-saved paths,
     claw routing, cache diagnostics, failure modes (CI-friendly, no HTTP).
  ② TokenPruneBackend + `responses` HTTP mock — real backend wiring, backend
     error propagation, multi-failure, claw fallback.
"""
from __future__ import annotations

import json
import sys
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock

import cachetools
import pytest
import responses

from adaptive_token_compressor.context.compressor import ContextCompressor
from adaptive_token_compressor.core.backends import BackendError
from adaptive_token_compressor.core.base import CompressionContext
from adaptive_token_compressor.core.exceptions import ConfigError
from adaptive_token_compressor.core.health import HealthStatus
from adaptive_token_compressor.core.metrics import CompressionScope

_SAVED_FIELDS = (
    "status_tokens_saved",
    "error_tokens_saved",
    "web_search_strip_tokens_saved",
    "web_search_compress_tokens_saved",
    "other_compress_tokens_saved",
    "other_claw_tokens_saved",
    "assistant_args_tokens_saved",
)

COMPRESS_SERVER_URL = "http://localhost:8001/compress"


# ─────────────────────────────────────────────────────────────────────────────
# Test doubles
# ─────────────────────────────────────────────────────────────────────────────


class FakeBackend:
    """Records calls; returns a short deterministic marker per input."""

    cache_tag = "token_prune"

    def __init__(self, fail: bool = False):
        self.calls: list[tuple] = []
        self.fail = fail

    def compress(
        self,
        text,
        *,
        mode=None,
        rate,
        force_tokens=None,
        force_reserve_digit=False,
        digit_neighbor_radius=0,
        **_unused,
    ):
        self.calls.append((text, rate, force_reserve_digit, digit_neighbor_radius))
        if self.fail:
            raise BackendError("boom", component="fake")
        return f"C[{len(text)}]"

    def health_check(self, *, timeout=5.0):
        ...


class FakeClawAdapter:
    """Detects a fixed type; compress prefixes so output is shorter + stable."""

    def __init__(self, content_type: str = "code", raise_on_compress: bool = False):
        self._ct = content_type
        self._raise = raise_on_compress
        self.detect_calls = 0
        self.compress_calls = 0

    def detect(self, content: str) -> str:
        self.detect_calls += 1
        return self._ct

    def compress_with_claw(self, content: str, content_type: str) -> str:
        self.compress_calls += 1
        if self._raise:
            raise RuntimeError("claw boom")
        return f"CLAW[{len(content)}]"


def _standalone(**kw) -> ContextCompressor:
    # Rule/backend dispatch without a window; argument tests opt in separately.
    # Current defaults are tested in TestV01Defaults.
    options = {"protect_recent_tool_turns": 0, "compression_mode": "backend_only", **kw}
    return ContextCompressor(**options)


def _with_cache(comp: ContextCompressor) -> ContextCompressor:
    comp.set_cache(cachetools.LRUCache(maxsize=256), threading.Lock())
    return comp


def _long_zh(n: int = 300) -> str:
    return "根据您提供的资料" * n


_RUNNING = (
    "Command still running (session delta-shoal, pid 2812401). "
    "Use process (list/poll/log/write/kill/clear/remove) for follow-up."
)


def _process_poll(tc_id: str, session: str = "delta-shoal") -> dict:
    return {
        "role": "assistant",
        "tool_calls": [{
            "id": tc_id,
            "type": "function",
            "function": {"name": "process",
                         "arguments": json.dumps({"action": "poll", "sessionId": session})},
        }],
    }


def _assistant_with_long_args(tc_id: str = "a") -> dict:
    return {
        "role": "assistant",
        "tool_calls": [{
            "id": tc_id,
            "type": "function",
            "function": {"name": "write", "arguments": json.dumps({"content": "X" * 1000})},
        }],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Construction (path independent)
# ─────────────────────────────────────────────────────────────────────────────


class TestConstruction:
    def test_unsupported_compression_mode_raises(self):
        with pytest.raises(ConfigError, match="mode"):
            _standalone(compression_mode="unsupported")

    def test_bad_compress_rate_raises(self):
        with pytest.raises(ConfigError):
            ContextCompressor(compress_rate=1.5, compression_mode='none')

    def test_zero_compress_rate_raises(self):
        with pytest.raises(ConfigError):
            ContextCompressor(compress_rate=0.0, compression_mode='none')

    def test_negative_min_chars_raises(self):
        with pytest.raises(ConfigError):
            ContextCompressor(compress_min_chars=-1, compression_mode='none')

    def test_non_positive_compress_timeout_raises(self):
        with pytest.raises(ConfigError):
            ContextCompressor(timeout=0, compression_mode='none')

    def test_claw_disabled_has_no_adapter(self):
        assert _standalone()._claw_adapter is None

    def test_claw_enabled_builds_adapter(self):
        pytest.importorskip("claw_compactor")
        comp = ContextCompressor(compression_mode='claw_with_backend')
        assert comp._claw_adapter is not None

    def test_name_and_scope(self):
        assert _standalone().name == "context"


# ─────────────────────────────────────────────────────────────────────────────
# Short-circuits
# ─────────────────────────────────────────────────────────────────────────────


class TestShortCircuits:
    def test_no_messages(self):
        r = _standalone().compress(CompressionContext(messages=[]))
        assert r.metrics.skip_reason == "no_messages"
        assert r.metrics.error is None
        assert r.messages == []

    def test_none_messages(self):
        r = _standalone().compress(CompressionContext(messages=None))
        assert r.metrics.skip_reason == "no_messages"

    def test_all_passthrough_user_only(self):
        r = _standalone().compress(CompressionContext(
            messages=[{"role": "user", "content": "hi"}]))
        assert r.metrics.skip_reason == "all_passthrough"
        assert r.metrics.error is None

    def test_all_passthrough_short_other(self):
        # 'Successfully wrote ...' is OTHER + below min_chars → passthrough.
        comp = _standalone()
        fb = FakeBackend()
        comp._backend = fb
        content = "Successfully wrote 99 bytes to /tmp/report.html"
        r = comp.compress(CompressionContext(
            messages=[{"role": "tool", "tool_call_id": "a", "content": content}]))
        assert r.metrics.skip_reason == "all_passthrough"
        assert r.messages[0]["content"] == content  # untouched
        assert fb.calls == []                        # backend never called

    @pytest.mark.parametrize("content", [
        "(no output)",
        '{"status":"error","tool":"exec","error":"failed"}',
        '{"results":[{"title":"result","snippet":"text"}]}',
        "long output " * 500,
    ])
    def test_tool_results_disabled_outside_window_keeps_original(self, content):
        comp = _standalone(tool_results=False)
        comp._backend = backend = FakeBackend()
        message = {"role": "tool", "tool_call_id": "result", "content": content}
        result = comp.compress(CompressionContext(messages=[message]))
        assert result.messages[0] is message
        assert result.metrics.skip_reason == "all_passthrough"
        assert result.metrics.error is None
        assert result.metrics.details["tool_result_messages_passthrough"] == 1
        assert result.metrics.details["protected_messages"] == 0
        assert all(result.metrics.details[key] == 0 for key in _SAVED_FIELDS)
        assert backend.calls == []

    def test_scope_is_context(self):
        r = _standalone().compress(CompressionContext(messages=[]))
        assert r.metrics.scope == CompressionScope.CONTEXT

    def test_tools_forwarded(self):
        tools = [{"type": "function", "function": {"name": "x"}}]
        r = _standalone().compress(CompressionContext(messages=[], tools=tools))
        assert r.tools == tools


# ─────────────────────────────────────────────────────────────────────────────
# Path ① — FakeBackend: dispatch + token-saved invariant
# ─────────────────────────────────────────────────────────────────────────────


class TestDispatchFake:
    def _run(self, messages, **kw):
        comp = _standalone(**kw)
        fb = FakeBackend()
        comp._backend = fb
        r = comp.compress(CompressionContext(messages=messages))
        return r, fb

    def test_invariant_sum_saved_equals_before_minus_after(self):
        messages = [
            {"role": "user", "content": "hi"},
            _assistant_with_long_args("a"),
            {"role": "tool", "tool_call_id": "b", "content": "(no output)"},   # STATUS drop
            {"role": "tool", "tool_call_id": "a", "content": "Command still running xyz"},  # STATUS stub
            {"role": "tool", "tool_call_id": "c",
             "content": '{"status":"error","tool":"bash","error":"boom"}'},    # ERROR
            {"role": "tool", "tool_call_id": "d", "content": _long_zh()},      # OTHER-branch backend
        ]
        r, _ = self._run(messages, assistant_arguments=True)
        d = r.metrics.details
        assert sum(d[k] for k in _SAVED_FIELDS) == r.metrics.tokens_before - r.metrics.tokens_after
        assert d["assistant_args_tokens_saved"] > 0

    def test_status_drop_when_no_matching_assistant_call(self):
        r, _ = self._run([{"role": "tool", "tool_call_id": "x", "content": "(no output)"}])
        # Dropped entirely (no assistant.tool_calls has id "x").
        assert all(m.get("content") != "(no output)" for m in r.messages)
        assert len(r.messages) == 0
        assert r.metrics.details["status_tokens_saved"] > 0

    def test_status_stub_when_session_followed_up(self):
        messages = [
            _assistant_with_long_args("a"),
            {"role": "tool", "tool_call_id": "a", "content": _RUNNING},
            _process_poll("p"),
            {"role": "tool", "tool_call_id": "p", "content": "done"},
        ]
        r, _ = self._run(messages)
        assert r.messages[1]["content"] == "(elided status)"
        assert r.messages[1]["tool_call_id"] == "a"  # pairing preserved
        assert r.metrics.details["status_tokens_saved"] > 0

    def test_running_status_kept_until_followed_up(self):
        # Without a later call naming the session, the session handle is the
        # only way to poll the process → verbatim.
        messages = [
            _assistant_with_long_args("a"),
            {"role": "tool", "tool_call_id": "a", "content": _RUNNING},
        ]
        r, _ = self._run(messages)
        assert r.messages[1]["content"] == _RUNNING

    def test_running_status_other_session_not_followed_up(self):
        messages = [
            _assistant_with_long_args("a"),
            {"role": "tool", "tool_call_id": "a", "content": _RUNNING},
            _process_poll("p", session="calm-sable"),
            {"role": "tool", "tool_call_id": "p", "content": "done"},
        ]
        r, _ = self._run(messages)
        assert r.messages[1]["content"] == _RUNNING

    @pytest.mark.parametrize("content", ["(no output)", "(no new output)",
                                         "(no new output)\n\nProcess still running."])
    def test_paired_no_output_kept_verbatim(self, content):
        # The stub is no shorter and hides "succeeded with no output".
        messages = [
            _assistant_with_long_args("a"),
            {"role": "tool", "tool_call_id": "a", "content": content},
        ]
        r, _ = self._run(messages)
        assert r.messages[1]["content"] == content
        assert r.metrics.details["status_tokens_saved"] == 0

    def test_error_simplified(self):
        r, _ = self._run([{"role": "tool", "tool_call_id": "c",
                           "content": '{"status":"error","tool":"grep","error":"no match"}'}])
        assert r.messages[0]["content"] == "grep failed: no match"
        assert r.metrics.details["error_tokens_saved"] > 0

    def test_error_with_extra_fields_stays_verbatim(self):
        content = '{"status":"error","tool":"exec","error":"failed","exit_code":2}'
        message = {"role": "tool", "tool_call_id": "error", "content": content}
        result, backend = self._run([message])
        assert result.messages[0] is message
        assert result.metrics.skip_reason == "all_passthrough"
        assert result.metrics.details["error_tokens_saved"] == 0
        assert backend.calls == []

    @pytest.mark.parametrize("content", [
        None, [], [{"type": "text", "text": "source text"}],
        [{"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}}],
    ])
    def test_non_string_tool_content_stays_verbatim(self, content):
        message = {"role": "tool", "tool_call_id": "parts", "content": content}
        result, backend = self._run([message])
        assert result.messages[0] is message
        assert result.metrics.skip_reason == "all_passthrough"
        assert backend.calls == []

    def test_other_short_passthrough_no_backend_call(self):
        r, fb = self._run([{"role": "tool", "tool_call_id": "a", "content": "short output"}])
        assert fb.calls == []
        assert r.metrics.details["other_compress_tokens_saved"] == 0

    def test_other_long_goes_to_backend(self):
        r, fb = self._run([{"role": "tool", "tool_call_id": "a", "content": _long_zh()}])
        assert len(fb.calls) == 1
        assert fb.calls[0][1] == 0.6  # rate
        assert r.metrics.details["other_compress_tokens_saved"] > 0

    def test_assistant_args_digested(self):
        messages = [
            _assistant_with_long_args("a"),
            {"role": "tool", "tool_call_id": "a", "content": "done"},
        ]
        r, _ = self._run(messages, assistant_arguments=True)
        assert r.metrics.details["assistant_args_tokens_saved"] > 0
        assistant = [m for m in r.messages if m.get("role") == "assistant"][0]
        assert "arg_preview" in assistant["tool_calls"][0]["function"]["arguments"]


# ─────────────────────────────────────────────────────────────────────────────
# Path ① — WEB_SEARCH two-stage
# ─────────────────────────────────────────────────────────────────────────────


class TestWebSearchFake:
    def test_lossless_strip_without_savings_keeps_original(self, monkeypatch, tavily_content):
        from adaptive_token_compressor.context import compressor as module

        monkeypatch.setattr(module, "web_search_strip", lambda content: content)
        comp = _standalone(compression_mode='none')
        comp._backend = backend = FakeBackend()
        message = {"role": "tool", "tool_call_id": "search", "content": tavily_content}
        result = comp.compress(CompressionContext(messages=[message]))
        assert result.messages[0] is message
        assert result.metrics.skip_reason == "all_passthrough"
        assert result.metrics.details["web_search_strip_tokens_saved"] == 0
        assert result.metrics.details["web_search_compress_tokens_saved"] == 0
        assert backend.calls == []

    def test_two_stage_savings(self, tavily_content):
        comp = _standalone()
        fb = FakeBackend()
        comp._backend = fb
        r = comp.compress(CompressionContext(
            messages=[{"role": "tool", "tool_call_id": "w", "content": tavily_content}]))
        d = r.metrics.details
        assert d["web_search_strip_tokens_saved"] > 0
        assert d["web_search_compress_tokens_saved"] > 0
        assert len(fb.calls) == 1                    # only the compress-server stage hits backend
        assert fb.calls[0][2] is True                # force_reserve_digit
        assert fb.calls[0][3] == 3                    # digit_neighbor_radius


# ─────────────────────────────────────────────────────────────────────────────
# Path ① — claw routing + fallback
# ─────────────────────────────────────────────────────────────────────────────


class TestClawRoutingFake:
    def test_code_routes_to_claw(self):
        comp = _standalone(compression_mode="claw_with_backend")
        fb = FakeBackend()
        comp._backend = fb
        comp._claw_adapter = FakeClawAdapter(content_type="code")
        r = comp.compress(CompressionContext(
            messages=[{"role": "tool", "tool_call_id": "a", "content": _long_zh()}]))
        assert r.metrics.details["other_claw_tokens_saved"] > 0
        assert fb.calls == []                        # claw handled it, compress-server untouched

    def test_text_type_routes_to_backend(self):
        comp = _standalone(compression_mode="claw_with_backend")
        fb = FakeBackend()
        comp._backend = fb
        comp._claw_adapter = FakeClawAdapter(content_type="text")
        r = comp.compress(CompressionContext(
            messages=[{"role": "tool", "tool_call_id": "a", "content": _long_zh()}]))
        assert r.metrics.details["other_compress_tokens_saved"] > 0
        assert len(fb.calls) == 1

    def test_claw_failure_falls_back_to_backend(self):
        comp = _standalone(compression_mode="claw_with_backend")
        fb = FakeBackend()
        comp._backend = fb
        comp._claw_adapter = FakeClawAdapter(content_type="code", raise_on_compress=True)
        r = comp.compress(CompressionContext(
            messages=[{"role": "tool", "tool_call_id": "a", "content": _long_zh()}]))
        assert r.metrics.details["claw_fallback_count"] == 1
        assert r.metrics.details["other_compress_tokens_saved"] > 0
        assert len(fb.calls) == 1                    # fell back to compress-server
        assert r.metrics.error is None               # fallback is not an error


# ─────────────────────────────────────────────────────────────────────────────
# Path ① — cache diagnostics
# ─────────────────────────────────────────────────────────────────────────────


class TestCacheDiagnostics:
    def test_claw_result_cached_without_repeating_compression(self):
        comp = _with_cache(_standalone(compression_mode="claw_with_backend"))
        comp._backend = backend = FakeBackend()
        comp._claw_adapter = adapter = FakeClawAdapter(content_type="code")
        ctx = CompressionContext(messages=[
            {"role": "tool", "tool_call_id": "code", "content": _long_zh()},
        ])
        first = comp.compress(ctx)
        second = comp.compress(ctx)
        assert first.messages == second.messages
        assert first.metrics.details["cache_misses"] == 1
        assert first.metrics.details["cache_hits"] == 0
        assert second.metrics.details["cache_hits"] == 1
        assert second.metrics.details["cache_misses"] == 0
        assert adapter.compress_calls == 1
        assert backend.calls == []

    def test_standalone_no_cache_counters(self):
        comp = _standalone()
        comp._backend = FakeBackend()
        r = comp.compress(CompressionContext(
            messages=[{"role": "tool", "tool_call_id": "a", "content": _long_zh()}]))
        assert r.metrics.details["cache_hits"] == 0
        assert r.metrics.details["cache_misses"] == 0  # standalone stays 0

    def test_miss_then_hit(self):
        comp = _with_cache(_standalone())
        fb = FakeBackend()
        comp._backend = fb
        msgs = [{"role": "tool", "tool_call_id": "a", "content": _long_zh()}]
        r1 = comp.compress(CompressionContext(messages=msgs))
        assert r1.metrics.details["cache_misses"] == 1
        assert r1.metrics.details["cache_hits"] == 0
        r2 = comp.compress(CompressionContext(messages=msgs))
        assert r2.metrics.details["cache_hits"] == 1
        assert len(fb.calls) == 1                    # backend only called once


# ─────────────────────────────────────────────────────────────────────────────
# Path ① — failure modes
# ─────────────────────────────────────────────────────────────────────────────


class TestFailureModesFake:
    @pytest.mark.parametrize("backend_fails", [False, True])
    def test_claw_detection_failure_uses_backend(
        self, monkeypatch, caplog, backend_fails,
    ):
        comp = _standalone(compression_mode="claw_with_backend")
        comp._backend = backend = FakeBackend(fail=backend_fails)
        comp._claw_adapter = adapter = FakeClawAdapter()
        monkeypatch.setattr(adapter, "detect", Mock(side_effect=RuntimeError("detect boom")))
        message = {"role": "tool", "tool_call_id": "code", "content": _long_zh()}
        result = comp.compress(CompressionContext(messages=[message]))
        assert "claw detection failed: RuntimeError" in caplog.text
        assert len(backend.calls) == 1
        assert adapter.compress_calls == 0
        assert "claw_fallback_count" not in result.metrics.details
        assert result.metrics.details["other_claw_tokens_saved"] == 0
        if backend_fails:
            assert result.messages[0] is message
            assert result.metrics.error == "boom"
            assert result.metrics.details["backend_errors"] == ["boom"]
            assert result.metrics.details["other_compress_tokens_saved"] == 0
            assert "Backend failed for OTHER message: boom" in caplog.text
        else:
            assert result.messages[0]["content"] == f"C[{len(message['content'])}]"
            assert result.metrics.error is None
            assert result.metrics.details["other_compress_tokens_saved"] > 0
        assert result.metrics.skip_reason is None

    def test_claw_and_backend_failure_preserves_original_and_does_not_cache(self, caplog):
        comp = _with_cache(_standalone(compression_mode="claw_with_backend"))
        comp._backend = backend = FakeBackend(fail=True)
        comp._claw_adapter = adapter = FakeClawAdapter(raise_on_compress=True)
        message = {"role": "tool", "tool_call_id": "code", "content": _long_zh()}
        ctx = CompressionContext(messages=[message])
        for _ in range(2):
            result = comp.compress(ctx)
            assert result.messages[0] is message
            assert result.metrics.error == "boom"
            assert result.metrics.skip_reason is None
            assert result.metrics.details["backend_errors"] == ["boom"]
            assert result.metrics.details["claw_fallback_count"] == 1
            assert result.metrics.details["other_claw_tokens_saved"] == 0
            assert result.metrics.details["other_compress_tokens_saved"] == 0
            assert result.metrics.details["cache_hits"] == 0
        assert adapter.compress_calls == len(backend.calls) == 2
        assert len(comp._cache) == 0
        assert "claw compression failed: RuntimeError" in caplog.text
        assert "Backend failed for OTHER message: boom" in caplog.text

    @pytest.mark.parametrize("healthy", [False, True])
    def test_health_check_forwards_backend_status_and_timeout(self, monkeypatch, healthy):
        comp = _standalone()
        comp._backend = backend = FakeBackend()
        status = (
            HealthStatus.healthy("fake") if healthy
            else HealthStatus.unhealthy("fake", "unavailable")
        )
        probe = Mock(return_value=status)
        monkeypatch.setattr(backend, "health_check", probe)
        assert comp.health_check(timeout=0.25) is status
        probe.assert_called_once_with(timeout=0.25)

    def test_single_backend_failure_fills_error(self):
        comp = _standalone()
        comp._backend = FakeBackend(fail=True)
        r = comp.compress(CompressionContext(
            messages=[{"role": "tool", "tool_call_id": "a", "content": _long_zh()}]))
        assert r.metrics.error == "boom"
        assert r.metrics.skip_reason is None
        assert r.metrics.details["backend_errors"] == ["boom"]
        # failed message keeps original content
        assert r.messages[0]["content"] == _long_zh()

    def test_multi_backend_failure_joined(self):
        comp = _standalone()
        comp._backend = FakeBackend(fail=True)
        r = comp.compress(CompressionContext(messages=[
            {"role": "tool", "tool_call_id": "a", "content": _long_zh()},
            {"role": "tool", "tool_call_id": "b", "content": _long_zh(301)},
        ]))
        assert r.metrics.error == "boom; boom"

    def test_web_search_backend_failure_keeps_stripped(self, tavily_content, caplog):
        comp = _standalone()
        comp._backend = FakeBackend(fail=True)
        r = comp.compress(CompressionContext(
            messages=[{"role": "tool", "tool_call_id": "w", "content": tavily_content}]))
        assert r.metrics.error == "boom"
        # stripped content retained (strip savings realized, compress-server failed)
        assert r.messages[0]["content"].startswith("Search: ")
        assert r.metrics.details["web_search_strip_tokens_saved"] > 0


# ─────────────────────────────────────────────────────────────────────────────
# Prefix-cache stability (T1 / T3 / T4 / T8)
# ─────────────────────────────────────────────────────────────────────────────


class TestPrefixCacheStability:
    def test_T1_same_messages_twice_byte_identical(self, conversation_history):
        # T4: FakeBackend keeps this CI-friendly (deterministic, no HTTP).
        def run():
            comp = _with_cache(_standalone())
            comp._backend = FakeBackend()
            return comp.compress(CompressionContext(messages=conversation_history)).messages
        assert run() == run()

    def test_T1_within_one_compressor_deterministic(self, conversation_history):
        comp = _with_cache(_standalone())
        comp._backend = FakeBackend()
        r1 = comp.compress(CompressionContext(messages=conversation_history))
        r2 = comp.compress(CompressionContext(messages=conversation_history))
        assert r1.messages == r2.messages

    def test_T3_growing_conversation_stable_prefix(self):
        # Round N+1 = round N + appended messages; the processed prefix must be
        # byte-identical across rounds (vLLM prefix-cache friendliness).
        base = [
            _assistant_with_long_args("a"),
            {"role": "tool", "tool_call_id": "a", "content": "Command still running x"},
            {"role": "tool", "tool_call_id": "z", "content": _long_zh()},
        ]
        comp = _with_cache(_standalone())
        comp._backend = FakeBackend()
        r1 = comp.compress(CompressionContext(messages=list(base))).messages
        grown = list(base) + [{"role": "user", "content": "next question"}]
        r2 = comp.compress(CompressionContext(messages=grown)).messages
        assert r2[: len(r1)] == r1

    def test_T4_fakebackend_no_http(self):
        # Explicit: a run with a stubbed backend touches no network.
        comp = _standalone()
        comp._backend = FakeBackend()
        r = comp.compress(CompressionContext(
            messages=[{"role": "tool", "tool_call_id": "a", "content": _long_zh()}]))
        assert r.metrics.error is None


# ─────────────────────────────────────────────────────────────────────────────
# Path ② — TokenPruneBackend + responses HTTP mock
# ─────────────────────────────────────────────────────────────────────────────


class TestBackendPathHTTP:
    @responses.activate
    def test_other_long_real_backend_wiring(self):
        responses.post(COMPRESS_SERVER_URL, json={"compressed_prompt": "SHORT"}, status=200)
        comp = _standalone(compress_server_url=COMPRESS_SERVER_URL)
        r = comp.compress(CompressionContext(
            messages=[{"role": "tool", "tool_call_id": "a", "content": _long_zh()}]))
        assert r.messages[0]["content"] == "SHORT"
        assert r.metrics.error is None
        assert len(responses.calls) == 1

    @responses.activate
    def test_web_search_sends_digit_guard(self, tavily_content):
        responses.post(COMPRESS_SERVER_URL, json={"compressed_prompt": "SHORT"}, status=200)
        comp = _standalone(compress_server_url=COMPRESS_SERVER_URL)
        comp.compress(CompressionContext(
            messages=[{"role": "tool", "tool_call_id": "w", "content": tavily_content}]))
        body = json.loads(responses.calls[0].request.body)
        assert body["force_reserve_digit"] is True
        assert body["digit_neighbor_radius"] == 3

    @responses.activate
    def test_backend_500_fills_error(self):
        responses.post(COMPRESS_SERVER_URL, json={"detail": "server error"}, status=500)
        comp = _standalone(compress_server_url=COMPRESS_SERVER_URL)
        r = comp.compress(CompressionContext(
            messages=[{"role": "tool", "tool_call_id": "a", "content": _long_zh()}]))
        assert r.metrics.error is not None
        assert r.messages[0]["content"] == _long_zh()  # original retained

    @responses.activate
    def test_multi_failure_joined(self):
        responses.post(COMPRESS_SERVER_URL, json={"detail": "err"}, status=500)
        comp = _standalone(compress_server_url=COMPRESS_SERVER_URL)
        r = comp.compress(CompressionContext(messages=[
            {"role": "tool", "tool_call_id": "a", "content": _long_zh()},
            {"role": "tool", "tool_call_id": "b", "content": _long_zh(301)},
        ]))
        assert "; " in r.metrics.error   # two joined failures

    @responses.activate
    def test_claw_fallback_over_http(self):
        # claw raises → fall back to the real HTTP compress-server backend.
        responses.post(COMPRESS_SERVER_URL, json={"compressed_prompt": "SHORT"}, status=200)
        comp = _standalone(compression_mode="claw_with_backend", compress_server_url=COMPRESS_SERVER_URL)
        comp._claw_adapter = FakeClawAdapter(content_type="code", raise_on_compress=True)
        r = comp.compress(CompressionContext(
            messages=[{"role": "tool", "tool_call_id": "a", "content": _long_zh()}]))
        assert r.messages[0]["content"] == "SHORT"
        assert r.metrics.details["claw_fallback_count"] == 1
        assert r.metrics.error is None

# ─────────────────────────────────────────────────────────────────────────────
# Concurrency — per-call `details` isolation (no shared mutable state)
# ─────────────────────────────────────────────────────────────────────────────


class _SlowFakeBackend:
    """FakeBackend that sleeps inside compress(), widening the window in which
    a *shared* details dict (the old `self._details`) would be clobbered by a
    concurrent compress() on the same instance."""

    cache_tag = "token_prune"

    def __init__(self, delay: float = 0.002):
        self._delay = delay

    def compress(
        self,
        text,
        *,
        mode=None,
        rate,
        force_tokens=None,
        force_reserve_digit=False,
        digit_neighbor_radius=0,
        **_unused,
    ):
        time.sleep(self._delay)
        return f"C[{len(text)}]"

    def health_check(self, *, timeout=5.0):
        ...


class TestConcurrentCompress:
    """`details` is per-call (a local dict threaded through the helpers), not
    `self._details`. Many threads sharing one compressor instance must each get
    a self-consistent CompressorResult — the 7-field saved invariant must hold
    on every result. A regression to shared instance state would interleave the
    counters and break the invariant on some results.
    """

    def test_concurrent_compress_details_isolated(self):
        import threading

        comp = _standalone(assistant_arguments=True)
        comp._backend = _SlowFakeBackend()

        # Each thread compresses a DISTINCT message mix so a shared details dict
        # would cross-contaminate different token totals (easy to detect).
        def ctx_for(i: int) -> CompressionContext:
            reps = 300 + i  # distinct OTHER-branch backend payload size per thread
            return CompressionContext(messages=[
                {"role": "user", "content": "hi"},
                _assistant_with_long_args(f"a{i}"),
                {"role": "tool", "tool_call_id": f"a{i}", "content": "根据您提供的资料" * reps},
            ])

        results: dict[int, object] = {}
        errors: list[Exception] = []

        def worker(i: int) -> None:
            try:
                results[i] = comp.compress(ctx_for(i))
            except Exception as e:  # pragma: no cover
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(24)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert len(results) == 24
        for r in results.values():
            d = r.metrics.details
            # The core invariant: 7 saved fields sum to before-after. If two
            # calls shared one details dict this fails on the clobbered ones.
            assert sum(d[k] for k in _SAVED_FIELDS) == r.metrics.tokens_before - r.metrics.tokens_after
            # Real work happened on each (args digest + OTHER-branch backend).
            assert d["assistant_args_tokens_saved"] > 0
            assert d["other_compress_tokens_saved"] > 0

    def test_concurrent_cache_counters_isolated(self):
        # cache_hits/misses live in the per-call details too; with a shared
        # cache each thread's counters must still only reflect its own lookups.
        import threading

        comp = _with_cache(_standalone())
        comp._backend = _SlowFakeBackend()

        def worker(i: int, out: dict) -> None:
            r = comp.compress(CompressionContext(messages=[
                {"role": "tool", "tool_call_id": f"t{i}", "content": _long_zh(300 + i)},
            ]))
            out[i] = r.metrics.details

        out: dict[int, dict] = {}
        threads = [threading.Thread(target=worker, args=(i, out)) for i in range(16)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Each call did exactly one OTHER-branch backend lookup → its own details records
        # exactly one hit-or-miss, never an inflated cross-thread tally.
        for d in out.values():
            assert d["cache_hits"] + d["cache_misses"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# Verbatim passthrough for read / exec / edit tool results (rewrite-loop fix)
# ─────────────────────────────────────────────────────────────────────────────


def _tool_result(tool_id: str, tool_name: str, content: str) -> list[dict]:
    """An assistant tool_call + its tool result, so tool_call_id → tool name
    can be resolved by the compressor."""
    return [
        {"role": "assistant", "tool_calls": [{
            "id": tool_id, "type": "function",
            "function": {"name": tool_name, "arguments": "{}"},
        }]},
        {"role": "tool", "tool_call_id": tool_id, "content": content},
    ]


class TestReadExecEditPassthrough:
    """read/exec/edit results are what the agent reads back verbatim; lossily
    compressing them mangles structure and triggers rewrite loops. They must
    pass through untouched even when long enough to hit the OTHER branch.
    """

    def _run(self, messages):
        comp = _standalone(excluded_tools=["read", "exec", "edit"])
        fb = FakeBackend()
        comp._backend = fb
        r = comp.compress(CompressionContext(messages=messages))
        return r, fb

    def test_read_result_passthrough(self):
        content = _long_zh()  # > compress_min_chars, would normally compress
        r, fb = self._run(_tool_result("r1", "read", content))
        tool_msg = [m for m in r.messages if m.get("role") == "tool"][0]
        assert tool_msg["content"] == content     # verbatim
        assert fb.calls == []                     # backend never called
        assert r.metrics.details["other_compress_tokens_saved"] == 0

    def test_exec_result_passthrough(self):
        r, fb = self._run(_tool_result("e1", "exec", _long_zh()))
        assert fb.calls == []

    def test_edit_result_passthrough(self):
        r, fb = self._run(_tool_result("d1", "edit", _long_zh()))
        assert fb.calls == []

    def test_other_tool_still_compressed(self):
        # A long OTHER result from a non-protected tool (e.g. web_fetch) is
        # still compressed — the fix is scoped to read/exec/edit.
        r, fb = self._run(_tool_result("w1", "web_fetch", _long_zh()))
        assert len(fb.calls) == 1
        assert r.metrics.details["other_compress_tokens_saved"] > 0

    def test_passthrough_is_position_independent(self):
        # Same read result at two different depths compresses identically
        # (i.e. always passthrough) → prefix-cache stable regardless of position.
        content = _long_zh()
        early = _tool_result("r1", "read", content)
        grown = (
            _tool_result("r1", "read", content)
            + [{"role": "user", "content": "next"}]
            + _tool_result("r2", "read", content)
        )
        comp = _standalone(excluded_tools=["read", "exec", "edit"]); comp._backend = FakeBackend()
        r1 = comp.compress(CompressionContext(messages=early)).messages
        r2 = comp.compress(CompressionContext(messages=grown)).messages
        # the first read result is byte-identical in both runs
        assert r1[1]["content"] == r2[1]["content"] == content


class TestExcludedTools:
    @pytest.mark.parametrize("excluded", [(), []])
    def test_no_implicit_read_exclusion(self, excluded):
        comp = _standalone(excluded_tools=excluded)
        comp._backend = fb = FakeBackend()
        comp.compress(CompressionContext(messages=_tool_result("r", "read", _long_zh())))
        assert len(fb.calls) == 1

    @pytest.mark.parametrize("invalid", [None, "read", True, {"read"}, [1], [None], [""], [" "], [" read"]])
    def test_invalid_config(self, invalid):
        with pytest.raises(ConfigError, match="excluded_tools"):
            _standalone(excluded_tools=invalid)

    def test_old_parameter_rejected(self):
        with pytest.raises(TypeError, match="protect_tool_results"):
            _standalone(protect_tool_results=True)

    @pytest.mark.parametrize("guidance", ["legacy", "recovery"])
    def test_exclusion_precedes_s_and_backend(self, guidance):
        messages = (
            _tool_result("r", "read", _long_zh())
            + _tool_result("e", "exec", _long_zh())
            + _tool_result("latest", "read", "done")
        )
        comp = _standalone(excluded_tools=["read"], large_result_stub=True, large_result_min_tokens=100, large_result_keep_tool_turns=1, large_result_stub_guidance=guidance)
        comp._backend = fb = FakeBackend()
        result = comp.compress(CompressionContext(messages=messages))
        assert result.messages[1] is messages[1]
        assert result.messages[3]["content"].startswith("[historical tool output omitted")
        assert fb.calls == []
        assert result.metrics.details["excluded_tools"] == ["read"]
        assert result.metrics.details["excluded_tool_results"] == 2
        assert result.metrics.details["large_result_stubs"] == 1

    @pytest.mark.parametrize("keep", [0, 2])
    @pytest.mark.parametrize("guidance", ["legacy", "recovery"])
    @pytest.mark.parametrize("content", [
        '{"status":"error","tool":"read","error":"File not found"}',
        "Command still running (session delta-shoal, pid 123). Use process for follow-up.",
        [{"type": "text", "text": "long output " * 500, "extra": 1}],
    ])
    def test_exclusion_precedes_rules_and_window(self, keep, guidance, content):
        messages = _tool_result("r", "read", content) + [_process_poll("poll")]
        comp = _standalone(protect_recent_tool_turns=keep, excluded_tools=["read"], large_result_stub=True, large_result_min_tokens=1, large_result_stub_guidance=guidance)
        result = comp.compress(CompressionContext(messages=messages))
        assert result.messages[1] is messages[1]
        assert result.metrics.details["large_result_stubs"] == 0
        assert result.metrics.details["status_tokens_saved"] == 0
        assert result.metrics.details["error_tokens_saved"] == 0

    def test_custom_tool_web_search_bypasses_backend(self):
        content = '{"results":[{"title":"result","url":"https://example.com","snippet":"text"}]}'
        messages = _tool_result("search", "custom_search", content)
        comp = _standalone(excluded_tools=["custom_search"])
        comp._backend = fb = FakeBackend()
        result = comp.compress(CompressionContext(messages=messages))
        assert result.messages[1] is messages[1]
        assert fb.calls == []

    def test_result_exclusion_does_not_protect_arguments(self):
        messages = [_assistant_with_long_args("r"), {
            "role": "tool", "tool_call_id": "r", "content": _long_zh(),
        }]
        name = messages[0]["tool_calls"][0]["function"]["name"]
        comp = _standalone(assistant_arguments=True, excluded_tools=[name])
        result = comp.compress(CompressionContext(messages=messages))
        assert result.messages[1] is messages[1]
        assert result.messages[0] != messages[0]

    def test_config_list_is_copied_and_matching_is_exact(self):
        names = ["read", "read"]
        comp = _standalone(excluded_tools=names)
        names.append("exec")
        comp._backend = fb = FakeBackend()
        messages = _tool_result("r", "Read", _long_zh()) + _tool_result("e", "exec", _long_zh())
        result = comp.compress(CompressionContext(messages=messages))
        assert len(fb.calls) == 2
        assert result.metrics.details["excluded_tools"] == ["read"]


# ─────────────────────────────────────────────────────────────────────────────
# v0_1 — window gate, stride, lossy switch, leak counter (design v8 §14.1)
# ─────────────────────────────────────────────────────────────────────────────


def _write_turn(i: int) -> list[dict]:
    """One tool turn: a completed write with long args + a long result."""
    tc_id = f"w{i}"
    return [
        {"role": "assistant", "tool_calls": [{
            "id": tc_id, "type": "function",
            "function": {"name": "write",
                         "arguments": json.dumps({"path": f"/tmp/f{i}", "content": "X" * 1000})},
        }]},
        {"role": "tool", "tool_call_id": tc_id, "content": _long_zh(300 + i)},
    ]


def _session(n_turns: int) -> list[dict]:
    msgs = [{"role": "user", "content": "task"}]
    for i in range(n_turns):
        msgs += _write_turn(i)
    return msgs


def _v01(**kw) -> ContextCompressor:
    """Current defaults (window on, lossy and arguments off) unless overridden."""
    comp = ContextCompressor(**kw)
    comp._backend = FakeBackend()
    return comp


def _compressed_turns(original: list[dict], out: list[dict]) -> list[int]:
    """Indices of tool turns whose assistant message was rewritten."""
    turns = [i for i, m in enumerate(original) if m.get("role") == "assistant" and m.get("tool_calls")]
    return [n for n, i in enumerate(turns) if out[i] is not original[i]]


class TestV01Defaults:
    def test_defaults(self):
        comp = ContextCompressor()
        assert comp._assistant_arguments is False
        assert comp._policy.enabled is True
        assert comp._large_result_stub is True
        assert comp._compression_mode == "none"
        assert comp._claw_adapter is None
        assert comp._protect_recent_tool_turns == 1
        assert comp._compress_stride_tool_turns == 1
        assert comp.effective_config["large_result_keep_tool_turns"] == 6

    def test_claw_disabled_by_default_even_with_lossy(self, monkeypatch):
        monkeypatch.setitem(
            sys.modules, "adaptive_token_compressor.context.claw_adapter", None)
        assert ContextCompressor()._claw_adapter is None
        assert ContextCompressor(compression_mode='backend_only')._claw_adapter is None

    @pytest.mark.parametrize("lossy", [False, True])
    def test_assistant_arguments_disabled_by_default(self, lossy):
        comp = _v01(protect_recent_tool_turns=0, compression_mode='backend_only' if lossy else 'none')
        msgs = _session(2)
        result = comp.compress(CompressionContext(messages=msgs))
        assert _compressed_turns(msgs, result.messages) == []
        assert result.metrics.details["assistant_args_tokens_saved"] == 0
        assert len(comp._backend.calls) == (2 if lossy else 0)

    def test_lossy_off_never_imports_claw(self, monkeypatch):
        # A None entry in sys.modules makes the inline import raise
        # ImportError, as if the claw-compactor extra were missing.
        monkeypatch.setitem(
            sys.modules, "adaptive_token_compressor.context.claw_adapter", None)
        assert ContextCompressor(compression_mode='none')._claw_adapter is None
        with pytest.raises(ConfigError):
            ContextCompressor(compression_mode='claw_with_backend')

    def test_bad_window_params_raise(self):
        with pytest.raises(ConfigError):
            ContextCompressor(protect_recent_tool_turns=-1, compression_mode='none')
        with pytest.raises(ConfigError):
            ContextCompressor(compress_stride_tool_turns=0, compression_mode='none')

    def test_lossy_off_never_calls_backend(self):
        comp = _v01(assistant_arguments=True, protect_recent_tool_turns=0)
        msgs = _session(3) + _tool_result("f1", "web_fetch", _long_zh())
        r = comp.compress(CompressionContext(messages=msgs))
        assert comp._backend.calls == []
        tool_msgs = [m for m in r.messages if m.get("role") == "tool"]
        assert all(m["content"].startswith("根据") for m in tool_msgs)   # verbatim
        assert r.metrics.details["assistant_args_tokens_saved"] > 0     # args still digested

    def test_lossy_off_never_calls_claw(self):
        comp = _v01(protect_recent_tool_turns=0)
        claw = FakeClawAdapter(content_type="code")
        comp._claw_adapter = claw
        comp.compress(CompressionContext(
            messages=_tool_result("f1", "web_fetch", _long_zh())))
        assert claw.detect_calls == 0
        assert claw.compress_calls == 0

    def test_lossy_off_web_search_strip_only(self, tavily_content):
        comp = _v01(protect_recent_tool_turns=0)
        r = comp.compress(CompressionContext(
            messages=[{"role": "tool", "tool_call_id": "w", "content": tavily_content}]))
        assert comp._backend.calls == []
        assert r.messages[0]["content"].startswith("Search: ")
        assert r.metrics.details["web_search_strip_tokens_saved"] > 0
        assert r.metrics.details["web_search_compress_tokens_saved"] == 0

    def test_health_check_skips_unused_backend(self):
        status = ContextCompressor(compression_mode='none').health_check()
        assert status.state.value == "healthy"
        assert status.details["backend"] == "unused"

    def test_details_echo_switches(self):
        r = _v01().compress(CompressionContext(messages=_session(1)))
        d = r.metrics.details
        assert d["assistant_arguments"] is False
        assert d["tool_result_policy_enabled"] is True
        assert d["compression_mode"] == "none"
        assert d["protect_recent_tool_turns"] == 1
        assert d["compress_stride_tool_turns"] == 1


class TestV01Window:
    def test_default_window_protects_latest_tool_turn(self):
        msgs = _session(3)
        comp = _v01(assistant_arguments=True, compression_mode='backend_only')
        result = comp.compress(CompressionContext(messages=msgs))
        assert _compressed_turns(msgs, result.messages) == [0, 1]
        assert all(result.messages[i] is msgs[i] for i in range(len(msgs) - 2, len(msgs)))
        assert len(comp._backend.calls) == 2
        assert result.metrics.details["protected_messages"] == 2

    def test_last_k_turns_untouched(self):
        msgs = _session(5)
        r = _v01(assistant_arguments=True, protect_recent_tool_turns=2, compression_mode='backend_only').compress(
            CompressionContext(messages=msgs))
        assert _compressed_turns(msgs, r.messages) == [0, 1, 2]
        # every message of the last 2 turns is the same object
        for i in range(len(msgs) - 4, len(msgs)):
            assert r.messages[i] is msgs[i]
        assert r.metrics.details["protected_messages"] == 4

    def test_window_protects_results_from_lossy(self):
        msgs = _session(3)
        comp = _v01(protect_recent_tool_turns=2, compression_mode='backend_only')
        comp.compress(CompressionContext(messages=msgs))
        # only turn 0's result reached the backend
        assert len(comp._backend.calls) == 1

    def test_fewer_turns_than_window_all_passthrough(self):
        msgs = _session(2)
        r = _v01(assistant_arguments=True, protect_recent_tool_turns=2, compression_mode='backend_only').compress(CompressionContext(messages=msgs))
        assert r.metrics.skip_reason == "all_passthrough"
        assert all(a is b for a, b in zip(r.messages, msgs))
        assert r.metrics.tokens_after == r.metrics.tokens_before

    def test_k0_matches_pre_v01(self):
        msgs = _session(3)
        a = _v01(assistant_arguments=True, protect_recent_tool_turns=0, compression_mode='backend_only').compress(
            CompressionContext(messages=msgs))
        assert _compressed_turns(msgs, a.messages) == [0, 1, 2]

    def test_orphan_tool_messages_before_first_turn_not_protected(self):
        msgs = [{"role": "tool", "tool_call_id": "x", "content": "(no output)"}] + _session(1)
        r = _v01(protect_recent_tool_turns=2).compress(CompressionContext(messages=msgs))
        assert all(m.get("content") != "(no output)" for m in r.messages)   # dropped

    @pytest.mark.parametrize("stride,expected", [
        # T = 2..7 tool turns, K = 2 → number of compressible turns F
        (1, [0, 1, 2, 3, 4, 5]),
        (2, [0, 0, 2, 2, 4, 4]),
        (3, [0, 0, 0, 3, 3, 3]),
    ])
    def test_stride_advances_in_batches(self, stride, expected):
        got = []
        for t in range(2, 8):
            msgs = _session(t)
            r = _v01(assistant_arguments=True, protect_recent_tool_turns=2, compress_stride_tool_turns=stride).compress(
                CompressionContext(messages=msgs))
            got.append(len(_compressed_turns(msgs, r.messages)))
        assert got == expected

    @pytest.mark.parametrize("lossy", [False, True])
    @pytest.mark.parametrize("stride", [1, 2])
    def test_monotonic_growing_session(self, lossy, stride):
        # Replay every request of a growing session: once a message is
        # compressed it is byte-identical in every later request, and the
        # compressed set only grows (prefix-cache safety).
        full = _session(8)
        comp = _with_cache(_v01(assistant_arguments=True, protect_recent_tool_turns=2, compress_stride_tool_turns=stride, compression_mode='backend_only' if lossy else 'none'))
        first_seen: dict[int, dict] = {}
        for m in range(2, len(full) + 1):
            out = comp.compress(CompressionContext(messages=full[:m])).messages
            assert len(out) == m
            for i, msg in enumerate(out):
                if msg is not full[i]:
                    if i in first_seen:
                        assert msg == first_seen[i]
                    first_seen[i] = msg
                else:
                    assert i not in first_seen, f"message {i} was un-compressed"
        assert first_seen

    def test_real_conversation_window(self, conversation_history):
        comp = _v01(assistant_arguments=True, protect_recent_tool_turns=2)
        r = comp.compress(CompressionContext(messages=conversation_history))
        assert len(r.messages) <= len(conversation_history)
        assert r.metrics.details["protected_messages"] > 0
        assert comp._backend.calls == []


class TestV01ErrorInsideWindow:
    """ERROR simplification is lossless, so it runs on first sight even
    inside the window (a delayed rewrite would break the prefix cache)."""

    _ERR = '{"status":"error","tool":"web_fetch","error":"fetch failed"}'

    def _msgs(self, err):
        return _session(1) + _tool_result("e1", "web_fetch", err)

    def test_latest_error_simplified(self):
        r = _v01(protect_recent_tool_turns=2).compress(CompressionContext(messages=self._msgs(self._ERR)))
        assert r.messages[-1]["content"] == "web_fetch failed: fetch failed"
        assert r.metrics.details["error_tokens_saved"] > 0
        assert r.metrics.skip_reason is None

    def test_error_with_extra_fields_untouched(self):
        err = '{"status":"error","tool":"exec","error":"boom","exitCode":2}'
        msgs = self._msgs(err)
        r = _v01(protect_recent_tool_turns=2).compress(CompressionContext(messages=msgs))
        assert r.messages[-1] is msgs[-1]
        assert r.metrics.skip_reason == "all_passthrough"

    def test_tool_results_off_keeps_error(self):
        msgs = self._msgs(self._ERR)
        r = _v01(protect_recent_tool_turns=2, tool_results=False).compress(
            CompressionContext(messages=msgs))
        assert r.messages[-1] is msgs[-1]

    def test_error_stable_across_requests(self):
        # Simplified on first sight → identical in every later request.
        msgs = self._msgs(self._ERR)
        comp = _v01(protect_recent_tool_turns=2)
        first = comp.compress(CompressionContext(messages=msgs)).messages[-1]
        grown = msgs + _session(3)[1:]
        later = comp.compress(CompressionContext(messages=grown)).messages[len(msgs) - 1]
        assert later == first


class TestV01ArgPreviewLeaks:
    def test_leak_counted(self, caplog):
        leaked = {"role": "assistant", "tool_calls": [{
            "id": "l", "type": "function",
            "function": {"name": "write", "arguments": json.dumps(
                {"path": "/tmp/r.md", "content": "<arg_preview kind=str chars=900 preview='x'>"})},
        }]}
        msgs = _session(1) + [leaked, {"role": "tool", "tool_call_id": "l", "content": "ok"}]
        with caplog.at_level("WARNING"):
            r = _v01().compress(CompressionContext(messages=msgs))
        assert r.metrics.details["arg_preview_leaks"] == 1
        assert "arg_preview marker" in caplog.text

    def test_no_leak_on_own_markers(self):
        # Markers the compressor itself writes are never counted: it scans
        # the raw input, not its output.
        r = _v01(assistant_arguments=True, protect_recent_tool_turns=0).compress(
            CompressionContext(messages=_session(3)))
        assert r.metrics.details["assistant_args_tokens_saved"] > 0
        assert r.metrics.details["arg_preview_leaks"] == 0


# ── v0_1 large-result stub (plan step 7) ─────────────────────────────────

_BIG = "\n".join(f"row {i}: value={i * 7} status=ok" for i in range(400))


def _read_turn(tc_id: str, content: str = _BIG) -> list[dict]:
    return [
        {"role": "assistant", "tool_calls": [{
            "id": tc_id, "type": "function",
            "function": {"name": "read", "arguments": json.dumps({"path": f"/tmp/{tc_id}.txt"})},
        }]},
        {"role": "tool", "tool_call_id": tc_id, "content": content},
    ]


def _stub_session(n_turns: int) -> list[dict]:
    msgs = [{"role": "user", "content": "task"}]
    for i in range(n_turns):
        msgs += _read_turn(f"r{i}")
    return msgs


def _stubbed(out: list[dict]) -> list[str]:
    return [m["tool_call_id"] for m in out
            if m.get("role") == "tool" and isinstance(m.get("content"), str)
            and m["content"].startswith("[historical tool output omitted")]


class TestIncompleteToolCalls:
    @pytest.mark.parametrize("call", [
        {}, {"id": None}, {"id": ""}, {"id": 42},
        {"id": "incomplete"}, {"id": "incomplete", "function": None},
        {"id": "incomplete", "function": {}},
        {"id": "incomplete", "function": {"name": None}},
        {"id": "incomplete", "function": {"name": 42}},
    ])
    @pytest.mark.parametrize("guidance", ["legacy", "recovery"])
    def test_incomplete_call_cannot_stub_or_route_a_large_result(self, call, guidance):
        messages = [
            {"role": "assistant", "tool_calls": [call]},
            {"role": "tool", "tool_call_id": call.get("id"), "content": _BIG},
            *_read_turn("latest", "done"),
        ]
        comp = _v01(large_result_stub=True, large_result_min_tokens=1, large_result_exempt_edited_files=True, large_result_stub_guidance=guidance)
        comp._backend = backend = FakeBackend()
        result = comp.compress(CompressionContext(messages=messages))
        assert result.messages == messages
        assert result.messages[1] is messages[1]
        assert result.metrics.error is None
        assert result.metrics.skip_reason == "all_passthrough"
        assert result.metrics.details["large_result_stubs"] == 0
        assert backend.calls == []
        assert comp._build_tool_name_by_id(messages) == {"latest": "read"}
        expected_ids = {"latest"}
        if call.get("id") == "incomplete":
            expected_ids.add("incomplete")
        assert comp._collect_assistant_tool_call_ids(messages) == expected_ids
        calls = comp._build_tool_call_by_id(messages)
        assert set(calls) == expected_ids
        if "incomplete" in expected_ids:
            assert calls["incomplete"] is call


class TestV01LargeResultStub:
    def test_on_by_default(self):
        msgs = _stub_session(7)
        r = _v01(protect_recent_tool_turns=1, large_result_min_tokens=100).compress(
            CompressionContext(messages=msgs))
        assert _stubbed(r.messages) == ["r0"]
        assert r.metrics.details["large_result_stub"] is True
        assert r.metrics.details["large_result_stub_guidance"] == "recovery"
        assert r.messages[-1] is msgs[-1]

    def test_default_keep_window(self):
        comp = _v01(large_result_stub=True, large_result_min_tokens=100)
        assert _stubbed(comp.compress(
            CompressionContext(messages=_stub_session(6))).messages) == []
        assert _stubbed(comp.compress(
            CompressionContext(messages=_stub_session(7))).messages) == ["r0"]

    def test_explicitly_disabled(self):
        msgs = _stub_session(3)
        r = _v01(
            protect_recent_tool_turns=1, large_result_stub=False,
        ).compress(CompressionContext(messages=msgs))
        assert _stubbed(r.messages) == []
        assert r.metrics.details["large_result_stub"] is False

    def test_latest_turn_never_stubbed(self):
        # keep=1: a result is stubbed only once a later tool turn exists.
        comp = _v01(protect_recent_tool_turns=1, large_result_stub=True, large_result_min_tokens=100, large_result_keep_tool_turns=1)
        assert _stubbed(comp.compress(CompressionContext(messages=_stub_session(1))).messages) == []
        out = comp.compress(CompressionContext(messages=_stub_session(3))).messages
        assert _stubbed(out) == ["r0", "r1"]

    def test_keep_two(self):
        comp = _v01(protect_recent_tool_turns=1, large_result_stub=True, large_result_min_tokens=100, large_result_keep_tool_turns=2)
        assert _stubbed(comp.compress(CompressionContext(messages=_stub_session(3))).messages) == ["r0"]

    def test_below_min_tokens_kept(self):
        comp = _v01(protect_recent_tool_turns=1, large_result_stub=True, large_result_min_tokens=100_000)
        assert _stubbed(comp.compress(CompressionContext(messages=_stub_session(3))).messages) == []

    def test_master_switch_disables_stub(self):
        comp = _v01(protect_recent_tool_turns=1, tool_results=False, large_result_stub=True, large_result_min_tokens=100)
        msgs = _stub_session(3)
        result = comp.compress(CompressionContext(messages=msgs))
        assert _stubbed(result.messages) == []
        assert all(a is b for a, b in zip(msgs, result.messages))

    def test_precedes_window(self):
        # Selected by position, not by the window frontier: with K=2 the
        # turn before the latest is inside the window but still stubbed.
        comp = _v01(protect_recent_tool_turns=2, large_result_stub=True, large_result_min_tokens=100, large_result_keep_tool_turns=1)
        assert _stubbed(comp.compress(CompressionContext(messages=_stub_session(3))).messages) == ["r0", "r1"]

    def test_write_result_never_stubbed(self):
        msgs = [{"role": "user", "content": "task"}] + _tool_result("w0", "write", _BIG) + _read_turn("r1")
        comp = _v01(protect_recent_tool_turns=1, large_result_stub=True, large_result_min_tokens=100)
        assert _stubbed(comp.compress(CompressionContext(messages=msgs)).messages) == []

    def test_pairing_and_positions_kept(self):
        msgs = _stub_session(3)
        comp = _v01(assistant_arguments=False, protect_recent_tool_turns=1, large_result_stub=True, large_result_min_tokens=100, large_result_keep_tool_turns=1)
        out = comp.compress(CompressionContext(messages=msgs)).messages
        assert len(out) == len(msgs)
        for a, b in zip(msgs, out):
            assert {k: v for k, v in a.items() if k != "content"} == \
                {k: v for k, v in b.items() if k != "content"}

    def test_details_and_tokens(self):
        comp = _v01(protect_recent_tool_turns=1, large_result_stub=True, large_result_min_tokens=100, large_result_keep_tool_turns=1)
        r = comp.compress(CompressionContext(messages=_stub_session(3)))
        d = r.metrics.details
        assert d["large_result_stubs"] == 2
        assert d["large_result_tokens_saved"] > 0
        assert r.metrics.skip_reason is None
        assert r.metrics.tokens_after < r.metrics.tokens_before

    def test_unsupported_shape_counted(self):
        msgs = _stub_session(2)
        msgs[2] = {**msgs[2], "content": [{"type": "text", "text": _BIG}, {"type": "text", "text": "x"}]}
        comp = _v01(protect_recent_tool_turns=1, large_result_stub=True, large_result_min_tokens=100, large_result_keep_tool_turns=1)
        r = comp.compress(CompressionContext(messages=msgs))
        assert r.messages[2] is msgs[2]
        assert r.metrics.details["large_result_skipped_shape"] == 1

    def test_monotonic_growing_session(self):
        full = _stub_session(6)
        comp = _with_cache(_v01(protect_recent_tool_turns=1, large_result_stub=True, large_result_min_tokens=100, large_result_keep_tool_turns=1))
        first_seen: dict[int, dict] = {}
        for m in range(2, len(full) + 1):
            out = comp.compress(CompressionContext(messages=full[:m])).messages
            for i, msg in enumerate(out):
                if msg is not full[i]:
                    if i in first_seen:
                        assert msg == first_seen[i]
                    first_seen[i] = msg
                else:
                    assert i not in first_seen, f"message {i} was un-stubbed"

    def test_cache_reused(self):
        comp = _with_cache(_v01(protect_recent_tool_turns=1, large_result_stub=True, large_result_min_tokens=100, large_result_keep_tool_turns=1))
        comp.compress(CompressionContext(messages=_stub_session(3)))
        d = comp.compress(CompressionContext(messages=_stub_session(3))).metrics.details
        assert d["cache_hits"] >= 2

    def test_edited_file_exempt(self):
        # r0 reads /tmp/r0.txt, which is edited later; r1's file never is.
        msgs = _stub_session(3) + _tool_result("e0", "edit", "ok")
        msgs[-2]["tool_calls"][0]["function"]["arguments"] = json.dumps(
            {"file_path": "/tmp/./r0.txt", "oldText": "a", "newText": "b"})
        comp = _v01(protect_recent_tool_turns=1, large_result_stub=True, large_result_min_tokens=100, large_result_keep_tool_turns=1, large_result_exempt_edited_files=True)
        r = comp.compress(CompressionContext(messages=msgs))
        assert _stubbed(r.messages) == ["r1", "r2"]
        assert r.metrics.details["large_result_exempt_edited_files"] is True
        # Off by default: the same history stubs r0 too.
        off = _v01(protect_recent_tool_turns=1, large_result_stub=True, large_result_min_tokens=100, large_result_keep_tool_turns=1)
        assert _stubbed(off.compress(CompressionContext(messages=msgs)).messages) == ["r0", "r1", "r2"]

    @pytest.mark.parametrize("arguments", [
        "{broken", "[]", None, {}, {"path": "", "file_path": None, "file": 42},
    ])
    @pytest.mark.parametrize("invalid_tool", ["read", "edit"])
    @pytest.mark.parametrize("guidance", ["legacy", "recovery"])
    def test_invalid_file_arguments_do_not_exempt_reads(self, arguments, invalid_tool, guidance):
        messages = _read_turn("read") + _tool_result("edit", "edit", "ok") + _read_turn("latest")
        messages[2]["tool_calls"][0]["function"]["arguments"] = {"path": "/tmp/read.txt"}
        invalid_index = 0 if invalid_tool == "read" else 2
        messages[invalid_index]["tool_calls"][0]["function"]["arguments"] = arguments
        comp = _v01(large_result_stub=True, large_result_min_tokens=100, large_result_keep_tool_turns=1, large_result_exempt_edited_files=True, large_result_stub_guidance=guidance)
        result = comp.compress(CompressionContext(messages=messages))
        assert _stubbed(result.messages) == ["read"]
        assert result.messages[3] is messages[3]
        assert result.messages[5] is messages[5]
        assert result.metrics.details["large_result_stubs"] == 1
        assert result.metrics.error is None

    @pytest.mark.parametrize("guidance", ["legacy", "recovery"])
    def test_edit_restores_earlier_stub(self, guidance):
        comp = _v01(protect_recent_tool_turns=1, large_result_stub=True, large_result_min_tokens=100, large_result_keep_tool_turns=1, large_result_exempt_edited_files=True, large_result_stub_guidance=guidance)
        before = _stub_session(3)
        assert _stubbed(comp.compress(CompressionContext(messages=before)).messages) == ["r0", "r1"]
        after = before + _tool_result("e0", "write", "ok")
        after[-2]["tool_calls"][0]["function"]["arguments"] = json.dumps({"path": "/tmp/r0.txt"})
        out = comp.compress(CompressionContext(messages=after)).messages
        assert _stubbed(out) == ["r1", "r2"]
        assert out[2] is after[2]

    def test_bad_params_raise(self):
        with pytest.raises(ConfigError):
            ContextCompressor(large_result_min_tokens=0, compression_mode='none')
        with pytest.raises(ConfigError):
            ContextCompressor(large_result_keep_tool_turns=0, compression_mode='none')


class TestRecoveryGuidance:
    def test_default_and_explicit_recovery_output(self):
        ctx = CompressionContext(messages=_stub_session(3))
        default = _v01(large_result_stub=True, large_result_min_tokens=100, large_result_keep_tool_turns=1).compress(ctx)
        recovery = _v01(large_result_stub=True, large_result_min_tokens=100, large_result_keep_tool_turns=1, large_result_stub_guidance="recovery").compress(ctx)
        assert default.messages == recovery.messages
        assert default.metrics.details == recovery.metrics.details
        assert default.metrics.details["large_result_stub_guidance"] == "recovery"
        assert "target:" in default.messages[2]["content"]

    @pytest.mark.parametrize("action", ["write", "edit"])
    @pytest.mark.parametrize("settings,expected", [
        ({"large_result_keep_tool_turns": 1}, ["r0", "r1"]),
        ({"large_result_stub": False}, []),
        ({"large_result_keep_tool_turns": 2}, ["r0", "r1"]),
        ({"large_result_keep_tool_turns": 3}, ["r0"]),
        ({"large_result_keep_tool_turns": 4}, []),
        ({"large_result_min_tokens": 100_000}, []),
        ({"protect_recent_tool_turns": 99, "compress_stride_tool_turns": 3}, ["r0", "r1"]),
        ({"tool_results": False}, []),
        ({"excluded_tools": ["read"]}, []),
        ({"excluded_tools": ["Read"]}, ["r0", "r1"]),
        ({"large_result_exempt_edited_files": True}, ["r1"]),
    ])
    def test_selection_and_passthrough_match_legacy(self, action, settings, expected):
        messages = _stub_session(4)
        messages[5]["tool_calls"][0]["function"] = {
            "name": action,
            "arguments": '{"file_path":"/tmp/./r0.txt","oldText":"a","newText":"b"}',
        }
        options = {
            "large_result_stub": True, "large_result_min_tokens": 100,
            "assistant_arguments": False, "large_result_keep_tool_turns": 1, **settings,
        }
        ctx = CompressionContext(messages=messages)
        legacy = _v01(**options, large_result_stub_guidance="legacy").compress(ctx)
        recovery = _v01(**options, large_result_stub_guidance="recovery").compress(ctx)
        assert _stubbed(legacy.messages) == _stubbed(recovery.messages) == expected
        for before, old, new in zip(messages, legacy.messages, recovery.messages):
            if before.get("tool_call_id") in expected:
                assert "target:" in new["content"]
                assert "This content is NOT in your context." in new["content"]
                assert {k: v for k, v in old.items() if k != "content"} == \
                    {k: v for k, v in new.items() if k != "content"}
            else:
                assert old == new == before

    def test_ordinary_rules_unchanged(self):
        messages = (
            _tool_result("error", "exec", '{"status":"error","tool":"exec","error":"failed"}')
            + _tool_result("status", "exec", "(no output)")
            + _read_turn("latest")
        )
        ctx = CompressionContext(messages=messages)
        legacy = _v01(protect_recent_tool_turns=2, large_result_stub_guidance="legacy").compress(ctx)
        recovery = _v01(protect_recent_tool_turns=2, large_result_stub_guidance="recovery").compress(ctx)
        assert legacy.messages == recovery.messages
        assert legacy.metrics.details["error_tokens_saved"] > 0
        assert legacy.metrics.details["error_tokens_saved"] == \
            recovery.metrics.details["error_tokens_saved"]
        assert _stubbed(recovery.messages) == []

    def test_shared_cache_isolates_modes_and_targets(self):
        cache = cachetools.LRUCache(maxsize=256)
        lock = threading.Lock()
        legacy = _v01(large_result_stub=True, large_result_min_tokens=100, large_result_keep_tool_turns=1, large_result_stub_guidance="legacy")
        recovery = _v01(large_result_stub=True, large_result_min_tokens=100, large_result_keep_tool_turns=1, large_result_stub_guidance="recovery")
        for comp in (legacy, recovery):
            comp.set_cache(cache, lock)
        messages = _stub_session(2)
        ctx = CompressionContext(messages=messages)
        old = legacy.compress(ctx)
        assert old.metrics.details["cache_misses"] == 1
        for arguments, target in [
            ({"path": "/tmp/a.py"}, "read /tmp/a.py"),
            ({"path": "/tmp/b.py"}, "read /tmp/b.py"),
            ({"path": "/tmp/b.py", "offset": 10}, "read /tmp/b.py offset=10"),
            ({"path": "/tmp/b.py", "offset": 10, "limit": 20}, "read /tmp/b.py offset=10 limit=20"),
            ({"path": "/tmp/b.py", "offset": 10, "limit": 21}, "read /tmp/b.py offset=10 limit=21"),
        ]:
            messages[1]["tool_calls"][0]["function"]["arguments"] = arguments
            result = recovery.compress(ctx)
            assert result.metrics.details["cache_misses"] == 1
            assert result.metrics.details["cache_hits"] == 0
            assert result.messages[2]["content"].splitlines()[2] == f"target: {target}"
            again = recovery.compress(ctx)
            assert again.messages == result.messages
            assert again.metrics.details["cache_hits"] == 1
        messages[1]["tool_calls"][0]["function"]["arguments"] = {"path": "/tmp/r0.txt"}
        cached_legacy = legacy.compress(ctx)
        assert cached_legacy.messages == old.messages
        assert cached_legacy.metrics.details["cache_hits"] == 1
        assert len(cache) == 6

    def test_cache_ignores_call_id_and_dict_key_order(self):
        comp = _with_cache(_v01(large_result_stub=True, large_result_min_tokens=100, large_result_keep_tool_turns=1, large_result_stub_guidance="recovery"))
        messages = _stub_session(2)
        function = messages[1]["tool_calls"][0]["function"]
        function["arguments"] = {"path": "a.py", "offset": 1, "limit": 2}
        first = comp.compress(CompressionContext(messages=messages))
        function["arguments"] = {"limit": 2, "offset": 1, "path": "a.py"}
        messages[1]["tool_calls"][0]["id"] = messages[2]["tool_call_id"] = "new-id"
        second = comp.compress(CompressionContext(messages=messages))
        assert second.messages[2]["content"] == first.messages[2]["content"]
        assert second.metrics.details["cache_hits"] == 1
        assert second.metrics.details["cache_misses"] == 0

    @pytest.mark.parametrize("tool_name,arg_key", [
        ("exec", "command"), ("web_search", "query"), ("custom_tool", "input"),
    ])
    def test_cache_isolates_other_tool_arguments(self, tool_name, arg_key):
        from adaptive_token_compressor.context.result_stub import render_stub

        comp = _with_cache(_v01(large_result_stub=True, large_result_min_tokens=100, large_result_keep_tool_turns=1, large_result_stub_guidance="recovery"))
        messages = _stub_session(2)
        call = messages[1]["tool_calls"][0]
        call["function"]["name"] = tool_name
        for value in ("first query", "second query"):
            call["function"]["arguments"] = json.dumps({arg_key: value})
            result = comp.compress(CompressionContext(messages=messages))
            assert result.metrics.details["cache_misses"] == 1
            assert result.messages[2]["content"] == render_stub(
                tool_name, _BIG, tool_call=call, guidance="recovery",
            )

    @pytest.mark.parametrize("guidance", ["legacy", "recovery"])
    def test_keep_decision_cached(self, guidance):
        comp = _with_cache(_v01(large_result_stub=True, large_result_min_tokens=1, large_result_keep_tool_turns=1, large_result_stub_guidance=guidance))
        ctx = CompressionContext(messages=_read_turn("small", "x " * 40) + _read_turn("latest"))
        first = comp.compress(ctx)
        second = comp.compress(ctx)
        assert first.messages == second.messages == ctx.messages
        assert first.metrics.details["cache_misses"] == 1
        assert second.metrics.details["cache_hits"] == 1
        assert _stubbed(second.messages) == []

    def test_actual_savings_and_mode_observable(self, caplog):
        from adaptive_token_compressor.core.metrics import count_messages_tokens

        with caplog.at_level("INFO", logger="adaptive_token_compressor.context.compressor"):
            comp = _v01(large_result_stub=True, large_result_min_tokens=100, large_result_keep_tool_turns=1, large_result_stub_guidance="recovery")
        assert '"large_result_stub_guidance": "recovery"' in caplog.text
        assert comp.effective_config["large_result_stub_guidance"] == "recovery"
        ctx = CompressionContext(messages=_stub_session(2))
        result = comp.compress(ctx)
        assert result.metrics.details["large_result_stub_guidance"] == "recovery"
        assert result.metrics.details["large_result_tokens_saved"] == (
            count_messages_tokens([ctx.messages[2]]) -
            count_messages_tokens([result.messages[2]])
        )

    @pytest.mark.parametrize("invalid", ["", "Recovery", "invalid", None, True, 1, [], {}])
    def test_invalid_guidance_rejected_even_when_stubs_disabled(self, invalid):
        with pytest.raises(ConfigError, match="guidance"):
            ContextCompressor(large_result_stub_guidance=invalid, compression_mode='none')


@pytest.fixture
def configured_claw(monkeypatch):
    adapter = FakeClawAdapter()
    monkeypatch.setitem(
        sys.modules, "adaptive_token_compressor.context.claw_adapter",
        SimpleNamespace(ContextClawAdapter=lambda **kwargs: adapter),
    )
    return adapter


class TestCapabilityGroups:
    @pytest.mark.parametrize("mode", ["none", "backend_only", "claw_only", "claw_with_backend"])
    def test_master_switch_precedes_all_result_processing(self, mode, configured_claw, tavily_content):
        comp = _standalone(assistant_arguments=True, tool_results=False, excluded_tools=["read"], large_result_stub=True, large_result_min_tokens=1, compression_mode=mode)
        comp._backend = backend = FakeBackend()
        messages = (
            _session(2) + _read_turn("read")
            + _tool_result("error", "exec", '{"status":"error","tool":"exec","error":"failed"}')
            + [{"role": "tool", "tool_call_id": "orphan", "content": "(no output)"}]
            + _tool_result("search", "web_search", tavily_content)
        )
        result = comp.compress(CompressionContext(messages=messages))
        for before, after in zip(messages, result.messages):
            if before.get("role") == "tool":
                assert after is before
        assert result.metrics.details["assistant_args_tokens_saved"] > 0
        assert all(result.metrics.details[key] == 0 for key in _SAVED_FIELDS[:-1])
        assert result.metrics.details["large_result_stubs"] == 0
        assert result.metrics.details["excluded_tool_results"] == 0
        assert backend.calls == []
        assert configured_claw.detect_calls == configured_claw.compress_calls == 0
        assert result.metrics.details["effective_config"] == comp.effective_config

    @pytest.mark.parametrize("group_enabled", [False, True])
    @pytest.mark.parametrize("rule_enabled", [False, True])
    @pytest.mark.parametrize("rule", ["status", "error", "web_search_strip"])
    def test_individual_rules(self, group_enabled, rule_enabled, rule, tavily_content):
        content = {
            "status": "(no output)",
            "error": '{"status":"error","tool":"exec","error":"failed"}',
            "web_search_strip": tavily_content,
        }[rule]
        message = {"role": "tool", "tool_call_id": "orphan", "content": content}
        comp = _standalone(
            rules_enabled=group_enabled, compression_mode="none",
            **{f"rules_{rule}": rule_enabled},
        )
        comp._backend = backend = FakeBackend()
        result = comp.compress(CompressionContext(messages=[message]))
        if group_enabled and rule_enabled:
            assert result.messages != [message]
            assert result.metrics.saved_tokens > 0
        else:
            assert result.messages == [message]
            assert result.messages[0] is message
        assert backend.calls == []

    @pytest.mark.parametrize("disable_group", [False, True])
    @pytest.mark.parametrize("stub_enabled", [False, True])
    def test_disabled_rules_do_not_disable_compression(
        self, disable_group, stub_enabled, tavily_content,
    ):
        rules = {"rules_enabled": False} if disable_group else {"rules_web_search_strip": False}
        comp = _standalone(
            large_result_stub=stub_enabled,
            large_result_keep_tool_turns=1,
            large_result_min_tokens=1,
            **rules,
        )
        comp._backend = backend = FakeBackend()
        messages = (
            _tool_result("search", "web_search", tavily_content)
            + _tool_result("other", "custom", _long_zh())
        )
        result = comp.compress(CompressionContext(messages=messages))
        expected_inputs = [_long_zh()] if stub_enabled else [tavily_content, _long_zh()]
        assert [call[0] for call in backend.calls] == expected_inputs
        assert _stubbed(result.messages) == (["search"] if stub_enabled else [])
        assert result.metrics.details["large_result_stubs"] == (1 if stub_enabled else 0)
        assert result.metrics.details["web_search_strip_tokens_saved"] == 0
        assert (result.metrics.details["web_search_compress_tokens_saved"] > 0) == (
            not stub_enabled
        )
        assert result.metrics.details["other_compress_tokens_saved"] > 0

    @pytest.mark.parametrize("rules", [
        {"rules_enabled": False}, {"rules_status": False, "rules_error": False},
    ])
    def test_disabled_status_and_error_do_not_fall_through_to_backend(self, rules):
        comp = _standalone(compress_min_chars=0, **rules)
        comp._backend = backend = FakeBackend()
        messages = [
            {"role": "tool", "tool_call_id": "status", "content": "(no output)"},
            {"role": "tool", "tool_call_id": "error",
             "content": '{"status":"error","tool":"exec","error":"failed"}'},
        ]
        result = comp.compress(CompressionContext(messages=messages))
        assert all(before is after for before, after in zip(messages, result.messages))
        assert backend.calls == []

    @pytest.mark.parametrize("group_enabled,error_enabled", [(False, True), (True, False), (True, True)])
    def test_error_rule_inside_window(self, group_enabled, error_enabled):
        messages = _tool_result("error", "exec", '{"status":"error","tool":"exec","error":"failed"}')
        comp = _v01(rules_enabled=group_enabled, rules_error=error_enabled)
        result = comp.compress(CompressionContext(messages=messages))
        if group_enabled and error_enabled:
            assert result.messages[1]["content"] == "exec failed: failed"
        else:
            assert result.messages[1] is messages[1]

    @pytest.mark.parametrize("mode", ["none", "backend_only", "claw_only", "claw_with_backend"])
    @pytest.mark.parametrize("content_type", ["code", "text"])
    def test_mode_routing(self, mode, content_type, configured_claw):
        configured_claw._ct = content_type
        comp = _standalone(compression_mode=mode)
        comp._backend = backend = FakeBackend()
        message = {"role": "tool", "tool_call_id": "other", "content": _long_zh()}
        result = comp.compress(CompressionContext(messages=[message]))
        uses_claw = mode in ("claw_only", "claw_with_backend")
        claw_compresses = uses_claw and content_type == "code"
        backend_compresses = mode == "backend_only" or (mode == "claw_with_backend" and not claw_compresses)
        assert configured_claw.detect_calls == int(uses_claw)
        assert configured_claw.compress_calls == int(claw_compresses)
        assert len(backend.calls) == int(backend_compresses)
        if not (claw_compresses or backend_compresses):
            assert result.messages[0] is message

    @pytest.mark.parametrize("stage", ["detect", "compress"])
    def test_claw_only_failure_is_visible_without_backend_fallback(
        self, stage, configured_claw, monkeypatch, caplog,
    ):
        if stage == "detect":
            monkeypatch.setattr(configured_claw, "detect", Mock(side_effect=RuntimeError("boom")))
        else:
            configured_claw._raise = True
        comp = _with_cache(_standalone(compression_mode="claw_only"))
        comp._backend = backend = FakeBackend()
        message = {"role": "tool", "tool_call_id": "other", "content": _long_zh()}
        for _ in range(2):
            result = comp.compress(CompressionContext(messages=[message]))
            assert result.messages[0] is message
            assert result.metrics.error
            assert result.metrics.details["claw_errors"]
            assert result.metrics.skip_reason is None
            assert result.metrics.details["cache_hits"] == result.metrics.details["cache_misses"] == 0
        assert "failed" in caplog.text
        assert backend.calls == []

    @pytest.mark.parametrize("mode", ["none", "backend_only", "claw_only", "claw_with_backend"])
    @pytest.mark.parametrize("enabled", [False, True])
    def test_health_checks_only_used_backends(self, mode, enabled, configured_claw):
        comp = _v01(tool_results=enabled, compression_mode=mode)
        comp._backend = backend = Mock()
        status = HealthStatus.healthy("fake")
        backend.health_check.return_value = status
        result = comp.health_check(timeout=2.0)
        if enabled and mode in ("backend_only", "claw_with_backend"):
            backend.health_check.assert_called_once_with(timeout=2.0)
            assert result is status
        else:
            backend.health_check.assert_not_called()
            assert result.details["backend"] == "unused"
