<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Testing Guide

This guide covers how to run tests for Metrics Manager.

## Prerequisites

- Service is running: `docker compose up -d`
- Or local setup with uvicorn and Telegraf running
- `curl` or similar HTTP client

---

## Running Tests via Docker

### Build Test Image

```bash
docker compose build
```

### Run All Tests

```bash
docker compose --profile test run --rm metrics-manager-test
```

All collected tests should pass; optional checks report their missing prerequisites
as skips.

### Run with Coverage Report

```bash
docker compose --profile test run --rm metrics-manager-test \
  python -m pytest tests/ -v --cov=app --cov-report=term-missing
```

---

## Running Tests Locally

### Prerequisites

- **Python 3.10+** (`python3 --version`)
- **uv** (fast package manager): `pip install uv`
- **Telegraf** installed and running on the system

### Setup

1. **Create a virtual environment:**

   ```bash
   uv venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

2. **Install test dependencies:**

   ```bash
   uv sync --group test
   ```

3. **Configure the environment:**

   ```bash
   cp .env.example .env
   ```

   Edit `.env` to point to your local Telegraf:

   ```bash
   TELEGRAF_PORT=9273
   TELEGRAF_HTTP_ENDPOINT=http://localhost:8186/write
   PROMETHEUS_TELEGRAF_ENDPOINT=http://localhost:9273
   ```

4. **For manual smoke tests, start the Docker telemetry backend:**

   ```bash
   docker compose up -d metrics-manager
   ```

   The root Telegraf configuration uses paths and native collectors installed in
   the image; it is not a standalone host configuration.

### Run Tests

```bash
# All tests
pytest

# Verbose output
pytest -v

# With coverage report
pytest --cov=app --cov-report=html

# Run specific test file
pytest tests/test_models.py -v
```

---

## Test Categories

| Test File                      | Description                                                                |
| ------------------------------ | -------------------------------------------------------------------------- |
| `test_models.py`               | Pydantic models: Metric, SimpleMetric, MetricsBatch, InfluxDB/OTLP parsing |
| `test_store.py`                | MetricsStore CRUD, persistence, cleanup, eviction, statistics              |
| `test_routes.py`               | REST API endpoints: health, ingestion, queries, Prometheus                 |
| `test_settings.py`             | Pydantic Settings loading, environment variables overrides, validation     |
| `test_logging_config.py`       | Structured logging setup (JSON and text formats)                           |
| `test_main.py`                 | FastAPI middleware, lifespan, correlation ID handling                      |
| `test_metrics.py`              | Internal service metrics counters and uptime                               |
| `test_rate_limit.py`           | IP-based rate limiting middleware                                          |
| `test_sse.py`                  | SSE endpoint `/metrics/stream`: streaming, parsing, errors                 |
| `test_telegraf_integration.py` | Native collector wiring, Telegraf configuration and custom metrics        |
| `test_docker_collectors.py`    | Optional collector selection, validation and mounted configuration        |
| `test_telemetry_selection.py`  | Real Telegraf filtering of storage, network and process fixtures           |
| `test_compose_profiles.py`    | Default bridge and opt-in host-NIC profiles                                |
| `test_env_example.py`         | Documented Docker configuration defaults                                  |
| `test_versions.py`            | Version mirrors, pinned dependencies and Docker build structure            |

---

## Smoke Tests (Manual Testing)

After starting the service with `docker compose up`, verify all endpoints:

### Test 1: Simple JSON Metric

```bash
curl -X POST http://localhost:9090/api/v1/metrics/simple \
  -H "Content-Type: application/json" \
  -d '{"name": "test_metric", "value": 123.45}'

# Verify
curl -s http://localhost:9090/api/v1/metrics/latest | grep -i "test_metric"
curl -s http://localhost:9090/metrics | grep "test_metric"
```

### Test 2: JSON Batch with Tags

```bash
curl -X POST http://localhost:9090/api/v1/metrics \
  -H "Content-Type: application/json" \
  -d '{
    "metrics": [
      {"name": "cpu_test", "tags": {"host": "test-server"}, "fields": {"usage": 55.5}},
      {"name": "memory_test", "tags": {"host": "test-server"}, "fields": {"used_mb": 4096}}
    ]
  }'

# Verify
curl -s http://localhost:9090/api/v1/metrics/latest | jq '.metrics | keys'
```

### Test 3: InfluxDB Line Protocol

```bash
curl -X POST http://localhost:9090/api/v1/metrics/influx \
  -H "Content-Type: text/plain" \
  -d 'influx_test,host=myhost,env=test value=99.9'

# Verify
curl -s http://localhost:9090/api/v1/metrics/latest | grep -i "influx_test"
```

### Test 4: Direct to Telegraf HTTP Listener

```bash
curl -X POST http://localhost:8186/write \
  -H "Content-Type: text/plain" \
  -d 'telegraf_direct,source=curl temperature=25.5'

