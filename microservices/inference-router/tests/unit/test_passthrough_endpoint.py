# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for pass-through service providers and their generated endpoints.

The backing services are never deployed here — every upstream call is mocked by
patching ``httpx.AsyncClient``. Coverage is three layers:

1. ``create_provider`` dispatch (service type -> PassthroughProvider).
2. ``PassthroughProvider.forward`` behavior (URL/header/body forwarding,
   binary vs JSON, auth injection, error mapping).
3. The registry-generated ``/v1`` routes via a TestClient (forwarding, 503 when
   unconfigured, exclusion from ``/v1/models``, and the shared concurrency limit).
"""

from __future__ import annotations

import asyncio
import json
import queue
import threading
from types import SimpleNamespace

import httpx
import pytest
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.config import ProviderConfig, RouterConfig, RoutingConfig, TelemetryConfig
from src.config.base import TelemetryBackendType
from src.observability import InMemoryTelemetry
from src.providers import (
    PASSTHROUGH_SERVICES,
    PASSTHROUGH_TYPES,
    LitellmProvider,
    PassthroughProvider,
    create_provider,
)
from src.providers.passthrough_provider import DEFAULT_TIMEOUT


pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class FakeRequest:
    """Minimal stand-in for a FastAPI Request used by ``forward``."""

    def __init__(self, body: bytes = b"", headers: dict[str, str] | None = None):
        self._body = body
        self.headers = headers or {}

    async def body(self) -> bytes:
        return self._body


def run(coro):
    """Drive a coroutine to completion (repo has no pytest-asyncio plugin)."""
    return asyncio.run(coro)


def patch_httpx(monkeypatch, *, response: httpx.Response | None = None, exc: Exception | None = None):
    """Replace ``httpx.AsyncClient`` with a fake that records the outgoing POST.

    Returns a list that receives one ``SimpleNamespace(url, content, headers,
    timeout)`` per call, so tests can assert exactly what was forwarded.
    """
    calls: list[SimpleNamespace] = []

    class _FakeClient:
        def __init__(self, *_args, **kwargs):
            self._timeout = kwargs.get("timeout")

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return False

        async def post(self, url, content=None, headers=None):
            calls.append(
                SimpleNamespace(url=url, content=content, headers=headers, timeout=self._timeout)
            )
            if exc is not None:
                raise exc
            return response

    monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)
    return calls


def make_passthrough(
    service: str,
    *,
    endpoint: str | None = "http://backend.invalid",
    timeout: float | None = 30.0,
    auth: dict | None = None,
) -> PassthroughProvider:
    settings: dict = {"endpoint": endpoint, "timeout": timeout}
    if auth is not None:
        settings["auth"] = auth
    return PassthroughProvider(
        ProviderConfig(name=f"{service}-backend", type=service, model=service, settings=settings)
    )


class PassthroughRouterStub:
    """Router stub exposing only what the pass-through endpoints touch."""

    def __init__(self, providers: dict[str, object] | None = None):
        self.plugin_manager = object()  # create_app reads router.plugin_manager
        self._providers = providers or {}

    def passthrough_for(self, service: str):
        return self._providers.get(service)

    async def health_check(self) -> dict:
        return {}


def build_app(router: PassthroughRouterStub, *, config: RouterConfig | None = None, max_concurrency: int = 0):
    return create_app(
        router,
        config or RouterConfig(providers=[], telemetry=TelemetryConfig(backend=TelemetryBackendType.MEMORY)),
        InMemoryTelemetry(),
        max_concurrency=max_concurrency,
    )


# ---------------------------------------------------------------------------
# 1) create_provider dispatch
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("service", sorted(PASSTHROUGH_SERVICES))
def test_create_provider_builds_passthrough_for_service_types(service: str) -> None:
    cfg = ProviderConfig(
        name=f"{service}-backend",
        type=service,
        model=service,
        settings={"endpoint": "http://x.invalid"},
    )
    provider = create_provider(cfg)
    assert isinstance(provider, PassthroughProvider)
    assert provider.service == service


def test_create_provider_builds_litellm_for_other_types() -> None:
    cfg = ProviderConfig(
        name="chat", type="hosted_vllm", model="m", settings={"endpoint": "http://x/v1"}
    )
    assert isinstance(create_provider(cfg), LitellmProvider)


def test_create_provider_returns_none_when_disabled() -> None:
    cfg = ProviderConfig(name="ocr", type="ocr", model="ocr", enabled=False, settings={})
    assert create_provider(cfg) is None


# ---------------------------------------------------------------------------
# 2) PassthroughProvider.forward
# ---------------------------------------------------------------------------


def test_forward_json_service_passes_through(monkeypatch) -> None:
    # Upstream sends a hop-by-hop header (connection) plus a normal one (x-upstream).
    upstream = httpx.Response(
        200, json={"text": "hello"}, headers={"connection": "keep-alive", "x-upstream": "yes"}
    )
    calls = patch_httpx(monkeypatch, response=upstream)
    provider = make_passthrough("ocr", endpoint="http://ocr.invalid", timeout=42.0)

    resp = run(provider.forward(
        FakeRequest(body=b'{"image_path": "/x"}', headers={"host": "gw", "content-type": "application/json"})
    ))

    assert resp.status_code == 200
    assert json.loads(resp.body) == {"text": "hello"}
    # Base endpoint gets the service subpath appended, and the per-request timeout used.
    assert calls[0].url == "http://ocr.invalid/v1/ocr"
    assert calls[0].timeout == 42.0
    assert calls[0].content == b'{"image_path": "/x"}'
    # Host header is stripped before forwarding; other client headers survive.
    assert "host" not in calls[0].headers
    assert calls[0].headers["content-type"] == "application/json"
    # Hop-by-hop header from upstream is dropped; a normal header is forwarded.
    resp_headers = {k.lower() for k in resp.headers}
    assert "connection" not in resp_headers
    assert resp.headers["x-upstream"] == "yes"


def test_forward_defaults_timeout_when_unset(monkeypatch) -> None:
    # An omitted settings.timeout must fall back to DEFAULT_TIMEOUT, never None
    # (httpx treats None as no timeout at all).
    provider = make_passthrough("ocr", endpoint="http://ocr.invalid", timeout=None)
    assert provider.timeout == DEFAULT_TIMEOUT

    calls = patch_httpx(monkeypatch, response=httpx.Response(200, json={}))
    run(provider.forward(
        FakeRequest(body=b"{}", headers={"content-type": "application/json"})
    ))
    assert calls[0].timeout == DEFAULT_TIMEOUT


def test_forward_does_not_double_service_path(monkeypatch) -> None:
    calls = patch_httpx(monkeypatch, response=httpx.Response(200, json={}))
    # Endpoint already points at the full service path.
    provider = make_passthrough("ocr", endpoint="http://ocr.invalid/v1/ocr")

    run(provider.forward(FakeRequest()))

    assert calls[0].url == "http://ocr.invalid/v1/ocr"


def test_forward_binary_service_returns_bytes(monkeypatch) -> None:
    upstream = httpx.Response(200, content=b"AUDIODATA", headers={"content-type": "audio/mpeg"})
    patch_httpx(monkeypatch, response=upstream)
    provider = make_passthrough("tts", endpoint="http://tts.invalid")

    resp = run(provider.forward(FakeRequest(body=b'{"input": "hi"}')))

    assert resp.status_code == 200
    assert resp.body == b"AUDIODATA"
    assert resp.media_type == "audio/mpeg"


def test_forward_injects_configured_auth(monkeypatch) -> None:
    calls = patch_httpx(monkeypatch, response=httpx.Response(200, json={}))
    provider = make_passthrough(
        "embeddings",
        endpoint="http://emb.invalid",
        auth={"scheme": "bearer", "api_key": "sk-xyz", "custom_headers": {"x-tenant": "acme"}},
    )

    run(provider.forward(FakeRequest(headers={"host": "gw"})))

    assert calls[0].headers["authorization"] == "Bearer sk-xyz"
    assert calls[0].headers["x-tenant"] == "acme"


def test_forward_scheme_none_adds_no_auth(monkeypatch) -> None:
    calls = patch_httpx(monkeypatch, response=httpx.Response(200, json={}))
    provider = make_passthrough(
        "embeddings", endpoint="http://emb.invalid", auth={"scheme": "none", "api_key": "sk-should-be-ignored"}
    )

    run(provider.forward(FakeRequest(headers={"host": "gw"})))

    assert "authorization" not in calls[0].headers


def test_forward_non_json_upstream_falls_back_to_detail(monkeypatch) -> None:
    upstream = httpx.Response(503, text="upstream boom", headers={"content-type": "text/plain"})
    patch_httpx(monkeypatch, response=upstream)
    provider = make_passthrough("rerank", endpoint="http://rr.invalid")

    resp = run(provider.forward(FakeRequest()))

    assert resp.status_code == 503
    assert json.loads(resp.body) == {"detail": "upstream boom"}


def test_forward_timeout_maps_to_504(monkeypatch) -> None:
    patch_httpx(monkeypatch, exc=httpx.TimeoutException("slow"))
    provider = make_passthrough("ocr", endpoint="http://ocr.invalid")

    with pytest.raises(Exception) as exc_info:
        run(provider.forward(FakeRequest()))
    assert getattr(exc_info.value, "status_code", None) == 504


def test_forward_request_error_maps_to_502(monkeypatch) -> None:
    patch_httpx(monkeypatch, exc=httpx.ConnectError("refused"))
    provider = make_passthrough("ocr", endpoint="http://ocr.invalid")

    with pytest.raises(Exception) as exc_info:
        run(provider.forward(FakeRequest()))
    assert getattr(exc_info.value, "status_code", None) == 502


def test_forward_missing_endpoint_returns_503(monkeypatch) -> None:
    patch_httpx(monkeypatch, response=httpx.Response(200, json={}))
    provider = make_passthrough("ocr", endpoint=None)

    with pytest.raises(Exception) as exc_info:
        run(provider.forward(FakeRequest()))
    assert getattr(exc_info.value, "status_code", None) == 503


# ---------------------------------------------------------------------------
# 3) Orchestrator segregation
# ---------------------------------------------------------------------------


def test_orchestrator_segregates_passthrough_from_chat_routing() -> None:
    from src.router.orchestrator import RouterOrchestrator

    config = RouterConfig(
        providers=[
            ProviderConfig(name="local", type="hosted_vllm", model="Qwen", settings={"endpoint": "http://x/v1"}),
            ProviderConfig(name="ocr-backend", type="ocr", model="ocr", settings={"endpoint": "http://o:8002"}),
        ],
        routing=RoutingConfig(policy="Balanced"),
        telemetry=TelemetryConfig(backend=TelemetryBackendType.MEMORY),
    )
    orch = RouterOrchestrator(config, telemetry=InMemoryTelemetry())
    run(orch.initialize())

    # Pass-through is reachable by service, never a chat-routing candidate.
    assert set(orch.passthrough_map) == {"ocr"}
    assert set(orch.provider_map) == {"local"}
    assert "ocr" not in orch.model_to_provider
    assert orch.passthrough_for("ocr") is orch.passthrough_map["ocr"]
    assert orch.passthrough_for("embeddings") is None


# ---------------------------------------------------------------------------
# 4) Generated routes via TestClient
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("service,spec", sorted(PASSTHROUGH_SERVICES.items()))
def test_generated_route_forwards(monkeypatch, service: str, spec) -> None:
    body = b"AUDIO" if spec.binary else json.dumps({"ok": service}).encode()
    ctype = "audio/mpeg" if spec.binary else "application/json"
    upstream = httpx.Response(200, content=body, headers={"content-type": ctype})
    patch_httpx(monkeypatch, response=upstream)

    router = PassthroughRouterStub({service: make_passthrough(service)})
    client = TestClient(build_app(router))

    resp = client.post(spec.route, content=b"{}", headers={"content-type": "application/json"})

    assert resp.status_code == 200
    if spec.binary:
        assert resp.content == b"AUDIO"
    else:
        assert resp.json() == {"ok": service}


def test_route_returns_503_when_service_not_configured() -> None:
    # Router has no pass-through providers registered.
    client = TestClient(build_app(PassthroughRouterStub({})))

    resp = client.post("/v1/ocr", json={"image_path": "/x"})

    assert resp.status_code == 503
    assert resp.json()["detail"] == "ocr service not configured"


def test_passthrough_providers_excluded_from_models() -> None:
    config = RouterConfig(
        providers=[
            ProviderConfig(name="local", type="hosted_vllm", model="Qwen/Qwen3.5-9B"),
            ProviderConfig(name="ocr-backend", type="ocr", model="ocr"),
            ProviderConfig(name="emb-backend", type="embeddings", model="bge-m3"),
        ],
        telemetry=TelemetryConfig(backend=TelemetryBackendType.MEMORY),
    )
    client = TestClient(build_app(PassthroughRouterStub({}), config=config))

    data = client.get("/v1/models").json()["data"]
    ids = {m["id"] for m in data}

    assert "Qwen/Qwen3.5-9B" in ids
    assert "auto" in ids
    # Pass-through backends are not chat models.
    assert "ocr" not in ids
    assert "bge-m3" not in ids


def test_passthrough_counts_against_concurrency_limit(monkeypatch) -> None:
    """A slow pass-through holding the only slot makes a second one 429."""
    started = threading.Event()
    release = threading.Event()

    class _BlockingProvider:
        async def forward(self, _request):
            started.set()
            await asyncio.to_thread(release.wait, 5)
            return JSONResponse({"ok": True})

    router = PassthroughRouterStub({"ocr": _BlockingProvider()})
    app = build_app(router, max_concurrency=1)

    failure_queue: queue.Queue[BaseException] = queue.Queue()

    def _hold_slot() -> None:
        try:
            with TestClient(app) as blocking_client:
                resp = blocking_client.post("/v1/ocr", json={})
                if resp.status_code != 200:
                    raise AssertionError(f"Unexpected status: {resp.status_code}")
        except BaseException as exc:  # pragma: no cover - propagated below
            failure_queue.put(exc)

    worker = threading.Thread(target=_hold_slot)
    worker.start()
    try:
        assert started.wait(timeout=5), "First pass-through never became active"

        with TestClient(app) as competing_client:
            resp = competing_client.post("/v1/ocr", json={})

        assert resp.status_code == 429
        assert resp.json() == {"detail": "Server busy: 1/1 concurrent requests. Retry later."}
    finally:
        release.set()
        worker.join(timeout=5)

    if not failure_queue.empty():
        raise failure_queue.get()
