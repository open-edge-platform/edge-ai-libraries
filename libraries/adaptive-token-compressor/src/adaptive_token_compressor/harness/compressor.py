# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""HarnessCompressor: section-aware compression of system/developer messages.

Pipeline:  optional QuantumLock stabilize → sectioning → per-compress-section
(normalize → cached backend → restore) → join → sweep_residual.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass

import cachetools

from ..core.backends import CompressionBackend, build_backend
from ..core.base import CompressionContext, CompressorResult
from ..core.cache import cache_get, cache_set
from ..core.exceptions import BackendError, ConfigError
from ..core.health import HealthStatus
from ..core.messages import HARNESS_LIKE_ROLES, MessageAccessor
from ..core.metrics import CompressionScope, CompressorMetrics, count_messages_tokens
from .profiles import resolve_profile
from .sectioning import SectionSplitter

logger = logging.getLogger("adaptive_token_compressor.harness.compressor")


@dataclass
class SectionDetail:
    """Per-section diagnostics for `metrics.details["section_details"]`."""

    name: str
    compressed: bool
    original_tokens: int
    compressed_tokens: int
    saved_tokens: int
    cache_hit: bool = False
    backend_error: str | None = None


class HarnessCompressor:
    """Section-aware compression for system / developer messages.

    `compress()` never raises: BackendError is caught per section. ConfigError
    raises only at construction (unknown profile, missing claw-compactor).
    Cache is injected via `set_cache()` — standalone use skips caching.
    """

    name: str = "harness"

    def __init__(
        self,
        *,
        profile: str = "openclaw",
        lingua_url: str = "http://localhost:8001/compress",
        compress_rate: float = 0.5,
        compress_min_chars: int = 500,
        timeout: float = 60.0,
        # Backend selection: "lingua" (default).
        compressor_backend: str = "lingua",
        enable_quantum_lock: bool = False,
    ) -> None:
        if not (0.0 <= compress_rate <= 1.0):
            raise ConfigError(
                "HarnessCompressor: compress_rate must be in [0.0, 1.0], "
                f"got {compress_rate!r}"
            )
        if compress_min_chars < 0:
            raise ConfigError(
                "HarnessCompressor: compress_min_chars must be >= 0, "
                f"got {compress_min_chars!r}"
            )
        if timeout <= 0:
            raise ConfigError(
                f"HarnessCompressor: timeout must be > 0, got {timeout!r}"
            )

        self._profile = resolve_profile(profile)
        self._splitter = SectionSplitter(self._profile.sectioning)
        self._normalizer = self._profile.normalizer
        try:
            self._backend: CompressionBackend = build_backend(
                compressor_backend,
                lingua_url=lingua_url,
                timeout=timeout,
            )
        except ValueError as e:
            raise ConfigError(f"HarnessCompressor: {e}") from e
        self._cache: cachetools.LRUCache | None = None
        self._cache_lock: threading.Lock | None = None
        self._compress_rate = compress_rate
        self._compress_min_chars = compress_min_chars
        self._timeout = timeout

        # Tokens lingua must NOT split (e.g. __AGENT_WORKSPACE__) — without
        # this, BERT chops the placeholder and restore can't find it.
        placeholders_fn = getattr(self._normalizer, "placeholders", None)
        self._normalizer_placeholders: list[str] = (
            list(placeholders_fn()) if placeholders_fn else []
        )

        self._quantum_lock = None
        self._FusionContext = None
        self._ql_appendix_start: str | None = None
        self._ql_appendix_end: str | None = None
        if enable_quantum_lock:
            try:
                from claw_compactor.fusion.quantum_lock import (
                    APPENDIX_END,
                    APPENDIX_START,
                    DYNAMIC_PATTERNS,
                    QuantumLock,
                )
                from claw_compactor.fusion.base import FusionContext
            except ImportError as e:
                raise ConfigError(
                    "HarnessCompressor: enable_quantum_lock=True requires the "
                    "'claw-compactor' extra. Install via "
                    "`pip install adaptive-token-compressor[claw-compactor]`, "
                    "or pass enable_quantum_lock=False to use raw compression."
                ) from e
            self._quantum_lock = QuantumLock()
            self._FusionContext = FusionContext
            self._ql_appendix_start = APPENDIX_START
            self._ql_appendix_end = APPENDIX_END
            # Protect QLock placeholders too — otherwise lingua drops them and
            # the appendix loses its anchor in the prefix.
            self._normalizer_placeholders = list(
                self._normalizer_placeholders
            ) + [p.placeholder for p in DYNAMIC_PATTERNS]

    def set_cache(
        self,
        cache: cachetools.LRUCache | None,
        lock: threading.Lock | None,
    ) -> None:
        self._cache = cache
        self._cache_lock = lock

    def _cached_backend(self, normalised: str, rate: float) -> tuple[str, bool]:
        # Wraps the selected main backend (lingua). force_tokens is part of the
        # cache key so different placeholder sets don't collide on identical
        # normalised text; backend.cache_tag prefixes the key so distinct
        # backends never share an entry.
        force_tokens = self._normalizer_placeholders
        force_tokens_key = tuple(force_tokens)
        key, cached = cache_get(
            self._cache, self._cache_lock,
            self._backend.cache_tag, normalised, rate, force_tokens_key,
        )
        if cached is not None:
            return cached, True
        compressed = self._backend.compress(
            normalised,
            rate=rate,
            force_tokens=force_tokens if force_tokens else None,
        )
        cache_set(self._cache, self._cache_lock, key, compressed)
        return compressed, False

    def compress(self, ctx: CompressionContext) -> CompressorResult:
        start = time.perf_counter()
        tokens_before = count_messages_tokens(ctx.messages, roles=HARNESS_LIKE_ROLES)

        new_messages: list[dict] = list(ctx.messages)
        all_section_details: list[SectionDetail] = []
        total_cache_hits = 0
        total_sections_compressed = 0
        backend_errors: list[str] = []
        skip_reason: str | None = None
        compressible_count = 0

        for idx, msg in MessageAccessor.iter_by_role(ctx.messages, *HARNESS_LIKE_ROLES):
            content = msg.get("content", "")
            if not isinstance(content, str):
                continue
            if len(content) < self._compress_min_chars:
                continue

            compressible_count += 1
            new_content, msg_details, msg_cache_hits, msg_compressed, msg_errors = (
                self._compress_message_content(content)
            )
            all_section_details.extend(msg_details)
            total_cache_hits += msg_cache_hits
            total_sections_compressed += msg_compressed
            backend_errors.extend(msg_errors)

            new_messages = MessageAccessor.replace_content(new_messages, idx, new_content)

        if compressible_count == 0:
            skip_reason = "min_chars"

        tokens_after = count_messages_tokens(new_messages, roles=HARNESS_LIKE_ROLES)
        duration_ms = (time.perf_counter() - start) * 1000

        metrics = CompressorMetrics(
            name=self.name,
            scope=CompressionScope.HARNESS,
            tokens_before=tokens_before,
            tokens_after=tokens_after,
            duration_ms=duration_ms,
            error="; ".join(backend_errors) if backend_errors else None,
            skip_reason=skip_reason,
            details={
                "section_details": all_section_details,
                "cache_hits": total_cache_hits,
                "sections_total": len(all_section_details),
                "sections_compressed": total_sections_compressed,
            },
        )

        return CompressorResult(
            messages=new_messages,
            tools=ctx.tools,
            metrics=metrics,
        )

    def _compress_message_content(
        self, content: str
    ) -> tuple[str, list[SectionDetail], int, int, list[str]]:
        # QuantumLock stabilize is one-way: dynamics → placeholders + tail
        # appendix. should_apply False → no-op for static prompts.
        working_content = content
        if self._quantum_lock is not None:
            try:
                ql_ctx = self._FusionContext(content=content, role="system")
                if self._quantum_lock.should_apply(ql_ctx):
                    working_content = self._quantum_lock.apply(ql_ctx).content
            except Exception as e:
                logger.warning(
                    "QuantumLock failed, falling back to raw content: %s", e
                )
                working_content = content

        # Bypass: keep the QLock appendix verbatim. Lingua treats the
        # `<!-- ... -->` markers + field-name lines as low-importance text
        # and shreds them, breaking the appendix → original-value mapping.
        # Split it off here, compress only the prefix, and re-attach.
        appendix_tail = ""
        if (
            self._ql_appendix_start is not None
            and self._ql_appendix_end is not None
        ):
            start_idx = working_content.find(self._ql_appendix_start)
            if start_idx >= 0:
                end_marker_idx = working_content.find(
                    self._ql_appendix_end, start_idx
                )
                if end_marker_idx >= 0:
                    cut_end = end_marker_idx + len(self._ql_appendix_end)
                    appendix_tail = working_content[start_idx:cut_end]
                    working_content = working_content[:start_idx]

        sections = self._splitter.split(working_content)

        from ..core.metrics import estimate_tokens

        section_details: list[SectionDetail] = []
        cache_hits = 0
        sections_compressed = 0
        errors: list[str] = []
        parts: list[str] = []

        for section in sections:
            original_tokens = estimate_tokens(section.content)

            if not section.should_compress:
                parts.append(section.content)
                section_details.append(SectionDetail(
                    name=section.name,
                    compressed=False,
                    original_tokens=original_tokens,
                    compressed_tokens=original_tokens,
                    saved_tokens=0,
                ))
                continue

            normalised, ctx = self._normalizer.normalize(section.content)
            try:
                compressed_normalised, cache_hit = self._cached_backend(
                    normalised, self._compress_rate
                )
                restored = self._normalizer.restore(compressed_normalised, ctx)
                if cache_hit:
                    cache_hits += 1
                sections_compressed += 1
                compressed_tokens = estimate_tokens(restored)
                parts.append(restored)
                section_details.append(SectionDetail(
                    name=section.name,
                    compressed=True,
                    original_tokens=original_tokens,
                    compressed_tokens=compressed_tokens,
                    saved_tokens=max(0, original_tokens - compressed_tokens),
                    cache_hit=cache_hit,
                ))
            except BackendError as e:
                err_msg = f"{section.name}: backend compression failed"
                errors.append(err_msg)
                logger.warning("Backend failed for section '%s': %s", section.name, type(e).__name__)
                parts.append(section.content)
                section_details.append(SectionDetail(
                    name=section.name,
                    compressed=False,
                    original_tokens=original_tokens,
                    compressed_tokens=original_tokens,
                    saved_tokens=0,
                    backend_error="backend compression failed",
                ))

        final = "".join(parts)
        final = self._normalizer.sweep_residual(final, source=content)

        # Re-attach the QLock appendix bypassed earlier. It is byte-identical
        # to QuantumLock.apply()'s output → LLM sees the same originals it
        # would have seen without the bypass; lingua simply never touched it.
        if appendix_tail:
            final = final + appendix_tail

        return final, section_details, cache_hits, sections_compressed, errors

    def health_check(self, *, timeout: float = 5.0) -> HealthStatus:
        return self._backend.health_check(timeout=timeout)
