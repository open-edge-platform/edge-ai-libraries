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

Expected output: `179 passed in ~2s`

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

1. **Create virtual environment:**

   ```bash
   uv venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

2. **Install test dependencies:**

   ```bash
   uv sync --group test
   ```

3. **Configure environment:**

   ```bash
   cp .env.example .env
   ```

   Edit `.env` to point to your local Telegraf:

   ```bash
   TELEGRAF_PORT=9273
   TELEGRAF_HTTP_ENDPOINT=http://localhost:8186/write
   PROMETHEUS_TELEGRAF_ENDPOINT=http://localhost:9273
   ```

4. **Start Telegraf on host:**

   ```bash
   telegraf --config telegraf.conf
   ```

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

| Test File | Description |
|-----------|-------------|
| `test_models.py` | Pydantic models: Metric, SimpleMetric, MetricsBatch, InfluxDB/OTLP parsing |
| `test_store.py` | MetricsStore CRUD, persistence, cleanup, eviction, statistics |
| `test_routes.py` | REST API endpoints: health, ingestion, queries, Prometheus |
| `test_settings.py` | Pydantic Settings loading, env var overrides, validation |
| `test_logging_config.py` | Structured logging setup (JSON and text formats) |
| `test_main.py` | FastAPI middleware, lifespan, correlation ID handling |
| `test_metrics.py` | Internal service metrics counters and uptime |
| `test_rate_limit.py` | IP-based rate limiting middleware |
| `test_sse.py` | SSE endpoint `/metrics/stream`: streaming, parsing, errors |
| `test_npu_monitor_tool.py` | NPU bit slicing, register maps, value decoding |
| `test_npu_reader.py` | `npu_reader.py` syntax, Telegraf wiring, InfluxDB fields |
| `test_telegraf_integration.py` | Telegraf config mounting and custom-metrics (integration) |

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
tests/test_npu_monitor_tool.py::...      PASSED
tests/test_npu_reader.py::...            PASSED
tests/test_telegraf_integration.py::...  SKIPPED (requires Docker)
========================= 179 passed, 1 skipped in 1.70s ==============
```

---

## Development Setup

For local development with hot-reload:

```bash
# Install dev dependencies
uv sync --group test --group dev

# Run with auto-reload
uvicorn app.main:app --reload --port 9090

# Run linting and formatting
black app/
ruff check app/
```

---

## Troubleshooting Tests

| Issue | Solution |
|-------|----------|
| `Module not found: app` | Ensure you're in `metrics-manager/` directory and ran `uv sync` |
| `Connection refused on :9090` | Telegraf not running. Start it: `telegraf --config telegraf.conf` |
| `Test fixtures failed` | Clear cache: `pytest --cache-clear` |
| `telegraf_integration skipped` | Expected if not in Docker. Other tests still pass |

## Supporting Resources

- [Building from Source](./build-from-source.md)
- [Installation Guide](./installation.md)
- [System Requirements](./system-requirements.md)
- [Troubleshooting](../troubleshooting.md)

## License

Copyright (C) 2025-2026 Intel Corporation

SPDX-License-Identifier: Apache-2.0