# Verify
curl -s http://localhost:9273/metrics | grep "telegraf_direct"
```

### Test 5: OpenTelemetry (OTLP)

```bash
curl -X POST http://localhost:9090/api/v1/metrics/otlp \
  -H "Content-Type: application/json" \
  -d '{
    "resourceMetrics": [{
      "resource": {"attributes": [{"key": "service.name", "value": {"stringValue": "test-service"}}]},
      "scopeMetrics": [{
        "metrics": [{
          "name": "otlp_test_metric",
          "gauge": {"dataPoints": [{"asDouble": 77.7, "attributes": []}]}
        }]
      }]
    }]
  }'

# Verify
curl -s http://localhost:9090/api/v1/metrics/latest | grep -i "otlp_test"
```

### Test 6: SSE Real-time Streaming

```bash
# Terminal 1: Connect to SSE stream
curl -N -H "Accept: text/event-stream" http://localhost:9090/metrics/stream

# Terminal 2: Push a metric
curl -X POST http://localhost:9090/api/v1/metrics/simple \
  -H "Content-Type: application/json" \
  -d '{"name": "realtime_test", "value": 42}'

# Terminal 1 should show the metric in the next SSE event (~500ms)
# Or open http://localhost:9090/metrics/stream in a browser
```

### Test 7: Full Health Check

```bash
echo "=== Health ===" && curl -s http://localhost:9090/health | jq .
echo "=== Detailed ===" && curl -s http://localhost:9090/api/health | jq .
echo "=== Stats ===" && curl -s http://localhost:9090/api/v1/stats | jq .
echo "=== Telegraf ===" && curl -s http://localhost:9273/metrics | head -20
```

---

## Expected Test Output

```
========================= test session starts ==========================
tests/test_settings.py::...              PASSED
tests/test_logging_config.py::...        PASSED
tests/test_main.py::...                  PASSED
tests/test_models.py::...                PASSED
tests/test_store.py::...                 PASSED
tests/test_routes.py::...                PASSED
tests/test_metrics.py::...               PASSED
tests/test_rate_limit.py::...            PASSED
tests/test_sse.py::...                   PASSED
tests/test_telegraf_integration.py::...  PASSED
tests/test_docker_collectors.py::...     PASSED
tests/test_telemetry_selection.py::...   PASSED
```

The real Telegraf selection checks require the binary pinned in `versions.env`.
Set its absolute path explicitly; otherwise those checks are skipped:

```bash
TELEGRAF_TEST_BINARY=/absolute/path/to/telegraf \
  .venv/bin/pytest tests/test_telemetry_selection.py -v
```

---

## Native collector build and tests

The Go module in `native/` contains six standalone collectors:

| Command | Data source |
|---------|-------------|
| `mm-plugin-cpu` | CPU topology, frequency and utilization from procfs/sysfs |
| `mm-plugin-gpu` | GPU and optional per-process telemetry from a qmassa JSON stream |
| `mm-plugin-npu` | Intel NPU PMT telemetry and sysfs |
| `mm-plugin-proc` | Process CPU and memory usage from procfs |
| `mm-plugin-membw` | Memory-controller performance counters, with multi-socket affinity |
| `mm-plugin-rapl` | Package/platform energy counters exposed through powercap |

Collectors emit InfluxDB line protocol to stdout by default. The shared `-out`
option also supports a Unix stream socket for Telegraf's `socket_listener`.
Native measurements use base units such as Hz, bytes, bytes per second and
watts; percentages remain percentages.

Build and test the module independently of the service image or Debian package.
From `microservices/metrics-manager`, run on a Linux host with Docker:

```bash
. ./versions.env
docker run --rm --cap-drop ALL --security-opt no-new-privileges \
  --user "$(id -u):$(id -g)" \
  -e HTTP_PROXY -e HTTPS_PROXY -e NO_PROXY \
  -e http_proxy -e https_proxy -e no_proxy \
  -e GOCACHE=/tmp/gocache -e GOMODCACHE=/tmp/gomodcache \
  -e GOTOOLCHAIN=local -e GOFLAGS=-mod=readonly \
  -v "$PWD/native:/src:ro" -w /src "$GO_IMAGE" \
  sh -ec 'go test -race ./...; go vet ./...; CGO_ENABLED=0 go build ./cmd/...'
