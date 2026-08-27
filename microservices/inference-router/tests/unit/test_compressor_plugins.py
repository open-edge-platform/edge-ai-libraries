# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the adaptive-token-compressor plugin.

One ``CompressorPlugin`` (``node = "compressor"``) covers every compressor kind;
``settings.type`` (harness / tool) selects the kind and the library
factory ``adaptive_token_compressor.create_compressor`` builds it. These tests
patch that factory so no Lingua server or predictor endpoint is required, and
verify the plugin layer: registration, per-type settings validation, the
request→compress→apply flow, trigger placement, error containment, and metrics
(per-instance via ``describe()``, cross-instance ``overall.*`` via
``describe_node()``).
"""

from types import SimpleNamespace
from typing import Any, Dict, Optional

import pytest

# These tests require the optional `adaptive-token-compressor` library (the
# compressor plugin imports it lazily). When it is not installed, the whole
# module is skipped at collection time.
pytest.importorskip("adaptive_token_compressor")

pytestmark = pytest.mark.compressor

from src.config import PluginConfig
from src.exceptions import ConfigurationError
from src.models import ChatCompletionMessage, ChatCompletionRequest
from src.plugins.manager import create_plugin_manager, set_request_id


# ─────────────────────────────────────────────────────────────────────────
# Fakes for the library layer
# ─────────────────────────────────────────────────────────────────────────


def _fake_metrics(tokens_before=100, tokens_after=40, skip_reason=None, error=None):
    """Mimic adaptive_token_compressor.core.metrics.CompressorMetrics."""
    saved = tokens_before - tokens_after
    ratio = 1.0 if tokens_before == 0 else tokens_after / tokens_before
    return SimpleNamespace(
        tokens_before=tokens_before,
        tokens_after=tokens_after,
        saved_tokens=saved,
        compression_ratio=ratio,
        duration_ms=1.5,
        skip_reason=skip_reason,
        error=error,
    )


def _fake_result(messages, tools=None, metrics=None):
    """Mimic adaptive_token_compressor.core.base.CompressorResult."""
    return SimpleNamespace(
        messages=messages,
        tools=tools,
        metrics=metrics if metrics is not None else _fake_metrics(),
    )


class _FakeCompressor:
    """Stand-in for a library compressor. Records the ctx it received."""

    name = "fake"

    def __init__(self, transform=None, raises: Optional[Exception] = None):
        self._transform = transform
        self._raises = raises
        self.last_ctx = None

    def compress(self, ctx):
        self.last_ctx = ctx
        if self._raises is not None:
            raise self._raises
        if self._transform is not None:
            return self._transform(ctx)
        # Default: drop everything but a single compressed system message.
        return _fake_result(
            messages=[{"role": "system", "content": "compressed"}],
            tools=ctx.tools,
        )

    def health_check(self, *, timeout: float = 5.0):
        return SimpleNamespace(state=SimpleNamespace(value="healthy"), message="ok", details={})


@pytest.fixture(autouse=True)
def _reset_manager():
    """Each test starts with a fresh CompressionManager singleton."""
    from src.plugins import compressor as comp

    comp._reset_manager_for_tests()


@pytest.fixture
def patch_factory(monkeypatch):
    """Patch the library factory so ``create_compressor(type, **kw)`` yields a fake.

    Type-agnostic: one fixture replaces every compressor kind. ``capture`` (a
    dict) records the type + ctor kwargs the plugin forwarded.
    """

    def _install(transform=None, raises=None, capture=None):
        fake = _FakeCompressor(transform=transform, raises=raises)
        import adaptive_token_compressor as atc

        def _create(type, **kwargs):  # noqa: A002 - matches library signature
            if capture is not None:
                capture.clear()
                capture["type"] = type
                capture.update(kwargs)
            return fake

        monkeypatch.setattr(atc, "create_compressor", _create, raising=True)
        return fake

    return _install


def _cfg(name, ctype, trigger="prerouting", **settings):
    """A compressor PluginConfig: node='compressor', settings.type=<ctype>."""
    return PluginConfig(
        name=name,
        node="compressor",
        trigger=trigger,
        settings={"type": ctype, **settings},
    )


def _request(messages=None, tools=None):
    return ChatCompletionRequest(
        model="test-model",
        messages=messages
        or [
            ChatCompletionMessage(role="system", content="long system prompt"),
            ChatCompletionMessage(role="user", content="hi"),
        ],
        tools=tools,
    )


# ─────────────────────────────────────────────────────────────────────────
# Registration / discovery
# ─────────────────────────────────────────────────────────────────────────


def test_compressor_plugin_is_registered():
    """The single compressor node is discovered via @register_plugin."""
    from src.plugins.manager import _PLUGIN_REGISTRY, _discover_plugin_modules

    _discover_plugin_modules()
    assert "compressor" in _PLUGIN_REGISTRY
    # The old per-type nodes no longer exist.
    assert "tool_compressor" not in _PLUGIN_REGISTRY
    assert "harness_compressor" not in _PLUGIN_REGISTRY
    assert "context_compressor" not in _PLUGIN_REGISTRY


# ─────────────────────────────────────────────────────────────────────────
# Settings validation (per-type, dispatched by settings.type)
# ─────────────────────────────────────────────────────────────────────────


def test_missing_type_is_rejected(patch_factory):
    """settings without a `type` is rejected at config load."""
    patch_factory()
    with pytest.raises(ConfigurationError):
        create_plugin_manager(
            [PluginConfig(name="bad", node="compressor", settings={})]
        )


def test_unknown_type_is_rejected(patch_factory):
    """An unrecognised settings.type is rejected at config load."""
    patch_factory()
    with pytest.raises(ConfigurationError):
        create_plugin_manager([_cfg("bad", "nope")])


def test_harness_rejects_out_of_range_rate():
    """Out-of-range values are rejected by the library constructor."""
    with pytest.raises(ConfigurationError):
        create_plugin_manager(
            [_cfg("bad", "harness", trigger="postrouting", compress_rate=1.5)]
        )


def test_tool_requires_predictor_url(patch_factory):
    """predictor_url is mandatory for a tool compressor."""
    patch_factory()
    with pytest.raises(ConfigurationError):
        create_plugin_manager([_cfg("bad", "tool")])  # missing predictor_url


# ─────────────────────────────────────────────────────────────────────────
# Compression flow
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_harness_compresses_request(patch_factory):
    """Harness compressor converts, compresses, and applies the result back."""
    patch_factory()
    pm = create_plugin_manager(
        [_cfg("compressor_post", "harness", trigger="postrouting",
              lingua_url="http://x/compress")]
    )
    out = await pm.process_postrouting_request(_request())
    assert len(out.messages) == 1
    assert out.messages[0].content == "compressed"


@pytest.mark.asyncio
async def test_tool_filters_tools(patch_factory):
    """Tool compressor rewrites request.tools from the compressor result."""
    tools = [
        {"type": "function", "function": {"name": "read"}},
        {"type": "function", "function": {"name": "write"}},
    ]

    def keep_first(ctx):
        return _fake_result(messages=ctx.messages, tools=ctx.tools[:1])

    patch_factory(transform=keep_first)
    pm = create_plugin_manager(
        [_cfg("compressor_pre", "tool", predictor_url="http://x/v1/chat/completions")]
    )
    out = await pm.process_prerouting_request(_request(tools=tools))
    assert out.tools == [{"type": "function", "function": {"name": "read"}}]


def test_tool_modes_are_forwarded_to_library(patch_factory):
    """tool settings (prompt_mode/tool_descriptions_mode) reach create_compressor."""
    captured: Dict[str, Any] = {}
    patch_factory(capture=captured)

    create_plugin_manager(
        [_cfg(
            "compressor_pre", "tool",
            predictor_url="http://x/v1/chat/completions",
            prompt_mode="static",
            tool_descriptions_mode="dynamic",
        )]
    )

    assert captured.get("type") == "tool"
    assert captured.get("prompt_mode") == "static"
    assert captured.get("tool_descriptions_mode") == "dynamic"
    # Router-only fields must NOT be forwarded to the library constructor.
    assert "cache_size" not in captured
    assert "metrics" not in captured


@pytest.mark.asyncio
async def test_messages_converted_to_plain_dicts(patch_factory):
    """The library receives plain OpenAI dicts (role flattened to str)."""
    fake = patch_factory(transform=lambda ctx: _fake_result(messages=ctx.messages))
    pm = create_plugin_manager(
        [_cfg("compressor_post", "harness", trigger="postrouting")]
    )
    await pm.process_postrouting_request(_request())
    assert isinstance(fake.last_ctx.messages[0], dict)
    assert fake.last_ctx.messages[0]["role"] == "system"


# ─────────────────────────────────────────────────────────────────────────
# Trigger-phase flexibility
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("trigger", ["prerouting", "postrouting", "postresponse"])
async def test_can_place_in_any_trigger(patch_factory, trigger):
    """A compressor loads into whichever phase the config names."""
    patch_factory()
    pm = create_plugin_manager([_cfg(f"compressor_{trigger}", "harness", trigger=trigger)])
    buckets = {
        "prerouting": pm.prerouting_plugins,
        "postrouting": pm.postrouting_plugins,
        "postresponse": pm.postresponse_plugins,
    }
    assert len(buckets[trigger]) == 1
    assert buckets[trigger][0].name == f"compressor_{trigger}"


@pytest.mark.asyncio
async def test_postresponse_placement_warns(patch_factory, caplog):
    """A compressor at postresponse logs a no-op warning (still loads)."""
    patch_factory()
    import logging

    with caplog.at_level(logging.WARNING, logger="src.plugins.compressor"):
        pm = create_plugin_manager(
            [_cfg("compressor_postresp", "harness", trigger="postresponse")]
        )

    assert len(pm.postresponse_plugins) == 1  # still loads
    assert any("no-op" in r.message for r in caplog.records)


# ─────────────────────────────────────────────────────────────────────────
# Error containment
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_compression_error_returns_unmodified_request(patch_factory, caplog):
    """A compressor that raises must not crash the pipeline."""
    patch_factory(raises=RuntimeError("token=super-secret"))
    pm = create_plugin_manager([_cfg("compressor_post", "harness", trigger="postrouting")])
    req = _request()
    out = await pm.process_postrouting_request(req)
    # Unchanged: still two messages with original content.
    assert len(out.messages) == 2
    assert out.messages[0].content == "long system prompt"
    assert "super-secret" not in caplog.text


@pytest.mark.asyncio
async def test_health_check_error_is_sanitized(patch_factory):
    """Health responses must not expose backend exception text."""
    fake = patch_factory()
    pm = create_plugin_manager([_cfg("compressor_health", "harness")])
    plugin = pm.get_plugin_by_name_and_node("compressor_health", "compressor")

    def fail_health_check(*, timeout: float = 5.0):
        raise RuntimeError("token=super-secret")

    fake.health_check = fail_health_check
    health = await plugin.health_check()

    assert health == {
        "healthy": False,
        "state": "unhealthy",
        "message": "compressor unavailable",
    }


# ─────────────────────────────────────────────────────────────────────────
# Metrics aggregation via the shared manager
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_config_driven_metrics_snapshot(patch_factory):
    """Metrics declared in settings are registered and namespaced by name."""
    patch_factory()
    from src.plugins import compressor as comp

    pm = create_plugin_manager(
        [_cfg("compressor_post", "harness", trigger="postrouting",
              metrics=["total_saved", "call_count", "compression_ratio"])]
    )

    set_request_id("req-1")  # overall.* PerRequest metrics need a denominator
    await pm.process_postrouting_request(_request())

    snap = comp.get_compression_metrics()
    assert snap.get("compressor_post.total_saved") == 60  # 100 - 40
    assert snap.get("compressor_post.call_count") == 1
    assert snap.get("compressor_post.compression_ratio") == pytest.approx(0.4)


@pytest.mark.asyncio
async def test_unknown_metric_is_skipped_not_fatal(patch_factory):
    """An unrecognised metric key is logged and skipped, not raised."""
    patch_factory()
    from src.plugins import compressor as comp

    pm = create_plugin_manager(
        [_cfg("compressor_post", "harness", trigger="postrouting",
              metrics=["total_saved", "does_not_exist"])]
    )
    set_request_id("req-1")
    await pm.process_postrouting_request(_request())

    snap = comp.get_compression_metrics()
    assert snap.get("compressor_post.total_saved") == 60
    assert "compressor_post.does_not_exist" not in snap


@pytest.mark.asyncio
async def test_two_instances_metrics_do_not_collide(patch_factory):
    """Same metric key on two instances stays separate via name prefixing."""
    patch_factory()
    from src.plugins import compressor as comp

    pm = create_plugin_manager(
        [
            _cfg("compressor_pre", "tool",
                 predictor_url="http://x/v1/chat/completions", metrics=["total_saved"]),
            _cfg("compressor_post", "harness", trigger="postrouting",
                 metrics=["total_saved"]),
        ]
    )
    set_request_id("req-1")
    await pm.process_prerouting_request(_request())
    await pm.process_postrouting_request(_request())

    snap = comp.get_compression_metrics()
    assert "compressor_pre.total_saved" in snap
    assert "compressor_post.total_saved" in snap


@pytest.mark.asyncio
async def test_default_metrics_when_omitted(patch_factory):
    """Omitting `metrics` registers the default per-compressor set."""
    patch_factory()
    from src.plugins import compressor as comp

    pm = create_plugin_manager([_cfg("compressor_post", "harness", trigger="postrouting")])
    set_request_id("req-1")
    await pm.process_postrouting_request(_request())

    snap = comp.get_compression_metrics()
    for key in comp.DEFAULT_PER_COMPRESSOR_METRICS:
        assert f"compressor_post.{key}" in snap, key


# ─────────────────────────────────────────────────────────────────────────
# Overall (cross-compressor) metrics + req_id dedup
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_overall_metrics_registered_and_aggregate(patch_factory):
    """overall.* metrics sum across every compressor source."""
    patch_factory()
    from src.plugins import compressor as comp

    pm = create_plugin_manager(
        [
            _cfg("compressor_pre", "tool", predictor_url="http://x/v1/chat/completions"),
            _cfg("compressor_post", "harness", trigger="postrouting"),
        ]
    )

    set_request_id("req-1")
    await pm.process_prerouting_request(_request())
    await pm.process_postrouting_request(_request())

    snap = comp.get_compression_metrics()
    assert snap.get("overall.total_input") == 200  # 100 + 100
    assert snap.get("overall.total_output") == 80  # 40 + 40
    assert snap.get("overall.compression_ratio") == pytest.approx(0.4)
    assert "overall.avg_duration_per_request" in snap


@pytest.mark.asyncio
async def test_overall_total_requests_dedup_by_req_id(patch_factory):
    """Two compressors on the same req_id count as ONE request; new id → +1."""
    patch_factory()
    from src.plugins import compressor as comp

    pm = create_plugin_manager(
        [
            _cfg("compressor_pre", "tool", predictor_url="http://x/v1/chat/completions"),
            _cfg("compressor_post", "harness", trigger="postrouting"),
        ]
    )

    set_request_id("req-1")
    await pm.process_prerouting_request(_request())
    await pm.process_postrouting_request(_request())
    assert comp.get_compression_metrics().get("overall.total_requests") == 1

    set_request_id("req-2")
    await pm.process_prerouting_request(_request())
    await pm.process_postrouting_request(_request())
    assert comp.get_compression_metrics().get("overall.total_requests") == 2


@pytest.mark.asyncio
async def test_avg_duration_per_request_uses_unique_requests(patch_factory):
    """avg_duration_per_request divides summed duration by unique req count."""
    patch_factory()
    from src.plugins import compressor as comp

    pm = create_plugin_manager([_cfg("compressor_post", "harness", trigger="postrouting")])
    set_request_id("req-1")
    await pm.process_postrouting_request(_request())
    set_request_id("req-2")
    await pm.process_postrouting_request(_request())

    snap = comp.get_compression_metrics()
    assert snap.get("overall.total_requests") == 2
    assert snap.get("overall.avg_duration_per_request") == pytest.approx(1.5)


# ─────────────────────────────────────────────────────────────────────────
# Metrics surfaced via describe() / describe_node() (the plugin API contract)
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_describe_folds_instance_metrics(patch_factory):
    """GET /plugins/{node}/{name} → describe(): this instance's own metrics."""
    patch_factory()
    pm = create_plugin_manager([_cfg("compressor_post", "harness", trigger="postrouting")])
    set_request_id("req-1")
    await pm.process_postrouting_request(_request())

    plugin = pm.get_plugin_by_name_and_node("compressor_post", "compressor")
    body = plugin.describe()
    assert body["name"] == "compressor_post"
    assert body["node"] == "compressor"
    assert body["metrics"].get("compressor_post.total_input") == 100


