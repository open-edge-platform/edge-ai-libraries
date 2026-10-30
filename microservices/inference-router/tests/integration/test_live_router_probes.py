# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""End-to-end probe tests against a running router, driven over HTTP.

Like the other integration suites, this talks to an **already-running** router
service (at ``GATEWAY_BASE_URL``, default ``http://127.0.0.1:8000``) — it does
*not* start its own. What it adds is **mock provider backends**: lightweight
threaded HTTP servers on their own free ports (so they never collide with a real
LLM backend) that serve a Prometheus ``/metrics`` body (what a probe scrapes) and
an OpenAI-compatible ``/v1/chat/completions`` that echoes the backend's identity
(so a routing decision is observable in the response).

Each test registers temporary providers (names prefixed ``itest_``) via the
providers API, pointed at those mocks, drives the probe lifecycle over HTTP, and
deletes everything it created on teardown. Nothing is asserted that a remote
client cannot observe — no router logs, no sink files — so the suite is portable.

Requirements (the suite auto-skips when unmet, see the ``reachable`` fixture):
  * a router reachable at ``GATEWAY_BASE_URL``,
  * that router can reach loopback mock servers on this host (e.g. it runs here,
    or with host networking), and runs code new enough that ``GET /v1/providers``
    reflects live probe metadata.

Covered cases:
  1. Zero-match and over-cardinality (``max_series``) regex extraction never crash
     the probe (observed behaviorally: the flood is capped, the service stays up).
  2. Enabling a probe surfaces its metric in ``GET /v1/providers/{name}`` and the
     spec round-trips; disabling it (lifecycle) makes the metric disappear.
  3. Each aggregation method publishes the numerically correct value.
  4. A publish ``prefix`` lands the metric in the right metadata namespace.
  5. A strategy keyed on a probe metric (``tpot_ms``), installed and activated via
     the strategy/policy/routing APIs (and restored afterward), makes ``auto``
     routing prefer the fastest mock.
  6. A probe whose endpoint is unreachable fails quietly without downing the service.
"""
from __future__ import annotations

import itertools
import json
import os
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable

import pytest
import requests


pytestmark = pytest.mark.integration

GATEWAY_BASE_URL = os.getenv("GATEWAY_BASE_URL", "http://127.0.0.1:8000").rstrip("/")

# Unique, collision-proof provider/strategy/policy names across runs on one host.
_SEQ = itertools.count()
_PREFIX = f"itest_{os.getpid()}"


def _name(role: str) -> str:
    return f"{_PREFIX}_{role}_{next(_SEQ)}"


# --------------------------------------------------------------------------- #
# Mock provider backend (separate port per instance)
# --------------------------------------------------------------------------- #

def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


class MockBackend:
    """A threaded OpenAI-compatible backend with a scrapeable ``/metrics`` body.

    ``metrics_text`` is mutable so a test can change what the probe sees. The chat
    endpoint echoes ``identity`` as the response ``model`` and message content, so
    the router's forwarded response reveals which backend served a routed request.
    """

    def __init__(self, identity: str, metrics_text: str = "") -> None:
        self.identity = identity
        self.metrics_text = metrics_text
        self.port = _free_port()
        backend = self

        class _Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args: Any) -> None:  # silence access logs
                pass

            def _send(self, code: int, body: bytes, content_type: str) -> None:
                self.send_response(code)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self) -> None:  # noqa: N802 - stdlib naming
                if self.path.rstrip("/").endswith("/metrics"):
                    self._send(200, backend.metrics_text.encode(), "text/plain")
                else:
                    self._send(404, b"not found", "text/plain")

            def do_POST(self) -> None:  # noqa: N802 - stdlib naming
                length = int(self.headers.get("Content-Length", 0))
                if length:
                    self.rfile.read(length)
                payload = {
                    "id": f"cmpl-{backend.identity}",
                    "object": "chat.completion",
                    "created": 1,
                    "model": backend.identity,
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": backend.identity},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                }
                self._send(200, json.dumps(payload).encode(), "application/json")

        self._httpd = ThreadingHTTPServer(("127.0.0.1", self.port), _Handler)

    def start(self) -> "MockBackend":
        threading.Thread(target=self._httpd.serve_forever, daemon=True).start()
        return self

    def stop(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()

    @property
    def chat_endpoint(self) -> str:
        return f"http://127.0.0.1:{self.port}/v1"

    @property
    def metrics_endpoint(self) -> str:
        return f"http://127.0.0.1:{self.port}/metrics"


# --------------------------------------------------------------------------- #
# Probe / provider payload builders
# --------------------------------------------------------------------------- #

def _probe_spec(
    name: str,
    metrics_endpoint: str,
    regex: str,
    *,
    publish: list[dict[str, Any]],
    method: str = "mean",
    window: int = 5,
    interval: float = 1,
    max_series: int = 200,
    enabled: bool = True,
) -> dict[str, Any]:
    return {
        "name": name,
        "enabled": enabled,
        "endpoint": metrics_endpoint,
        "interval": interval,
        "timeout": 5,
        "extract": [{"regex": regex}],
        "aggregate": {"window": window, "method": method},
        "max_series": max_series,
        "publish": publish,
    }


def _provider_settings(backend: MockBackend, probes: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "endpoint": backend.chat_endpoint,
        "timeout": 30.0,
        "auth": {"scheme": "none", "api_key": None, "custom_headers": {}},
        "probes": probes,
    }


def _wait_until(check: Callable[[], Any], timeout: float = 30, interval: float = 0.4) -> Any:
    """Poll ``check`` until it returns truthy or the timeout elapses."""
    deadline = time.monotonic() + timeout
    last: Any = None
    while time.monotonic() < deadline:
        try:
            last = check()
            if last:
                return last
        except (requests.RequestException, AssertionError, KeyError):
            pass
        time.sleep(interval)
    return last


# --------------------------------------------------------------------------- #
# Test lab: a thin client over the running router with full teardown
# --------------------------------------------------------------------------- #

class Lab:
    """Drives the running router's APIs and cleans up everything it creates."""

    def __init__(self, base: str) -> None:
        self.base = base
        self._backends: list[MockBackend] = []
        self._providers: list[str] = []
        self._strategies: list[str] = []
        self._policies: list[str] = []
        self._routing_restore: str | None = None  # original policy, if we changed it

    # ---- mock backends --------------------------------------------------- #

    def backend(self, identity: str, metrics_text: str = "") -> MockBackend:
        mock = MockBackend(identity, metrics_text).start()
        self._backends.append(mock)
        return mock

    # ---- providers ------------------------------------------------------- #

    def create_provider(
        self,
        backend: MockBackend,
        probes: list[dict[str, Any]],
        *,
        role: str = "p",
        labels: list[str] | None = None,
    ) -> str:
        name = _name(role)
        body = {
            "type": "hosted_vllm",
            "model": name,  # model == name so a direct chat (model=name) bypasses routing
            "enabled": True,
            "metadata": {"labels": labels or [name], "cost": 0},
            "settings": _provider_settings(backend, probes),
        }
        resp = requests.post(f"{self.base}/v1/providers/{name}", json=body, timeout=30)
        resp.raise_for_status()
        self._providers.append(name)
        return name

    def set_probes(self, name: str, backend: MockBackend, probes: list[dict[str, Any]]) -> None:
        resp = requests.post(
            f"{self.base}/v1/providers/{name}",
            json={"settings": _provider_settings(backend, probes)},
            timeout=30,
        )
        resp.raise_for_status()

    def provider(self, name: str) -> dict[str, Any]:
        resp = requests.get(f"{self.base}/v1/providers/{name}", timeout=10)
        resp.raise_for_status()
        return resp.json()

    def metadata(self, name: str) -> dict[str, Any]:
        return self.provider(name)["metadata"]

    def performance(self, name: str) -> dict[str, Any]:
        return self.metadata(name).get("performance") or {}

    def chat(self, model: str, timeout: float = 30) -> requests.Response:
        return requests.post(
            f"{self.base}/v1/chat/completions",
            json={"model": model, "messages": [{"role": "user", "content": "hi"}]},
            timeout=timeout,
        )

    # ---- routing (strategy + policy + active policy), restored on teardown - #

    def activate_strategy(self, selector: dict[str, Any], sort: list[dict[str, Any]]) -> None:
        """Create a strategy + policy and make it the active routing policy.

        Skips the test if the router rejects RSD edits (e.g. no workspace copy of
        strategy.yaml/policy.yaml to override).
        """
        strategy = _name("strat")
        policy = _name("pol")
        strat_body = {"description": "itest", "rules": [], "provider_selector": selector, "sort": sort}
        resp = requests.post(f"{self.base}/v1/strategies/{strategy}", json=strat_body, timeout=30)
        if resp.status_code != 200:
            pytest.skip(f"router rejected strategy create ({resp.status_code}): {resp.text}")
        self._strategies.append(strategy)

        pol_body = {"criterion": "FirstMatch", "strategies": [strategy]}
        resp = requests.post(f"{self.base}/v1/policies/{policy}", json=pol_body, timeout=30)
        if resp.status_code != 200:
            pytest.skip(f"router rejected policy create ({resp.status_code}): {resp.text}")
        self._policies.append(policy)

        original = requests.get(f"{self.base}/v1/routing", timeout=10).json().get("policy")
        self._routing_restore = original or ""
        resp = requests.post(f"{self.base}/v1/routing", json={"policy": policy}, timeout=30)
        resp.raise_for_status()

    # ---- teardown -------------------------------------------------------- #

    def close(self) -> None:
        # Restore global routing FIRST so nothing references a to-be-deleted RSD.
        if self._routing_restore is not None:
            _safe(lambda: requests.post(
                f"{self.base}/v1/routing", json={"policy": self._routing_restore}, timeout=30
            ))
        for policy in self._policies:
            _safe(lambda p=policy: requests.delete(f"{self.base}/v1/policies/{p}", timeout=30))
        for strategy in self._strategies:
            _safe(lambda s=strategy: requests.delete(f"{self.base}/v1/strategies/{s}", timeout=30))
        for name in self._providers:
            _safe(lambda n=name: requests.delete(f"{self.base}/v1/providers/{n}", timeout=30))
        for mock in self._backends:
            _safe(mock.stop)


def _safe(fn: Callable[[], Any]) -> None:
    try:
        fn()
    except Exception:  # noqa: BLE001 - teardown must never mask a test failure
        pass


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

@pytest.fixture(scope="module")
def gateway_base() -> str:
    """Base URL of the running router, or skip when it is unreachable."""
    try:
        requests.get(f"{GATEWAY_BASE_URL}/health", timeout=5).raise_for_status()
    except requests.RequestException as exc:
        pytest.skip(f"router not reachable at {GATEWAY_BASE_URL}: {exc}")
    return GATEWAY_BASE_URL


@pytest.fixture(scope="module")
def reachable(gateway_base: str) -> str:
    """One-time end-to-end check that the probe suite can run here at all.

    Registers a throwaway provider whose probe scrapes an in-test mock, and waits
    for the value to surface in ``GET /v1/providers``. This simultaneously proves
    the router is reachable, that it can reach loopback mock servers on this host,
    and that it reflects live probe metadata — skipping the whole module with a
    clear reason if any of those does not hold.
    """
    lab = Lab(gateway_base)
    try:
        mock = lab.backend("reach", 'vllm:probe_ping{m="x"} 1.0\n')
        name = lab.create_provider(
            mock,
            [
                _probe_spec(
                    "reach",
                    mock.metrics_endpoint,
                    r"vllm:(probe_ping)\{[^}]*\}\s+([0-9.eE+-]+)",
                    publish=[{"to": "metadata", "prefix": "performance"}],
                )
            ],
        )
        ok = _wait_until(lambda: lab.performance(name).get("probe_ping") == 1.0, timeout=25)
        if not ok:
            pytest.skip(
                "router did not reflect an in-test probe value; the probe suite needs a "
                "router running on this host (able to reach loopback mocks) built from "
                "current code (GET /v1/providers reflects live probe metadata)"
            )
    finally:
        lab.close()
    return gateway_base


@pytest.fixture
def lab(reachable: str):
    """A fresh :class:`Lab` bound to the running router, torn down after the test."""
    instance = Lab(reachable)
    try:
        yield instance
    finally:
        instance.close()


# --------------------------------------------------------------------------- #
# 1. Zero / too-many field extraction — never crashes (behavioral)
# --------------------------------------------------------------------------- #

def test_regex_zero_and_too_many_fields_never_crash(lab: Lab) -> None:
    """A no-match probe publishes nothing; a flood is capped at max_series."""
    zero_mock = lab.backend("zero", 'vllm:something_else{m="x"} 1.0\n')
    flood_mock = lab.backend("flood", "".join(f"metric_{i} {float(i)}\n" for i in range(60)))

    zero = lab.create_provider(
        zero_mock,
        [
            _probe_spec(
                "zero",
                zero_mock.metrics_endpoint,
                r"vllm:(this_name_never_appears)\{[^}]*\}\s+([0-9.eE+-]+)",
                publish=[{"to": "metadata", "prefix": "performance"}],
            )
        ],
        role="zero",
    )
    flood = lab.create_provider(
        flood_mock,
        [
            _probe_spec(
                "flood",
                flood_mock.metrics_endpoint,
                r"([a-z0-9_]+)\s+([0-9.eE+-]+)",  # one series per line
                publish=[{"to": "metadata", "prefix": "performance"}],
                max_series=10,  # 60 series >> cap
            )
        ],
        role="flood",
    )

    # The flood probe populated metadata but stayed bounded by max_series.
    assert _wait_until(lambda: 0 < len(lab.performance(flood)) <= 10), lab.performance(flood)

    # The zero-match probe is a graceful miss: it never publishes a series, and the
    # service keeps serving the provider API and chat for both providers.
    assert not lab.performance(zero)
    assert requests.get(f"{lab.base}/v1/providers/{zero}", timeout=5).ok
    chat = lab.chat(flood)  # direct (model == provider name)
    assert chat.status_code == 200
    assert chat.json()["choices"][0]["message"]["content"] == flood_mock.identity


# --------------------------------------------------------------------------- #
# 2. Enable → metric appears + spec round-trips; disable → metric disappears
# --------------------------------------------------------------------------- #

def test_probe_enable_disable_lifecycle_via_api(lab: Lab) -> None:
    """Enabling a probe surfaces its metric and spec; disabling removes the metric."""
    mock = lab.backend("svc", 'vllm:num_requests_waiting{m="x"} 7.0\n')
    regex = r"vllm:(num_requests_waiting)\{[^}]*\}\s+([0-9.eE+-]+)"

    # Start with no probe — metric absent.
    name = lab.create_provider(mock, probes=[], role="svc")
    assert "num_requests_waiting" not in json.dumps(lab.metadata(name))

    # Enable a probe → its value appears in GET metadata...
    probe = _probe_spec("perf", mock.metrics_endpoint, regex,
                        publish=[{"to": "metadata", "prefix": "performance"}])
    lab.set_probes(name, mock, [probe])
    assert _wait_until(lambda: lab.performance(name).get("num_requests_waiting") == 7.0), (
        lab.performance(name)
    )

    # ...and the spec itself round-trips through the providers API.
    persisted = next((p for p in lab.provider(name)["settings"]["probes"] if p["name"] == "perf"), None)
    assert persisted is not None and persisted["endpoint"] == mock.metrics_endpoint
    assert persisted["extract"][0]["regex"] == regex

    # Disable the probe → the rebuilt provider no longer carries the metric.
    lab.set_probes(name, mock, [{**probe, "enabled": False}])
    assert _wait_until(lambda: "num_requests_waiting" not in lab.performance(name)), (
        lab.performance(name)
    )


# --------------------------------------------------------------------------- #
# 3. Aggregation methods publish the correct number
# --------------------------------------------------------------------------- #

def test_aggregation_methods_publish_correct_value(lab: Lab) -> None:
    """With a constant input, every method yields that constant (stdev → 0)."""
    const = 42.0
    methods = ["latest", "mean", "median", "p50", "p90", "p95", "p99", "ewma", "min", "max"]
    mock = lab.backend("agg", f'vllm:val{{m="x"}} {const}\n')

    probes = [
        _probe_spec(
            f"agg_{method}",
            mock.metrics_endpoint,
            r"vllm:(val)\{[^}]*\}\s+([0-9.eE+-]+)",
            method=method,
            publish=[{"to": "metadata", "prefix": f"attributes.{method}"}],
        )
        for method in [*methods, "stdev"]
    ]
    name = lab.create_provider(mock, probes, role="agg")

    def _all_present() -> bool:
        md = lab.metadata(name)
        return all(method in md for method in [*methods, "stdev"])

    assert _wait_until(_all_present), lab.metadata(name)

    md = lab.metadata(name)
    for method in methods:
        assert md[method]["val"] == pytest.approx(const), (method, md[method])
    assert md["stdev"]["val"] == pytest.approx(0.0)  # constant series → zero spread


def test_aggregation_math_is_distinct_and_correct() -> None:
    """The same code the live probe uses computes each method correctly.

    A pure-logic check (no router) that proves the methods are numerically
    *distinct* on a varying sample set, complementing the constant-input test.
    """
    from src.providers.probes.aggregator import MetricAggregator

    samples = [10.0, 20.0, 30.0, 40.0, 50.0]
    expected = {
        "latest": 50.0, "mean": 30.0, "median": 30.0, "p50": 30.0,
        "min": 10.0, "max": 50.0,
        "p90": 46.0,  # linear interpolation: 0.9*(5-1)=3.6 → 40 + 0.6*(50-40)
    }
    for method, want in expected.items():
        agg = MetricAggregator(window=10, method=method, max_series=10)
        for value in samples:
            agg.add({"m": value})
        assert agg.values()["m"] == pytest.approx(want), method


# --------------------------------------------------------------------------- #
# 4. Publish prefix routes the metric to the right metadata namespace
# --------------------------------------------------------------------------- #

def test_publish_prefix_targets_namespace(lab: Lab) -> None:
    """One probe, three prefixes → the metric lands in three metadata locations."""
    mock = lab.backend("pfx", 'vllm:queue_depth{m="x"} 3.0\n')
    probe = _probe_spec(
        "pfx",
        mock.metrics_endpoint,
        r"vllm:(queue_depth)\{[^}]*\}\s+([0-9.eE+-]+)",
        publish=[
            {"to": "metadata", "prefix": "performance"},       # typed field
            {"to": "metadata", "prefix": "capability"},        # typed field
            {"to": "metadata", "prefix": "attributes.probe"},  # free-form → probe.*
        ],
    )
    name = lab.create_provider(mock, [probe], role="pfx")

    assert _wait_until(lambda: "queue_depth" in lab.performance(name)), lab.metadata(name)

    md = lab.metadata(name)
    assert md["performance"]["queue_depth"] == 3.0
    assert md["capability"]["queue_depth"] == 3.0
    # ``attributes.probe`` surfaces as a top-level ``probe`` key in to_dict().
    assert md["probe"]["queue_depth"] == 3.0


# --------------------------------------------------------------------------- #
# 5. Routing follows a probe-published metric (strategy installed via API)
# --------------------------------------------------------------------------- #

def test_routing_strategy_follows_probe_metric(lab: Lab) -> None:
    """A strategy keyed on probe ``tpot_ms`` routes ``auto`` to the fastest mock.

    The strategy filters by a label unique to these test providers, so it never
    competes with the router's real providers; it drops the over-threshold mock
    and sorts the rest ascending. Providers are created slow→fast so the winner is
    not simply the first one.
    """
    label = _PREFIX + "_tpot"

    def _tpot_provider(value: float, role: str) -> str:
        mock = lab.backend(role, f'vllm:tpot_ms{{m="x"}} {value}\n')
        probe = _probe_spec(
            "perf",
            mock.metrics_endpoint,
            r"vllm:(tpot_ms)\{[^}]*\}\s+([0-9.eE+-]+)",
            method="latest",
            publish=[{"to": "metadata", "prefix": "performance"}],
        )
        return lab.create_provider(mock, [probe], role=role, labels=[label, role])

    slow = _tpot_provider(500.0, "slow")
    mid = _tpot_provider(40.0, "mid")
    fast = _tpot_provider(10.0, "fast")

    # Only providers carrying our label are eligible; drop tpot_ms > 100, sort asc.
    lab.activate_strategy(
        selector={"label": label, "performance": {"tpot_ms": 100}},
        sort=[{"provider_attribute": "performance.tpot_ms", "descending": False}],
    )

    # Wait until all three mocks' tpot_ms has been scraped into routing metadata.
    assert _wait_until(
        lambda: all(lab.performance(n).get("tpot_ms") is not None for n in (slow, mid, fast)),
        timeout=30,
    ), "probes never populated tpot_ms"

    # "auto" invokes the decision engine; it must pick the fastest eligible mock.
    response = lab.chat("auto")
    assert response.status_code == 200, response.text
    chosen = response.json()["choices"][0]["message"]["content"]
    assert chosen == "fast", f"routing picked {chosen!r}, expected 'fast'"

    # The over-threshold mock is only filtered for strategy routing; a direct call
    # by name still reaches it (the filter is strategy-scoped, not a disable).
    direct = lab.chat(slow)
    assert direct.status_code == 200
    assert direct.json()["choices"][0]["message"]["content"] == "slow"


# --------------------------------------------------------------------------- #
# 6. A probe with an unreachable endpoint never crashes the service
# --------------------------------------------------------------------------- #

def test_probe_survives_unreachable_endpoint(lab: Lab) -> None:
    """A probe pointed at a dead port fails quietly; the provider stays serviceable."""
    mock = lab.backend("up", "")  # chat works; metrics endpoint is intentionally wrong
    dead_endpoint = f"http://127.0.0.1:{_free_port()}/metrics"  # nothing listens there

    probe = _probe_spec(
        "perf",
        dead_endpoint,
        r"vllm:(num_requests_waiting)\{[^}]*\}\s+([0-9.eE+-]+)",
        publish=[{"to": "metadata", "prefix": "performance"}],
    )
    name = lab.create_provider(mock, [probe], role="up")

    time.sleep(3)  # a few tick intervals against the dead endpoint
    assert requests.get(f"{lab.base}/health", timeout=5).ok
    assert not lab.performance(name)  # nothing published
    chat = lab.chat(name)  # provider still serves requests
    assert chat.status_code == 200
    assert chat.json()["choices"][0]["message"]["content"] == "up"
