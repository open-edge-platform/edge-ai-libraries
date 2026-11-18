# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""ContextCompressor: rule + compress-server hybrid compression for user/assistant/tool
messages.

Three-layer dispatch by role: user → passthrough; assistant → tool_call args
summarization; tool → classify into STATUS / ERROR / WEB_SEARCH / OTHER and
apply the matching rule or backend call.

`excluded_tools` takes precedence over every tool-result transform below;
excluded results stay verbatim, but assistant arguments are independent.

Window gate (v0_1, design v8 §14.1): the most recent
`protect_recent_tool_turns` tool turns (assistant tool_calls + their results)
never enter any lossy branch. The gate boundary only advances every
`compress_stride_tool_turns` turns, so already-sent turns are rewritten in
batches (each rewrite of a cached turn breaks the vLLM prefix cache from
there on). The one exception is the lossless ERROR simplification, applied
on first sight inside the window too: delaying it until the turn leaves the
window would break the cache for a ~10-token gain.

Historical large-result stub (opt-in): a tool result of
>= `large_result_min_tokens` whose turn is followed by >=
`large_result_keep_tool_turns` later tool turns is replaced in place by a
fixed-format stub (see result_stub.py). It is selected by position only,
independent of the window frontier, and takes precedence
over every other non-excluded tool-result rule. Rewriting a cached turn is worth it here:
the stubbed turn shrinks to ~100 tokens, so re-prefilling it once is cheap.
With `large_result_exempt_edited_files`, `read` results of a file that the
history writes/edits are never stubbed (stubbed copies are restored once).

The tool-result policy's master switch precedes every result transform.
Backend failures surface in metrics.error. Claw failures fall back only when
the selected mode permits backend calls.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from typing import Any

import cachetools

from ..core.backends import BackendError, CompressionBackend, TokenPruneBackend
from ..core.base import CompressionContext, CompressorResult
from ..core.cache import cache_get, cache_set
from ..core.exceptions import ConfigError
from ..core.health import HealthStatus
from ..core.metrics import CompressionScope, CompressorMetrics, count_messages_tokens
from .assistant_handler import (
    ARG_PREVIEW_MARKER,
    build_completed_tool_call_ids,
    compress_assistant_message,
)
from .config import (
    CompressBackendConfig,
    CompressionMode,
    ContentCompressionConfig,
    ContextWindowConfig,
    LargeResultStubConfig,
    ResultRulesConfig,
    ToolResultPolicy,
)
from .result_stub import (
    StubGuidance,
    content_text,
    edited_file_read_ids,
    make_stub,
    stub_eligible_call_ids,
    validate_stub_guidance,
    with_text,
)
from .tool_handler import ToolContentCategory, classify, simplify_error, web_search_strip

logger = logging.getLogger("adaptive_token_compressor.context.compressor")

# Roles counted for tokens_before / tokens_after (system/developer belong to
# HarnessCompressor, never to context).
_CONTEXT_ROLES = ("user", "assistant", "tool")

# STATUS stub content kept when the message must stay to preserve pairing.
_ELIDED_STATUS = "(elided status)"

# WEB_SEARCH compress params (static per message-type; plan §6.6 point 2).
_WEB_SEARCH_RATE = 0.6
_WEB_SEARCH_DIGIT_RADIUS = 3

# OpenClaw: "Command still running (session delta-shoal, pid 2812401). Use
# process (...) for follow-up." The session name is the handle for later
# process poll/log/kill calls, so the message is only elided once a later
# tool_call references that session.
_RUNNING_SESSION_RE = re.compile(r"^Command still running \(session ([^,\s)]+)")