@pytest.mark.asyncio
async def test_describe_node_folds_overall_metrics(patch_factory):
    """GET /plugins/{node} → describe_node(): metrics across all instances."""
    patch_factory()
    from src.plugins.compressor import CompressorPlugin

    pm = create_plugin_manager(
        [
            _cfg("compressor_pre", "tool", predictor_url="http://x/v1/chat/completions"),
            _cfg("compressor_post", "harness", trigger="postrouting"),
        ]
    )
    set_request_id("req-1")
    await pm.process_prerouting_request(_request())
    await pm.process_postrouting_request(_request())

    node_view = CompressorPlugin.describe_node()
    assert node_view["node"] == "compressor"
    assert "cache_stats" in node_view
    assert node_view["metrics"].get("overall.total_input") == 200
    # per-instance metrics are visible at the node level too
    assert node_view["metrics"].get("compressor_pre.total_input") == 100


@pytest.mark.asyncio
async def test_describe_metrics_are_source_scoped(patch_factory):
    """describe() shows only that instance's source; reset() clears only it."""
    patch_factory()

    pm = create_plugin_manager(
        [
            _cfg("compressor_pre", "tool", predictor_url="http://x"),
            _cfg("compressor_post", "harness", trigger="postrouting"),
        ]
    )
    set_request_id("req-1")
    req = _request()
    await pm.process_prerouting_request(req)
    await pm.process_postrouting_request(req)

    pre = pm.get_plugin_by_name_and_node("compressor_pre", "compressor")
    post = pm.get_plugin_by_name_and_node("compressor_post", "compressor")

    pre_metrics = pre.describe()["metrics"]
    post_metrics = post.describe()["metrics"]
    assert "compressor_pre.total_input" in pre_metrics
    assert "compressor_post.total_input" not in pre_metrics
    assert "compressor_post.total_input" in post_metrics
    assert "compressor_pre.total_input" not in post_metrics

    # Instance reset zeroes only this source; the other is untouched.
    assert post.reset() is True
    assert post.describe()["metrics"].get("compressor_post.total_input") == 0.0
    assert pre.describe()["metrics"].get("compressor_pre.total_input") == pre_metrics.get(
        "compressor_pre.total_input"
    )