```

`versions.env` pins the compiler image by digest; `go.mod` declares the minimum
language version and module dependency. The command downloads that dependency
into the disposable container and leaves no build outputs in the checkout.
Unit tests use synthetic kernel files, qmassa fixtures and mocked performance
counters; they do not require GPU/NPU devices or privileged hardware access.
Passing these tests does not replace real-hardware validation of each collector.

### Terminal dashboard tests

The same Go test command also covers the Prometheus parser, HTTP poller and
terminal dashboard: responsive layouts, process limits/CPU modes, thresholds,
alert lifecycles, chart history, missing data, and network/storage counter rates.
Configuration examples are checked against built-in defaults.
Linux CLI regressions run the real entry point in a pseudo-terminal and verify
clean SIGINT/SIGTERM exits, restored terminal attributes and alternate-screen
cleanup.

Build the standalone dashboard using the
[terminal guide](./terminal-dashboard.md#build-and-start). Check `--help`,
`--version` and `-once` output, then exercise all four tabs and resize a real
terminal across single-, two- and three-column layouts. Verify that the terminal
is restored after quitting or interrupting the process. A one-frame rendering
does not test keyboard interaction or accumulated history.

## Release validation scope

Build both image variants with explicit `INSTALL_OPENVINO` values and distinct
tags, as described in the [build guide](./build-from-source.md). For each image,
check startup, the reported version, tagged metric ingestion through the API
to Telegraf's Prometheus endpoint, core CPU/memory/process series, and graceful
shutdown. Allow time for at least two collection intervals before checking
rate-based metrics.

Unit tests and container smoke tests do not prove that host GPU, NPU, power or
memory-bandwidth counters are accessible. Validate those collectors on the
intended hardware with the documented device access and permissions. Likewise,
an OpenVINO import or CPU device check does not validate GPU/NPU inference.

## Isolated Debian package tests

Build the package using `./native/build.sh`. From the component directory, run
both scenarios in separate disposable Ubuntu containers:

```bash
(
set -e
for scenario in fresh upgrade; do
  docker run --rm \
    --cap-drop ALL \
    --cap-add CHOWN --cap-add DAC_OVERRIDE --cap-add FOWNER \
    --cap-add SETUID --cap-add SETGID \
    --security-opt no-new-privileges \
    --cpus 2 --memory 2g \
    -e http_proxy -e https_proxy -e HTTP_PROXY -e HTTPS_PROXY \
    -e no_proxy -e NO_PROXY \
    -e DEBIAN_FRONTEND=noninteractive \
    -e METRICS_MANAGER_PACKAGE_TEST=1 \
    -v "$PWD/native/packaging/dist/metrics-manager_2026.3.0_amd64.deb:/packages/metrics-manager.deb:ro" \
    -v "$PWD/native/tests/package-install-test.sh:/tests/package-install-test.sh:ro" \
    ubuntu:24.04 \
    bash /tests/package-install-test.sh /packages/metrics-manager.deb "$scenario"
done
)
```

The script requires root inside a disposable container, refuses an existing
Metrics Manager installation or running systemd, and uses real `apt`/`dpkg`.
Only the package and test script are mounted, read-only. No host system
directories, devices, PID namespace or published ports are required.
Network access is needed for distribution dependencies and `curl`.

Both scenarios verify dependency resolution, account/file/FIFO ownership,
binary versions, documentation and offline systemd unit validation. The
installed Telegraf runs as the service user, exports an HTTP-ingested metric,
and supplies the installed TUI. Removal must preserve operator configuration;
purge must remove package configuration and the service account.

The upgrade scenario derives a synthetic lower-version fixture from the current
payload. It verifies that five modified conffiles survive, new defaults appear
as `.dpkg-dist`, and operator drop-ins/scripts remain unchanged. This is not a
test of an older release's binaries or automatic metric migration.

Run the optional-collector configuration tests without changing host services:

```bash
bash native/tests/configure-metrics-test.sh
```

Actual systemd startup, service restart during upgrade, reboot and privileged
hardware collection require an approved test host or disposable VM. Container
tests do not validate systemd sandbox enforcement or boot behavior.

## Development Setup

For local development with hot-reload:

```bash
# Install dev dependencies
uv sync --group test --group dev

# Run with auto-reload
uvicorn app.main:app --reload --port 9090

# Check application formatting, linting and types
.venv/bin/black --check app/
.venv/bin/ruff check app/
.venv/bin/mypy app/
```

Async fixtures use function-scoped event loops and close their stores/clients.
Resource leaks and unraisable exceptions fail the suite rather than being
silenced. Lifecycle regressions cover queued/active HTTP pushes, debounce
cancellation and cleanup when the application lifespan exits with an error.

---

## Troubleshooting Tests

| Issue                          | Solution                                                          |
| ------------------------------ | ----------------------------------------------------------------- |
| `Module not found: app`        | Ensure you are in `metrics-manager/` directory and ran `uv sync`  |
| `Connection refused on :9090`  | The API is not running. Start the service with `docker compose up -d` |
| `Test fixtures failed`         | Clear cache: `pytest --cache-clear`                               |
| `telemetry_selection skipped` | Set `TELEGRAF_TEST_BINARY` to the pinned Telegraf binary           |

## Supporting Resources

- [Get Started Guide](../get-started.md)
- [System Requirements](./system-requirements.md)
- [Building from Source](./build-from-source.md)
- [Troubleshooting](../troubleshooting.md)

## License

Copyright (C) 2025-2026 Intel Corporation

SPDX-License-Identifier: Apache-2.0
