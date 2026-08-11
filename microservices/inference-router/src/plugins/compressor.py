# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Compressor plugin — one ``compressor`` node covering every compressor type.

A single :class:`CompressorPlugin` (``node = "compressor"``) handles all
compressor kinds. The kind is chosen per instance by ``settings.type``
(``harness`` / ``tool`` / ``context``) and constructed through the library
factory ``adaptive_token_compressor.create_compressor``. Every instance shares
one process-wide ``CompressionManager`` for caching + metrics aggregation;
per-instance metrics surface via ``describe()`` and cross-instance ``overall.*``
metrics via ``describe_node()``.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any, Dict, List, Optional, Type

from pydantic import BaseModel, ConfigDict, Field

from src.models import ChatCompletionRequest
from src.plugins.base import PluginBaseNode, PluginSchemaError
from src.plugins.manager import (
    get_request_id,
    register_node_finalizer,
    register_plugin,
)

logger = logging.getLogger(__name__)

# The node key this plugin registers under. Every compressor instance shares this
# one node, so the node IS the family — no separate plugin_group is needed.
_NODE = "compressor"


# ─────────────────────────────────────────────────────────────────────────
# Shared CompressionManager singleton
# ─────────────────────────────────────────────────────────────────────────

_MANAGER: Optional[Any] = None  # adaptive_token_compressor.CompressionManager
_MANAGER_LOCK = threading.Lock()


def _get_manager(cache_size: int = 4096) -> Optional[Any]:
    """Get or lazily create the shared ``CompressionManager`` (None if lib missing)."""
    global _MANAGER
    if _MANAGER is not None:
        return _MANAGER
    with _MANAGER_LOCK:
        if _MANAGER is None:
            try:
                from adaptive_token_compressor import CompressionManager
            except Exception as exc:  # pragma: no cover - import guard
                logger.warning(
                    "adaptive-token-compressor not importable (%s); compressor "
                    "plugins run standalone with no cache/metrics aggregation.",
                    exc,
                )
                return None
            _MANAGER = CompressionManager(cache_size=cache_size)
            logger.info(
                "Initialized shared CompressionManager (cache_size=%d)", cache_size
            )
    return _MANAGER


def get_compression_metrics(source: str | None = None) -> Dict[str, float]:
    """Metric snapshot from the shared manager (global or source-scoped)."""
    if _MANAGER is None:
        return {}
    try:
        return _MANAGER.snapshot(source=source)
    except Exception as exc:
        # e.g. PerRequest metrics registered but no request seen yet.
        logger.debug("compression snapshot unavailable: %s", exc)
        return {}


def get_compression_cache_stats() -> Dict[str, Dict[str, int]]:
    """Per-compressor cache stats from the shared manager (``{}`` if none)."""
    if _MANAGER is None:
        return {}
    return _MANAGER.cache_stats()


def reset_compression_metrics(source: str | None = None) -> None:
    """Clear metrics + caches globally or for one source."""
    if _MANAGER is not None:
        _MANAGER.reset(source=source)


def _reset_manager_for_tests() -> None:
    """Drop the singleton so tests start from a clean slate."""
    global _MANAGER
    with _MANAGER_LOCK:
        _MANAGER = None


# ─────────────────────────────────────────────────────────────────────────
# Metric registration (config-driven)
# ─────────────────────────────────────────────────────────────────────────

# Config metric key → library MetricSpec class name (per-compressor set).
_METRIC_SPECS = {
    "call_count": "CallCount",
    "total_input": "TotalInput",
    "total_output": "TotalOutput",
    "total_saved": "TotalSaved",
    "total_duration": "TotalDuration",
    "compression_ratio": "CompressionRatio",
    "avg_saved_per_call": "AvgSavedPerCall",
    "avg_duration_per_call": "AvgDurationPerCall",
    "avg_input_per_call": "AvgInputPerCall",
    "avg_output_per_call": "AvgOutputPerCall",
}

# Valid set surfaced for settings validation error messages.
SUPPORTED_METRICS = frozenset(_METRIC_SPECS)

# Default per-compressor metrics when a plugin's settings omit `metrics`.
DEFAULT_PER_COMPRESSOR_METRICS = [
    "total_input",
    "total_output",
    "call_count",
    "compression_ratio",
    "avg_duration_per_call",
]