class ContextCompressor:
    """Flat configuration with internally grouped rules, stubs and compression."""

    name: str = "context"

    def __init__(
        self,
        *,
        assistant_arguments: bool = False,
        protect_recent_tool_turns: int = 1,
        compress_stride_tool_turns: int = 1,
        tool_results: bool = True,
        excluded_tools: list[str] | tuple[str, ...] = (),
        rules_enabled: bool = True,
        rules_status: bool = True,
        rules_error: bool = True,
        rules_web_search_strip: bool = True,
        large_result_stub: bool = True,
        large_result_stub_guidance: StubGuidance = "recovery",
        large_result_min_tokens: int = 4000,
        large_result_keep_tool_turns: int = 6,
        large_result_exempt_edited_files: bool = False,
        compression_mode: CompressionMode = "none",
        compress_min_chars: int = 200,
        compress_server_url: str = "http://localhost:8001/compress",
        compress_rate: float = 0.6,
        timeout: float = 30.0,
    ) -> None:
        if not (0.0 < compress_rate <= 1.0):
            raise ConfigError(
                f"ContextCompressor: compress_rate must be in (0, 1], got {compress_rate}"
            )
        if timeout <= 0:
            raise ConfigError(
                f"ContextCompressor: timeout must be > 0, got {timeout}"
            )
        if compress_min_chars < 0:
            raise ConfigError(
                f"ContextCompressor: compress_min_chars must be >= 0, got {compress_min_chars}"
            )
        if protect_recent_tool_turns < 0:
            raise ConfigError(
                "ContextCompressor: protect_recent_tool_turns must be >= 0, "
                f"got {protect_recent_tool_turns}"
            )
        if compress_stride_tool_turns < 1:
            raise ConfigError(
                "ContextCompressor: compress_stride_tool_turns must be >= 1, "
                f"got {compress_stride_tool_turns}"
            )
        if large_result_min_tokens < 1:
            raise ConfigError(
                "ContextCompressor: large_result_min_tokens must be >= 1, "
                f"got {large_result_min_tokens}"
            )
        if large_result_keep_tool_turns < 1:
            raise ConfigError(
                "ContextCompressor: large_result_keep_tool_turns must be >= 1 "
                "(the latest turn's result is never stubbed), "
                f"got {large_result_keep_tool_turns}"
            )
        validate_stub_guidance(large_result_stub_guidance)
        if compression_mode not in ("none", "backend_only", "claw_only", "claw_with_backend"):
            raise ConfigError(
                "ContextCompressor: compression_mode must be one of "
                "['none', 'backend_only', 'claw_only', 'claw_with_backend'], "
                f"got {compression_mode!r}"
            )
        if not isinstance(excluded_tools, (list, tuple)) or any(
            not isinstance(name, str) or not name.strip() or name != name.strip()
            for name in excluded_tools
        ):
            raise ConfigError(
                "ContextCompressor: excluded_tools must be a list or tuple of non-empty "
                "tool names without surrounding whitespace"
            )
        self._window = ContextWindowConfig(
            protect_recent_tool_turns=protect_recent_tool_turns,
            compress_stride_tool_turns=compress_stride_tool_turns,
        )
        self._policy = ToolResultPolicy(
            enabled=tool_results,
            excluded_tools=tuple(excluded_tools),
            rules=ResultRulesConfig(
                enabled=rules_enabled, status=rules_status,
                error=rules_error, web_search_strip=rules_web_search_strip,
            ),
            large_result_stub=LargeResultStubConfig(
                enabled=large_result_stub, guidance=large_result_stub_guidance,
                min_tokens=large_result_min_tokens,
                keep_tool_turns=large_result_keep_tool_turns,
                exempt_edited_files=large_result_exempt_edited_files,
            ),
            compression=ContentCompressionConfig(
                mode=compression_mode, min_chars=compress_min_chars,
                compress_backend=CompressBackendConfig(
                    url=compress_server_url, rate=compress_rate, timeout=timeout,
                ),
            ),
        )
        self._rules = self._policy.rules
        compression = self._policy.compression
        backend = compression.compress_backend
        stub = self._policy.large_result_stub
        self._backend: CompressionBackend = TokenPruneBackend(
            compress_server_url=backend.url, timeout=backend.timeout,
        )
        self._compress_rate = backend.rate
        self._compress_min_chars = compression.min_chars
        self._assistant_arguments = assistant_arguments
        self._excluded_tools = frozenset(self._policy.excluded_tools)
        self._compression_mode = compression.mode
        self._backend_enabled = self._policy.enabled and compression.mode in (
            "backend_only", "claw_with_backend",
        )
        self._protect_recent_tool_turns = self._window.protect_recent_tool_turns
        self._compress_stride_tool_turns = self._window.compress_stride_tool_turns
        self._large_result_stub = stub.enabled
        self._large_result_min_tokens = stub.min_tokens
        self._large_result_keep_tool_turns = stub.keep_tool_turns
        self._large_result_exempt_edited_files = stub.exempt_edited_files
        self._large_result_stub_guidance: StubGuidance = stub.guidance
        self._compress_mode = "llmlingua2"
        logger.info(
            "ContextCompressor init: effective_config=%s",
            json.dumps(self.effective_config, ensure_ascii=False, sort_keys=True),
        )

        self._claw_adapter = None
        if self._policy.enabled and compression.mode in ("claw_only", "claw_with_backend"):
            try:
                from .claw_adapter import ContextClawAdapter
            except ImportError as e:
                raise ConfigError(
                    f"ContextCompressor: compression_mode={compression.mode!r} "
                    "requires the 'claw-compactor' package. Install "
                    "`claw-compactor>=7,<8` or select 'backend_only' / 'none'."
                ) from e
            # disable_dangerous is a hardcoded internal policy, not a kwarg.
            self._claw_adapter = ContextClawAdapter(disable_dangerous=True)

        # Cache injected by CompressionManager via set_cache(); None standalone.
        self._cache: cachetools.LRUCache | None = None
        self._cache_lock: threading.Lock | None = None

    @property
    def effective_config(self) -> dict:
        """Detached, JSON-compatible configuration with all defaults resolved."""
        stub = self._policy.large_result_stub
        compression = self._policy.compression
        backend = compression.compress_backend
        return {
            "assistant_arguments": self._assistant_arguments,
            "protect_recent_tool_turns": self._window.protect_recent_tool_turns,
            "compress_stride_tool_turns": self._window.compress_stride_tool_turns,
            "tool_results": self._policy.enabled,
            "excluded_tools": list(self._policy.excluded_tools),
            "rules_enabled": self._rules.enabled,
            "rules_status": self._rules.status,
            "rules_error": self._rules.error,
            "rules_web_search_strip": self._rules.web_search_strip,
            "large_result_stub": stub.enabled,
            "large_result_stub_guidance": stub.guidance,
            "large_result_min_tokens": stub.min_tokens,
            "large_result_keep_tool_turns": stub.keep_tool_turns,
            "large_result_exempt_edited_files": stub.exempt_edited_files,
            "compression_mode": compression.mode,
            "compress_min_chars": compression.min_chars,
            "compress_server_url": backend.url,
            "compress_rate": backend.rate,
            "timeout": backend.timeout,
        }

    def set_cache(
        self,
        cache: cachetools.LRUCache | None,
        lock: threading.Lock | None,
    ) -> None:
        """Inject the LRU cache + lock (called by CompressionManager). Passing
        `(None, None)` disables caching — the `_cached_*` wrappers then call
        the backend / pure functions directly.
        """
        self._cache = cache
        self._cache_lock = lock

    def _cached_backend(
        self,
        content: str,
        details: dict,
        *,
        rate: float,
        force_reserve_digit: bool = False,
        digit_neighbor_radius: int = 0,
    ) -> str:
        """Cache-aware wrapper around `self._backend.compress(...)`. Key is
        prefixed with `self._backend.cache_tag` to isolate backend identities.
        `details` (owned by compress()) tracks cache_hits / misses.
        BackendError propagates.
        """
        key, cached = cache_get(
            self._cache, self._cache_lock,
            self._backend.cache_tag,
            content,
            rate,
            force_reserve_digit,
            digit_neighbor_radius,
            self._compress_mode,
        )
        if cached is not None:
            details["cache_hits"] += 1
            return cached
        result = self._backend.compress(
            content, mode=self._compress_mode, rate=rate,
            force_reserve_digit=force_reserve_digit,
            digit_neighbor_radius=digit_neighbor_radius,
        )
        cache_set(self._cache, self._cache_lock, key, result)
        if key is not None:
            details["cache_misses"] += 1
        return result

    def _cached_claw(self, content: str, content_type: str, details: dict) -> str:
        """Cache-aware wrapper around `compress_with_claw`. Same cache
        semantics as `_cached_backend`. Cortex / FusionEngine exceptions
        propagate; the caller falls back to `_cached_backend`.
        """
        key, cached = cache_get(self._cache, self._cache_lock, "claw", content, content_type)
        if cached is not None:
            details["cache_hits"] += 1
            return cached
        adapter = self._claw_adapter
        assert adapter is not None
        result = adapter.compress_with_claw(content, content_type)
        cache_set(self._cache, self._cache_lock, key, result)
        if key is not None:
            details["cache_misses"] += 1
        return result

    def _cached_web_strip(self, content: str, details: dict) -> str:
        """Cache-aware wrapper around `web_search_strip`. Same cache semantics
        as `_cached_backend`. Pure — never raises.
        """
        key, cached = cache_get(self._cache, self._cache_lock, "web_strip", content)
        if cached is not None:
            details["cache_hits"] += 1
            return cached
        result = web_search_strip(content)
        cache_set(self._cache, self._cache_lock, key, result)
        if key is not None:
            details["cache_misses"] += 1
        return result

    def _cached_stub(
        self, tool_name: str | None, text: str, details: dict,
        *, tool_call: dict | None = None,
    ) -> str | None:
        """Cache-aware wrapper around `make_stub` (tokenizing a large result
        on every request is the expensive part). "" caches a keep decision."""
        # Call ids do not affect the target; legacy text ignores arguments.
        call_key = (
            json.dumps(
                (tool_call or {}).get("function") or {},
                ensure_ascii=False, separators=(",", ":"), sort_keys=True,
            )
            if self._large_result_stub_guidance == "recovery" else ""
        )
        key, cached = cache_get(
            self._cache, self._cache_lock, "result_stub",
            tool_name, self._large_result_min_tokens, text,
            self._large_result_stub_guidance, call_key,
        )
        if cached is not None:
            details["cache_hits"] += 1
            return cached or None
        stub = make_stub(
            tool_name, text, self._large_result_min_tokens,
            tool_call=tool_call, guidance=self._large_result_stub_guidance,
        )
        cache_set(self._cache, self._cache_lock, key, stub or "")
        if key is not None:
            details["cache_misses"] += 1
        return stub

    def compress(self, ctx: CompressionContext) -> CompressorResult:
        """Run the three-layer dispatch over `ctx.messages`; return a
        CompressorResult with a NEW messages list (handlers never mutate
        input). `tools` is forwarded unchanged.

        Never raises. skip_reason is "no_messages" or "all_passthrough" when
        nothing was compressed; backend failures fill metrics.error; claw
        fallbacks bump details["claw_fallback_count"] without erroring.
        """
        start = time.perf_counter()
        messages = ctx.messages or []
        tokens_before = count_messages_tokens(messages, roles=_CONTEXT_ROLES)

        # Per-call diagnostics (local, not self state → concurrency-safe).
        details: dict[str, Any] = {
            "status_tokens_saved": 0,
            "error_tokens_saved": 0,
            "web_search_strip_tokens_saved": 0,
            "web_search_compress_tokens_saved": 0,
            "other_compress_tokens_saved": 0,
            "other_claw_tokens_saved": 0,
            "assistant_args_tokens_saved": 0,
            "assistant_arguments": self._assistant_arguments,
            "tool_result_policy_enabled": self._policy.enabled,
            "excluded_tools": sorted(self._excluded_tools),
            "excluded_tool_results": 0,
            "compression_mode": self._compression_mode,
            "effective_config": self.effective_config,
            "protect_recent_tool_turns": self._protect_recent_tool_turns,
            "compress_stride_tool_turns": self._compress_stride_tool_turns,
            "large_result_stub": self._large_result_stub,
            "large_result_stub_guidance": self._large_result_stub_guidance,
            "large_result_exempt_edited_files": self._large_result_exempt_edited_files,
            "large_result_stubs": 0,
            "large_result_tokens_saved": 0,
            "large_result_skipped_shape": 0,
            "assistant_messages_passthrough": 0,
            "tool_result_messages_passthrough": 0,
            "protected_messages": 0,
            "arg_preview_leaks": 0,
            "cache_hits": 0,
            "cache_misses": 0,
        }

        if not messages:
            return self._result(messages, ctx.tools, tokens_before, tokens_before,
                                start, details, skip_reason="no_messages")

        # The history is the raw transcript, so a marker in any tool_call's
        # arguments was produced by the model itself. Cumulative over the
        # history: take the max per session when aggregating.
        details["arg_preview_leaks"] = self._count_arg_preview_leaks(messages)
        if details["arg_preview_leaks"]:
            logger.warning(
                "arg_preview marker found in %d raw tool_call argument(s)",
                details["arg_preview_leaks"],
            )

        completed_ids = (
            build_completed_tool_call_ids(messages)
            if self._assistant_arguments
            else set()
        )
        assistant_tc_ids = self._collect_assistant_tool_call_ids(messages)
        tool_name_by_id = self._build_tool_name_by_id(messages)
        tool_call_by_id = self._build_tool_call_by_id(messages)
        backend_errors: list[str] = []
        claw_errors: list[str] = []
        claw_fallback_count = 0
        touched = False
        protected_from = self._protected_from_index(
            messages, self._protect_recent_tool_turns, self._compress_stride_tool_turns
        )
        stub_ids = (
            stub_eligible_call_ids(messages, self._large_result_keep_tool_turns)
            if self._policy.enabled and self._large_result_stub
            else set()
        )
        if stub_ids and self._large_result_exempt_edited_files:
            stub_ids -= edited_file_read_ids(messages)

        new_messages: list[dict] = []
        for idx, msg in enumerate(messages):
            if msg.get("role") == "tool" and not self._policy.enabled:
                details["tool_result_messages_passthrough"] += 1
                new_messages.append(msg)
                continue
            tool_call_id = msg.get("tool_call_id")
            if (
                msg.get("role") == "tool"
                and isinstance(tool_call_id, str)
                and tool_name_by_id.get(tool_call_id, "") in self._excluded_tools
            ):
                details["excluded_tool_results"] += 1
                details["tool_result_messages_passthrough"] += 1
                new_messages.append(msg)
                continue
            # Large-result stub first: by position only, before the window
            # gate and every other tool-result rule.
            if msg.get("role") == "tool" and msg.get("tool_call_id") in stub_ids:
                stubbed = self._stub_large_result(
                    msg, tool_name_by_id, tool_call_by_id, details
                )
                if stubbed is not None:
                    touched = True
                    new_messages.append(stubbed)
                    continue

            if idx >= protected_from:
                details["protected_messages"] += 1
                # window gate → verbatim, except the lossless ERROR rewrite
                new_msg = (
                    self._simplify_error_msg(msg)
                    if self._rules.enabled and self._rules.error else msg
                )
                if new_msg is not msg:
                    details["error_tokens_saved"] += self._msg_tokens(msg) - self._msg_tokens(new_msg)
                    touched = True
                new_messages.append(new_msg)
                continue

            role = msg.get("role")

            if role == "assistant":
                if not self._assistant_arguments:
                    details["assistant_messages_passthrough"] += 1
                    new_messages.append(msg)
                    continue

                new_msg = compress_assistant_message(msg, completed_ids)[0]
                if new_msg is not msg:
                    touched = True
                    details["assistant_args_tokens_saved"] += (
                        self._msg_tokens(msg) - self._msg_tokens(new_msg)
                    )
                new_messages.append(new_msg)
                continue

            if role != "tool":
                new_messages.append(msg)          # user / other → passthrough
                continue

            # ── tool message: classify + dispatch ──
            content = msg.get("content")
            if not isinstance(content, str):
                new_messages.append(msg)
                continue

            cat = classify(content)
            before = self._msg_tokens(msg)

            if cat is ToolContentCategory.STATUS:
                if not (self._rules.enabled and self._rules.status):
                    new_messages.append(msg)
                    continue
                tc_id = msg.get("tool_call_id")
                if tc_id not in assistant_tc_ids:
                    details["status_tokens_saved"] += before   # orphan → dropped
                    touched = True
                    continue
                if self._running_status_followed_up(content, idx, messages):
                    stub = {**msg, "content": _ELIDED_STATUS}
                    details["status_tokens_saved"] += before - self._msg_tokens(stub)
                    touched = True
                    new_messages.append(stub)
                    continue
                # "(no output)" etc., or a running command never polled since:
                # keep verbatim (the stub saves nothing / would lose the session).
                new_messages.append(msg)
                continue

            if cat is ToolContentCategory.ERROR:
                new_msg = (
                    self._simplify_error_msg(msg)
                    if self._rules.enabled and self._rules.error else msg
                )
                if new_msg is not msg:
                    details["error_tokens_saved"] += before - self._msg_tokens(new_msg)
                    touched = True
                new_messages.append(new_msg)
                continue

            if cat is ToolContentCategory.WEB_SEARCH:
                new_msg, errored = self._compress_web_search(msg, content, before, details)
                if errored:
                    backend_errors.append(errored)
                if new_msg is not msg:
                    touched = True
                new_messages.append(new_msg)
                continue

            # OTHER
            if self._compression_mode == "none":
                new_messages.append(msg)
                continue

            if len(content) < self._compress_min_chars:
                new_messages.append(msg)          # short template → passthrough
                continue

            new_msg, err, fell_back = self._compress_other(msg, content, before, details)
            if err:
                if self._backend_enabled:
                    backend_errors.append(err)
                else:
                    claw_errors.append(err)
            if fell_back:
                claw_fallback_count += 1
            if new_msg is not msg:
                touched = True
            new_messages.append(new_msg)

        if claw_fallback_count:
            details["claw_fallback_count"] = claw_fallback_count
        if backend_errors:
            details["backend_errors"] = backend_errors
        if claw_errors:
            details["claw_errors"] = claw_errors

        # all_passthrough only when nothing happened; a backend failure counts
        # as an attempt so metrics.error is filled.
        if not touched and not backend_errors and not claw_errors:
            return self._result(messages, ctx.tools, tokens_before, tokens_before,
                                start, details, skip_reason="all_passthrough")

        tokens_after = count_messages_tokens(new_messages, roles=_CONTEXT_ROLES)
        errors = backend_errors + claw_errors
        error = "; ".join(errors) if errors else None
        return self._result(new_messages, ctx.tools, tokens_before, tokens_after,
                            start, details, error=error)

    # ── dispatch helpers ──────────────────────────────────────────────────

    def _stub_large_result(
        self, msg: dict, tool_name_by_id: dict[str, str],
        tool_call_by_id: dict[str, dict], details: dict,
    ) -> dict | None:
        """Stubbed copy of an eligible tool result, or None to fall through
        to the normal rules (too small, write/edit, unsupported shape)."""
        content = msg.get("content")
        text = content_text(content)
        if text is None:
            details["large_result_skipped_shape"] += 1
            return None
        tool_call_id = msg.get("tool_call_id")
        tool_name = tool_name_by_id.get(tool_call_id) if isinstance(tool_call_id, str) else None
        tool_call = tool_call_by_id.get(tool_call_id) if isinstance(tool_call_id, str) else None
        stub = self._cached_stub(
            tool_name, text, details, tool_call=tool_call,
        )
        if stub is None:
            return None
        new_msg = {**msg, "content": with_text(content, stub)}
        details["large_result_stubs"] += 1
        details["large_result_tokens_saved"] += self._msg_tokens(msg) - self._msg_tokens(new_msg)
        return new_msg

    def _compress_web_search(
        self,
        msg: dict,
        content: str,
        before: int,
        details: dict,
    ) -> tuple[dict, str | None]:
        """WEB_SEARCH: optional rule strip, then optional backend
        (digit-guarded). Returns (new_msg, error_or_None); new_msg is `msg`
        itself when the strip does not shrink it and no backend runs. Strip
        savings are always kept; a backend failure keeps the stripped content
        and records the error."""
        strip_enabled = self._rules.enabled and self._rules.web_search_strip
        stripped = self._cached_web_strip(content, details) if strip_enabled else content
        strip_msg = {**msg, "content": stripped} if strip_enabled else msg
        strip_saved = before - self._msg_tokens(strip_msg)
        if not self._backend_enabled:
            if strip_saved <= 0:
                return msg, None
            details["web_search_strip_tokens_saved"] += strip_saved
            return strip_msg, None
        details["web_search_strip_tokens_saved"] += strip_saved
        try:
            final = self._cached_backend(
                stripped, details, rate=_WEB_SEARCH_RATE,
                force_reserve_digit=True, digit_neighbor_radius=_WEB_SEARCH_DIGIT_RADIUS,
            )
        except BackendError as e:
            logger.warning("Backend failed for web_search message: %s", e)
            return strip_msg, str(e)
        final_msg = {**msg, "content": final}
        details["web_search_compress_tokens_saved"] += (
            self._msg_tokens(strip_msg) - self._msg_tokens(final_msg)
        )
        return final_msg, None

    def _compress_other(
        self,
        msg: dict,
        content: str,
        before: int,
        details: dict,
    ) -> tuple[dict, str | None, bool]:
        """OTHER routing; backend fallback is allowed only by the selected mode."""
        use_claw_type: str | None = None
        if self._claw_adapter is not None and self._compression_mode in ("claw_only", "claw_with_backend"):
            try:
                ct = self._claw_adapter.detect(content)
            except Exception as e:
                logger.warning("claw detection failed: %s", type(e).__name__)
                if not self._backend_enabled:
                    return msg, f"claw detection failed: {type(e).__name__}", False
                ct = "text"
            if ct in {"code", "diff", "log", "search"}:
                use_claw_type = ct

        if use_claw_type is not None:
            try:
                out = self._cached_claw(content, use_claw_type, details)
                new_msg = {**msg, "content": out}
                details["other_claw_tokens_saved"] += before - self._msg_tokens(new_msg)
                return new_msg, None, False
            except Exception as e:
                logger.warning("claw compression failed: %s", type(e).__name__)
                if not self._backend_enabled:
                    return msg, f"claw compression failed: {type(e).__name__}", False

        if not self._backend_enabled:
            return msg, None, False

        # main backend plain (routed here, or claw fallback)
        try:
            out = self._cached_backend(
                content,
                details,
                rate=self._compress_rate,
            )
        except BackendError as e:
            logger.warning("Backend failed for OTHER message: %s", e)
            return msg, str(e), use_claw_type is not None
        new_msg = {**msg, "content": out}
        details["other_compress_tokens_saved"] += before - self._msg_tokens(new_msg)
        return new_msg, None, use_claw_type is not None

    # ── small utilities ───────────────────────────────────────────────────

    @staticmethod
    def _protected_from_index(messages: list[dict], keep: int, stride: int) -> int:
        """Index of the first message inside the window gate.

        With T tool turns (assistant messages with tool_calls), turns
        [0, F) are compressible where F = ((T - keep) // stride) * stride
        (0 when T <= keep); everything from turn F's assistant message on is
        protected. F never decreases as the history grows, so a turn once
        compressed stays compressed identically. keep=0, stride=1 → nothing
        protected.
        """
        starts = [
            i for i, m in enumerate(messages)
            if m.get("role") == "assistant" and m.get("tool_calls")
        ]
        t = len(starts)
        frontier = ((t - keep) // stride) * stride if t > keep else 0
        return starts[frontier] if frontier < t else len(messages)

    @staticmethod
    def _simplify_error_msg(msg: dict) -> dict:
        """ERROR tool result → 'X failed: msg' (lossless, see simplify_error);
        anything else, or an error JSON with extra fields, returns `msg`."""
        content = msg.get("content")
        if msg.get("role") != "tool" or not isinstance(content, str):
            return msg
        if classify(content) is not ToolContentCategory.ERROR:
            return msg
        simplified = simplify_error(content)
        return msg if simplified == content else {**msg, "content": simplified}

    @staticmethod
    def _running_status_followed_up(content: str, idx: int, messages: list[dict]) -> bool:
        """True iff `content` is a "Command still running (session X, ...)"
        status and some tool_call after position `idx` mentions session X —
        the agent already followed up on it, so the status can be elided.
        """
        m = _RUNNING_SESSION_RE.match(content.strip())
        if m is None:
            return False
        session = m.group(1)
        for later in messages[idx + 1:]:
            if later.get("role") != "assistant":
                continue
            for tc in later.get("tool_calls") or []:
                args = (tc.get("function") or {}).get("arguments")
                if isinstance(args, str) and session in args:
                    return True
        return False

    @staticmethod
    def _count_arg_preview_leaks(messages: list[dict]) -> int:
        """Number of tool_calls whose raw arguments contain the arg_preview
        marker (the model copied a historical marker into a real call)."""
        leaks = 0
        for m in messages:
            if m.get("role") != "assistant":
                continue
            for tc in m.get("tool_calls") or []:
                args = (tc.get("function") or {}).get("arguments")
                if isinstance(args, str) and ARG_PREVIEW_MARKER in args:
                    leaks += 1
        return leaks

    @staticmethod
    def _collect_assistant_tool_call_ids(messages: list[dict]) -> set[str]:
        """Ids present in any assistant.tool_calls — a STATUS result whose id
        is here must stay (as a stub) so the call is not orphaned."""
        ids: set[str] = set()
        for m in messages:
            if m.get("role") != "assistant":
                continue
            for tc in m.get("tool_calls") or []:
                tc_id = tc.get("id")
                if isinstance(tc_id, str) and tc_id:
                    ids.add(tc_id)
        return ids

    @staticmethod
    def _build_tool_name_by_id(messages: list[dict]) -> dict[str, str]:
        """Map each tool_call_id → the tool name that produced it, so a
        tool-result message can be routed by its originating tool."""
        names: dict[str, str] = {}
        for m in messages:
            if m.get("role") != "assistant":
                continue
            for tc in m.get("tool_calls") or []:
                tc_id = tc.get("id")
                name = (tc.get("function") or {}).get("name")
                if isinstance(tc_id, str) and tc_id and isinstance(name, str):
                    names[tc_id] = name
        return names

    @staticmethod
    def _build_tool_call_by_id(messages: list[dict]) -> dict[str, dict]:
        """Map each tool_call_id to its original call for contextual stubs."""
        calls: dict[str, dict] = {}
        for message in messages:
            if message.get("role") != "assistant":
                continue
            for tool_call in message.get("tool_calls") or []:
                tool_call_id = tool_call.get("id")
                if isinstance(tool_call_id, str) and tool_call_id:
                    calls[tool_call_id] = tool_call
        return calls

    @staticmethod
    def _msg_tokens(msg: dict) -> int:
        return count_messages_tokens([msg], roles=_CONTEXT_ROLES)

    def _result(
        self, messages, tools, tokens_before, tokens_after, start, details,
        *, error: str | None = None, skip_reason: str | None = None,
    ) -> CompressorResult:
        metrics = CompressorMetrics(
            name=self.name,
            scope=CompressionScope.CONTEXT,
            tokens_before=tokens_before,
            tokens_after=tokens_after,
            duration_ms=(time.perf_counter() - start) * 1000,
            error=error,
            skip_reason=skip_reason,
            details=dict(details),
        )
        return CompressorResult(messages=messages, tools=tools, metrics=metrics)

    def health_check(self, *, timeout: float = 5.0) -> HealthStatus:
        """Forward to `self._backend.health_check`. claw_adapter is a local
        package with no reachability concept, so it is not pinged. With
        the selected mode does not use a backend, it is not pinged either."""
        if not self._backend_enabled:
            return HealthStatus.healthy(self.name, backend="unused")
        return self._backend.health_check(timeout=timeout)