@pytest.mark.asyncio
async def test_reset_node_clears_all(patch_factory):
    """reset_node() clears every compressor source; snapshot empties."""
    patch_factory()
    from src.plugins.compressor import CompressorPlugin
    from src.plugins import compressor as comp

    pm = create_plugin_manager([_cfg("compressor_post", "harness", trigger="postrouting")])
    set_request_id("req-1")
    await pm.process_postrouting_request(_request())
    assert comp.get_compression_metrics().get("compressor_post.total_input") == 100

    assert CompressorPlugin.reset_node() is True
    # No req_id seen post-reset → PerRequest snapshot empties.
    assert comp.get_compression_metrics() == {}


# ─────────────────────────────────────────────────────────────────────────
# request_id propagation (regression: set once at API entry must reach both
# the non-streaming endpoint body AND the StreamingResponse generator, which
# runs after the endpoint returns)
# ─────────────────────────────────────────────────────────────────────────


def test_request_id_propagates_to_streaming_and_non_streaming():
    """A request_id set at the endpoint entry is visible in both response paths."""
    from fastapi import FastAPI
    from fastapi.responses import StreamingResponse
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.testclient import TestClient

    from src.plugins.manager import get_request_id

    app = FastAPI()
    app.add_middleware(CORSMiddleware, allow_origins=["*"])  # mirror src/api/app.py

    @app.post("/chat")
    async def chat(stream: bool = False):
        set_request_id("req-XYZ")  # set ONCE at entry, as router.py does
        if stream:
            async def gen():
                # runs after chat() returns — the path compressors take
                yield f"seen={get_request_id()}".encode()
            return StreamingResponse(gen(), media_type="text/plain")
        return {"seen": get_request_id()}

    client = TestClient(app)
    assert client.post("/chat?stream=false").json()["seen"] == "req-XYZ"
    assert "seen=req-XYZ" in client.post("/chat?stream=true").text