# Prefix for cross-compressor metrics (registered by the group finalizer).
_OVERALL_PREFIX = "overall"


def _register_metrics(manager: Any, source: str, metric_keys: List[str]) -> None:
    """Register per-compressor metrics, namespaced ``<source>.<key>``. Unknown keys skipped."""
    if not metric_keys:
        return
    import adaptive_token_compressor as atc

    for key in metric_keys:
        spec_name = _METRIC_SPECS.get(key)
        if spec_name is None:
            logger.warning(
                "compressor '%s': unknown metric %r (supported: %s) — skipped",
                source,
                key,
                sorted(SUPPORTED_METRICS),
            )
            continue
        try:
            spec_cls = getattr(atc, spec_name)
            manager.register_metric(f"{source}.{key}", spec_cls(sources=source))
        except Exception as exc:
            logger.warning(
                "compressor '%s': failed to register metric %r (%s) — skipped",
                source,
                key,
                exc,
            )


def register_overall_metrics(sources: List[str]) -> None:
    """Register cross-compressor ``overall.*`` metrics spanning ``sources``. No-op if empty."""
    if not sources:
        return
    manager = _get_manager()
    if manager is None:
        return
    import adaptive_token_compressor as atc

    sources = list(sources)
    specs = {
        f"{_OVERALL_PREFIX}.total_requests": atc.RequestCount(),
        f"{_OVERALL_PREFIX}.total_input": atc.TotalInput(sources=sources),
        f"{_OVERALL_PREFIX}.total_output": atc.TotalOutput(sources=sources),
        f"{_OVERALL_PREFIX}.compression_ratio": atc.CompressionRatio(sources=sources),
        f"{_OVERALL_PREFIX}.avg_duration_per_request": atc.AvgDurationPerRequest(
            sources=sources
        ),
    }
    for name, spec in specs.items():
        try:
            manager.register_metric(name, spec)
        except Exception as exc:
            logger.warning(
                "compression overall metrics: failed to register %r (%s)", name, exc
            )
    logger.info("Registered overall compression metrics (sources=%s)", sources)


@register_node_finalizer(_NODE)
def _finalize_compressor_node(members: List[PluginBaseNode]) -> None:
    """Node finalizer: register overall.* metrics across all compressor instances."""
    register_overall_metrics([p.name for p in members])


# ─────────────────────────────────────────────────────────────────────────
# Request ↔ CompressionContext conversion
# ─────────────────────────────────────────────────────────────────────────


def _request_to_context(request: ChatCompletionRequest) -> Any:
    """Build a ``CompressionContext`` from a request (messages → OpenAI-shaped dicts)."""
    from adaptive_token_compressor import CompressionContext

    messages = [
        msg.model_dump(mode="json", exclude_none=True) for msg in request.messages
    ]
    return CompressionContext(messages=messages, tools=request.tools)


def _apply_result(request: ChatCompletionRequest, result: Any) -> ChatCompletionRequest:
    """Return a copy of the request with the compressed messages/tools applied."""
    from src.models import ChatCompletionMessage

    messages = [ChatCompletionMessage.model_validate(m) for m in result.messages]
    return request.model_copy(update={"messages": messages, "tools": result.tools})


def _log_metrics(plugin_name: str, ctype: str, result: Any) -> None:
    """Emit a single info line summarising one compress() call."""
    m = getattr(result, "metrics", None)
    if m is None:
        return
    logger.info(
        "[%s] %s: %s→%s tokens (saved=%s, ratio=%.2f, %.1fms%s%s)",
        plugin_name,
        ctype,
        m.tokens_before,
        m.tokens_after,
        m.saved_tokens,
        m.compression_ratio,
        m.duration_ms,
        f", skip={m.skip_reason}" if m.skip_reason else "",
        f", error={m.error}" if m.error else "",
    )


# ─────────────────────────────────────────────────────────────────────────
# Settings validation (library-driven for all compressor types)
# ─────────────────────────────────────────────────────────────────────────

# Settings keys that are router concerns, NOT library constructor params.
_COMMON_KEYS = frozenset({"type", "cache_size", "metrics", "extra_config"})


