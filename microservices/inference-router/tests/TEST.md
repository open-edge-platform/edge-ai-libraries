# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

## Test Guide

This repository uses two test layers:

- `unit/`: deterministic, in-process tests that do not require a running gateway.
- `integration/`: end-to-end validation over HTTP against an externally running
  gateway. The provider-probe suite additionally stands up its own mock *backends*
  (not its own router), so it needs no real LLM — see
  [Provider Probes](#provider-probes).

Unless you are specifically validating deployment or backend connectivity, start with the unit suites.

## Prerequisites

Run commands from the repository root:

```bash
cd inference-router
```

Prepare a Python environment with the required test dependencies before running the commands below. The project virtual environment is not created automatically, so you may need to create or activate one first and install the required packages.

Example environment check:

```bash
pytest --version
```

## Quick Start

Run all non-live unit tests:

```bash
pytest tests/unit
```

Run the router API contract suites only:

```bash
pytest \
  tests/unit/test_api_protocol_contract.py \
  tests/unit/test_api_validation_and_errors.py \
  tests/unit/test_api_behavior_contract.py
```

Run the in-process app wiring suite:

```bash
pytest tests/unit/test_chat_endpoint.py
```

Collect the live gateway suites without executing them:

```bash
pytest --collect-only tests/integration
```

## Unit Test Suites

These tests run in-process with `fastapi.testclient.TestClient` and stubbed router objects. They validate the gateway API layer without requiring a server process.

### Router API Contract

- `tests/unit/test_api_protocol_contract.py`
  Coverage: root and health endpoints, `/v1/models`, `/v1/metrics`, `/v1/metrics/reset`, request-id rewriting, SSE streaming protocol, metrics aggregation, and response shape guarantees.

- `tests/unit/test_api_validation_and_errors.py`
  Coverage: invalid request payloads, 422 validation responses, 400 routing errors, 500 internal failures, 503 uninitialized-state failures, streaming error chunks, and 429 concurrency enforcement.

- `tests/unit/test_api_behavior_contract.py`
  Coverage: request forwarding semantics, multi-turn payload preservation, tool-call pass-through, reasoning-content pass-through, streaming tool-call deltas, direct model-selection metrics, and parallel request isolation.

### Routing Logic

- `tests/unit/test_decision_policy.py`
  Coverage: decision-policy loading, policy ordering, and rule-combination behavior in the decision engine.

- `tests/unit/test_strategy_executor.py`
  Coverage: strategy parsing, rule binding, candidate filtering, provider ranking, and invalid strategy configuration handling.

### Plugin Layer

- `tests/unit/test_plugins.py`
  Coverage: plugin registration, trigger ordering, per-plugin schema validation, and invalid plugin configuration rejection.

### Dynamic Configuration

These suites cover the runtime configuration APIs (`src/api/v1/config.py`, `src/api/v1/plugin.py`, `src/api/v1/_config_runtime.py`), which apply changes to both the live runtime (router, plugin manager, telemetry) and the on-disk `config.yaml`.

- `tests/unit/test_config_endpoint.py`
  Coverage: `GET /v1/config` returning redacted secrets while keeping API keys redacted in the response.

- `tests/unit/test_plugin_endpoint.py`
  Coverage: plugin listing (including disabled entries), create/update/delete round-trips that persist to `config.yaml` and update the runtime, trigger moves, and 404 handling. Also guards the persistence invariants:
  - env-var placeholders (e.g. `api_key: ${SECRET_KEY}`) are preserved in the file and the resolved secret never reaches disk;
  - writes are atomic and leave no stray `.tmp` file behind.

  Additionally covers the node registry (`GET /v1/plugins/nodes`,
  `GET /v1/plugins/{node}`) and the per-instance view/reset surface: the
  instance `GET /v1/plugins/{node}/{name}` folding a live plugin's `describe()`
  metrics into the payload, `POST /v1/plugins/{node}/{name}/reset` zeroing them,
  the node-level `POST /v1/plugins/{node}/reset`, `404` for an unloaded
  instance or unregistered node, and `400` when a plugin does not support reset.

### App Wiring

- `tests/unit/test_chat_endpoint.py`
  Coverage: in-process app and router wiring, endpoint smoke coverage through a real `RouterOrchestrator` initialization path, and plugin HTTP endpoint checks.

### Compressor (optional dependency)

These two suites require the optional `adaptive-token-compressor` library:

- `tests/unit/test_token_accounting.py`
  Coverage: baseline token accounting, and byte-for-byte parity between the
  router's local token counters and the vendored library counters.

- `tests/unit/test_compressor_plugins.py`
  Coverage: the `compressor` plugin layer — registration, per-type settings
  validation, the request→compress→apply flow, trigger placement, error
  containment, and per-instance / cross-instance metrics.

Both files are marked with the `compressor` marker and begin with
`pytest.importorskip("adaptive_token_compressor")`. This means:

- If the library **is not installed**, both suites are skipped at collection
  time (reported as `skipped`, not errored), so `pytest tests/unit` stays green.
- If the library **is installed**, they run normally.

Run them only when the dependency is present (select by marker):

```bash
pytest -m compressor
```

Exclude them explicitly (e.g. in a CI job without the library):

```bash
pytest tests/unit -m "not compressor"
```

Run just these two files directly (they self-skip if the library is missing):

```bash
pytest tests/unit/test_token_accounting.py tests/unit/test_compressor_plugins.py
```

Install the dependency to enable them:

```bash
pip install adaptive-token-compressor
```

### Shared Support

- `tests/unit/_api_contract_support.py`
  Shared harness for the in-process router API suites. This is support code, not a standalone test file.

## Integration Test Suites

These tests are grouped under `tests/integration/` and are auto-marked as `integration` by `tests/integration/conftest.py`. They all talk to an externally running gateway over HTTP — the **Provider Probes** suite additionally stands up its own mock *backends* (never its own router), so the running gateway has something to probe and route to without a real LLM.

### Live Gateway Validation

- `tests/integration/test_router_gateway.py`
  Coverage: router health, model listing, routed and direct requests, streaming vs non-streaming behavior, token/metrics endpoints, invalid-model handling, stats reset, and concurrent request behavior against a running gateway.

- `tests/integration/test_gateway_request_types.py`
  Coverage: request-shape compatibility, tool-calling variants, structured outputs, streaming variants, generation parameters, large payloads, and tool-definition variants against a running gateway.

### Provider Probes

- `tests/integration/test_live_router_probes.py`
  The single home for provider-probe end-to-end coverage, driven entirely over
  HTTP against the **running gateway** (like the other integration suites). Instead
  of requiring a real LLM, each test stands up **mock provider backends** —
  lightweight threaded HTTP servers, each on its own free port (so they never
  collide with a real backend) — that serve a Prometheus `/metrics` body (what a
  probe scrapes) and an OpenAI-compatible `/v1/chat/completions` that echoes the
  backend's identity (so a routing decision is visible in the response).

  Each test registers temporary providers (names prefixed `itest_`) pointed at
  those mocks via the providers API, drives the probe lifecycle over HTTP, and
  deletes everything it created on teardown (providers, and — for the routing test
  — a temporary strategy/policy with the original routing restored). Nothing is
  asserted that a remote client cannot observe (no router logs, no sink files), so
  the suite is portable.

  Requirements — the suite auto-skips (with a single up-front reachability check)
  unless all hold:
  - a gateway is reachable at `GATEWAY_BASE_URL`;
  - it can reach **loopback mock servers on this host** (i.e. it runs on this host,
    e.g. natively or with host networking);
  - it runs code new enough that `GET /v1/providers` reflects live probe metadata.

  The one exception is a pure-logic aggregation-math test, which needs no gateway
  and always runs.

  Coverage:
  - zero-match and over-cardinality (`max_series`) regex extraction never crash
    the probe (observed behaviorally: the flood is capped, the service stays up);
  - enabling a probe via the providers API surfaces its metric in
    `GET /v1/providers/{name}` metadata and round-trips the spec; disabling it
    (lifecycle) removes the metric;
  - every aggregation method (`latest/mean/median/p50/p90/p95/p99/ewma/min/max/stdev`)
    publishes the numerically correct value;
  - publish `prefix` routes a metric into the right metadata namespace
    (`performance.*`, `capability.*`, free-form `probe.*`);
  - a strategy keyed on a probe metric (`tpot_ms`) — installed and activated via
    the strategy/policy/routing APIs, then restored — makes `auto` routing prefer
    the fastest mock;
  - a probe with an unreachable endpoint fails quietly without downing the service.

  > **Note:** the routing test briefly changes the gateway's **active routing
  > policy** (restored on teardown), so prefer running this suite against a dev
  > gateway rather than one serving production traffic.

  Run it against a gateway on this host:

  ```bash
  GATEWAY_BASE_URL=http://127.0.0.1:8000 \
  pytest tests/integration/test_live_router_probes.py
  ```

## Running Integration Tests

All integration suites require a running gateway. The **Live Gateway Validation** suites expect the API endpoints used by `tests/integration/test_client.py`; the **Provider Probes** suite additionally requires that the gateway run on this host so it can reach the in-test mock backends on loopback (see above).

Default base URL:

```text
http://127.0.0.1:8000
```

Override it with `GATEWAY_BASE_URL` if needed:

```bash
GATEWAY_BASE_URL=http://127.0.0.1:8000 \
pytest tests/integration/test_router_gateway.py
```

Run all integration tests:

```bash
pytest tests/integration
```

Run only the live gateway validation suites:

```bash
pytest \
  tests/integration/test_router_gateway.py \
  tests/integration/test_gateway_request_types.py
```

## Useful Patterns

Run only unit tests by directory:

```bash
pytest tests/unit
```

Run only integration tests by marker:

```bash
pytest -m integration tests/integration
```

Run a single test function:

```bash
pytest tests/unit/test_api_validation_and_errors.py::test_non_streaming_routing_error_returns_http_400
```

## Notes

- The unit API suites are the primary fast feedback path for router API correctness.
- The integration suites are the deployment-facing validation path and should be used when checking real routing behavior, backend interoperability, or containerized startup.
- Current test runs may show existing warnings from the local dependency stack, including the `asyncio_mode` config warning and the `TestClient` deprecation warning.