class _CompressorConfig(BaseModel):
    """Minimal router config fields; compressor kwargs are library-driven extras."""

    # Keep unknown fields so dynamic library-driven types can pass constructor
    # kwargs through without adding a dedicated settings model in the router.
    model_config = ConfigDict(extra="allow")

    type: str  # "harness" | "tool" | "context"
    cache_size: int = Field(default=4096, ge=0)
    metrics: List[str] = Field(default_factory=list)  # see SUPPORTED_METRICS


def _library_params(config: _CompressorConfig) -> Dict[str, Any]:
    """The library constructor kwargs = all settings fields minus router-only ones."""
    return {
        k: v for k, v in config.model_dump().items() if k not in _COMMON_KEYS
    }


# ─────────────────────────────────────────────────────────────────────────
# CompressorPlugin — one node, all compressor types
# ─────────────────────────────────────────────────────────────────────────


@register_plugin
class CompressorPlugin(PluginBaseNode):
    """Adaptive token compression. One instance = one compressor of ``settings.type``.

    ``node = "compressor"``; ``settings.type`` selects the kind (harness / tool /
    context). Per-instance metrics fold into ``describe()``; cross-instance
    ``overall.*`` metrics into ``describe_node()``.
    """

    @classmethod
    def plugin_type(cls) -> str:
        return _NODE

    @classmethod
    def settings_model(cls) -> Type[BaseModel]:
        # Base shape for node metadata; per-type validation is in validate_settings.
        return _CompressorConfig

    @classmethod
    def validate_settings(cls, settings: Dict[str, Any]) -> BaseModel:
        """Validate all compressor types via library schema checks."""
        ctype = settings.get("type")
        if not isinstance(ctype, str) or not ctype:
            raise PluginSchemaError(
                f"compressor: settings.type must be a non-empty string, got {ctype!r}"
            )

        # Single validation path for both known and future library types.
        try:
            import adaptive_token_compressor as atc
        except Exception as exc:  # pragma: no cover - import guard
            raise PluginSchemaError(
                "compressor: adaptive-token-compressor is not importable; "
                f"cannot validate settings.type={ctype!r}: {exc}"
            ) from exc

        known = sorted(atc.available_compressor_types())
        if ctype not in known:
            raise PluginSchemaError(
                f"compressor: settings.type must be one of {known}, got {ctype!r}"
            )

        try:
            schema = atc.config_schema(ctype)
        except Exception as exc:
            raise PluginSchemaError(
                f"compressor: failed to fetch config schema for type {ctype!r}: {exc}"
            ) from exc

        properties: Dict[str, Dict[str, Any]] = dict(schema.get("properties", {}) or {})
        required = set(schema.get("required", []) or [])
        allowed = set(properties)
        provided_lib_keys = {k for k in settings if k not in _COMMON_KEYS}

        unknown = sorted(provided_lib_keys - allowed)
        missing = sorted(required - provided_lib_keys)
        bad_enum: List[str] = []
        for key in sorted(provided_lib_keys & allowed):
            choices = properties.get(key, {}).get("enum")
            if choices is not None and settings.get(key) not in choices:
                bad_enum.append(
                    f"{key}={settings.get(key)!r} not in {list(choices)!r}"
                )

        errors: List[str] = []
        if unknown:
            errors.append(f"unknown params: {unknown}")
        if missing:
            errors.append(f"missing required params: {missing}")
        if bad_enum:
            errors.append("invalid enum values: " + "; ".join(bad_enum))
        if errors:
            raise PluginSchemaError(
                f"Invalid settings for compressor type {ctype!r}: " + " | ".join(errors)
            )

        # Inject constructor defaults surfaced by the library schema so
        # `_library_params` forwards explicit values to create_compressor.
        merged = dict(settings)
        for key, fragment in properties.items():
            if key not in merged and "default" in fragment:
                merged[key] = fragment["default"]

        try:
            return _CompressorConfig(**merged)
        except Exception as exc:
            raise PluginSchemaError(
                f"Invalid common compressor settings for type {ctype!r}: {exc}"
            ) from exc

    def init(self) -> None:
        """Build the library compressor for ``settings.type`` and register it."""
        s = self.parsed_settings
        self._ctype: str = s.type

        # Compressors only act on requests; at postresponse they are a no-op.
        if self.trigger == "postresponse":
            logger.warning(
                "compressor '%s' (type=%s) at trigger=postresponse is a no-op; "
                "use prerouting/postrouting.",
                self.name,
                self._ctype,
            )

        self._compressor = self._build_compressor(s)

        # Register with the shared manager; `name` is the (unique) source key. On
        # failure (e.g. duplicate name) degrade to standalone — no cache/aggregation.
        self._wrapper = None
        manager = _get_manager(cache_size=s.cache_size)
        if manager is not None:
            try:
                self._wrapper = manager.register_compressor(self.name, self._compressor)
                logger.info(
                    "Registered compressor '%s' (type=%s, trigger=%s)",
                    self.name,
                    self._ctype,
                    self.trigger,
                )
                requested = s.metrics or DEFAULT_PER_COMPRESSOR_METRICS
                _register_metrics(manager, self.name, requested)
            except Exception as exc:
                logger.warning(
                    "compressor '%s': manager registration failed (%s); running standalone.",
                    self.name,
                    exc,
                )

    def _build_compressor(self, s: _CompressorConfig) -> Any:
        """Construct the library compressor via the type-dispatching factory."""
        from adaptive_token_compressor import create_compressor
        from adaptive_token_compressor.core.exceptions import ConfigError

        try:
            return create_compressor(self._ctype, **_library_params(s))
        except ConfigError as exc:
            raise PluginSchemaError(
                f"Invalid settings for compressor type {self._ctype!r}: {exc}"
            ) from exc

    def _compress(self, request: ChatCompletionRequest) -> ChatCompletionRequest:
        """Shared request→compress→apply path with error containment."""
        try:
            ctx = _request_to_context(request)
            if self._wrapper is not None:
                # req_id lets the library count unique requests, not compress calls.
                result = self._wrapper.compress(ctx, req_id=get_request_id())
            else:
                result = self._compressor.compress(ctx)
            _log_metrics(self.name, self._ctype, result)
            return _apply_result(request, result)
        except Exception as exc:
            logger.error(
                "[%s] compressor (type=%s) failed: %s — returning request unmodified.",
                self.name,
                self._ctype,
                exc,
                exc_info=True,
            )
            return request

    async def process_request(
        self, request: ChatCompletionRequest
    ) -> ChatCompletionRequest:
        # `_compress` calls the library compressor, which makes *synchronous*
        # blocking HTTP calls (lingua / predictor). Offload to a worker thread so
        # the event loop stays responsive. Safe to run concurrently: the library
        # compressor's cache/aggregator are lock-guarded.
        return await asyncio.to_thread(self._compress, request)

    # Compressors act on requests only; process_response inherits the passthrough.

    def describe(self) -> Dict[str, Any]:
        """Instance view + this compressor's own (source-scoped) metrics."""
        return {
            **super().describe(),
            "metrics": get_compression_metrics(source=self.name),
        }

    @classmethod
    def describe_node(cls) -> Dict[str, Any]:
        """Node view + metrics across ALL compressor instances (incl. overall.*)."""
        return {
            **cls.node_metadata(),
            "metrics": get_compression_metrics(),
            "cache_stats": get_compression_cache_stats(),
        }

    def reset(self) -> bool:
        """Clear this compressor's own metrics + cache."""
        reset_compression_metrics(source=self.name)
        return True

    @classmethod
    def reset_node(cls) -> bool:
        """Clear metrics + caches across all compressor instances."""
        reset_compression_metrics()
        return True

    async def health_check(self) -> Dict[str, Any]:
        """Probe the library compressor's backend (Lingua / predictor)."""

        def _probe() -> Dict[str, Any]:
            try:
                status = self._compressor.health_check(timeout=5.0)
                state = getattr(status, "state", None)
                state_str = getattr(state, "value", str(state))
                return {
                    "healthy": state_str != "unhealthy",
                    "state": state_str,
                    "message": getattr(status, "message", None) or "OK",
                    "details": dict(getattr(status, "details", {}) or {}),
                }
            except Exception as exc:
                return {"healthy": False, "state": "unhealthy", "message": str(exc)}

        return await asyncio.to_thread(_probe)
