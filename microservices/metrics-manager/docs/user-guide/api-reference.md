# API Reference

**Version: 2026.1.0**

This document describes all REST API endpoints, request/response formats, and examples.

---

## Health Checks

### Basic Health Check

```bash
curl http://localhost:9090/health
```

```json
{
  "status": "healthy",
  "version": "2026.1.0",
  "uptime_seconds": 3600.5,
  "checks": {"store": true}
}
```

### Detailed Health Check

```bash
curl http://localhost:9090/api/health
```

```json
{
  "status": "healthy",
  "version": "2026.1.0",
  "uptime_seconds": 3600.5,
  "checks": {"store": true},
  "metrics_store": {
    "total_metrics": 42,
    "metric_names": ["fps", "cpu"],
    "retention_seconds": 300,
    "max_metrics": 100000,
    "telegraf_endpoint": "http://localhost:8186/write"
  },
  "sse_subscribers": 2
}
```

### Service Statistics

```bash
curl http://localhost:9090/api/v1/stats
```

```json
{
  "requests_total": 1523,
  "errors_total": 5,
  "metrics_received_total": 45000,
  "sse_events_sent": 3120,
  "uptime_seconds": 3600.5
}
```

---

## Push Metrics

Four input formats are supported. All return `{"accepted": N, "message": "..."}`.

### A. Simple JSON - `POST /api/v1/metrics/simple`

The simplest format for single metrics.

```bash
# Single metric
curl -X POST http://localhost:9090/api/v1/metrics/simple \
  -H "Content-Type: application/json" \
  -d '{"name": "my_metric", "value": 42.5}'

# With tags
curl -X POST http://localhost:9090/api/v1/metrics/simple \
  -H "Content-Type: application/json" \
  -d '{
    "name": "fps",
    "value": 29.97,
    "tags": {"source": "camera1", "pipeline": "detection"}
  }'

# With explicit timestamp (optional)
curl -X POST http://localhost:9090/api/v1/metrics/simple \
  -H "Content-Type: application/json" \
  -d '{
    "name": "fps",
    "value": 29.97,
    "timestamp": 1776947971
  }'
```

**Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | yes | Metric name (1–256 chars) |
| `value` | int \| float | yes | Numeric value |
| `tags` | object | no | Key-value labels (e.g. `{"source": "camera1"}`) |
| `timestamp` | int \| float | no | Unix timestamp — seconds (`< 1e12`), milliseconds (`< 1e15`), or nanoseconds. Auto-detected. Defaults to current UTC time if omitted. |

---

### B. JSON Batch - `POST /api/v1/metrics`

Multiple metrics at once, with multiple fields per metric.

```bash
curl -X POST http://localhost:9090/api/v1/metrics \
  -H "Content-Type: application/json" \
  -d '{
    "metrics": [
      {
        "name": "cpu",
        "fields": {"usage_user": 45.2, "usage_system": 12.1},
        "tags": {"host": "server1"},
        "timestamp": 1704067200000000000
      },
      {
        "name": "inference",
        "fields": {"latency_ms": 23.5, "throughput": 42},
        "tags": {"model": "yolov8"},
        "metric_type": "gauge"
      }
    ]
  }'
```

**Response:**
```json
{"accepted": 2, "message": "Accepted 2 metrics"}
```

---

### C. InfluxDB Line Protocol - `POST /api/v1/metrics/influx`

Standard InfluxDB text format, one metric per line.

```bash
curl -X POST http://localhost:9090/api/v1/metrics/influx \
  -H "Content-Type: text/plain" \
  -d 'cpu_usage,host=server1,cpu=cpu0 usage=45.2 1704067200000000000
memory,host=server1 used_percent=67.5 1704067200000000000
fps,pipeline=detection value=29.97'
```

**Format:**
```
measurement[,tag1=val1,tag2=val2] field1=val1[,field2=val2] [timestamp]
```

**Alternative endpoint (InfluxDB-compatible):**

```bash
curl -X POST http://localhost:9090/write \
  -H "Content-Type: text/plain" \
  -d 'cpu,host=server1 usage=45.2'
```

Returns `204 No Content`.

**Direct to Telegraf HTTP listener (bypasses FastAPI):**

```bash
curl -X POST http://localhost:8186/write \
  -H "Content-Type: text/plain" \
  -d 'cpu,host=server1 usage=45.2'
```

---

### D. OpenTelemetry (OTLP) - `POST /api/v1/metrics/otlp`

OpenTelemetry metrics format (protocol buffer or JSON).

```bash
curl -X POST http://localhost:9090/api/v1/metrics/otlp \
  -H "Content-Type: application/json" \
  -d '{
    "resourceMetrics": [{
      "resource": {
        "attributes": [
          {"key": "service.name", "value": {"stringValue": "my-service"}}
        ]
      },
      "scopeMetrics": [{
        "metrics": [{
          "name": "custom_metric",
          "gauge": {
            "dataPoints": [{
              "asDouble": 42.5,
              "attributes": [
                {"key": "host", "value": {"stringValue": "server1"}}
              ]
            }]
          }
        }]
      }]
    }]
  }'
```

---

## Query Metrics

### Get All Custom Metrics (JSON)

```bash
curl http://localhost:9090/api/v1/metrics
```

```json
{
  "metrics": {
    "fps": {
      "name": "fps",
      "fields": {"value": 29.97},
      "tags": {"source": "camera1"},
      "timestamp": 1704067200
    },
    "cpu": {
      "name": "cpu",
      "fields": {"usage": 45.2},
      "tags": {"host": "server1"},
      "timestamp": 1704067200
    }
  }
}
```

### Filter by Metric Name

```bash
curl "http://localhost:9090/api/v1/metrics?name=fps"
```

### Get Latest Value for Each Metric

```bash
curl http://localhost:9090/api/v1/metrics/latest
```

### Get Metric Names List

```bash
curl http://localhost:9090/api/v1/metrics/names
```

```json
{"names": ["fps", "cpu", "mem"], "count": 3}
```

### Prometheus Format (Custom Metrics Only)

```bash
curl http://localhost:9090/metrics
```

```
fps{source="camera1"} 29.97
cpu_usage{host="server1"} 45.2
```

### Telegraf Prometheus Endpoint (System + Custom Metrics)

```bash
curl http://localhost:9273/metrics
```

Returns all system metrics (CPU, memory, temperature, GPU, NPU) plus persisted custom metrics in Prometheus text format.

---

## Delete Metrics

### Clear All Metrics

```bash
curl -X DELETE http://localhost:9090/api/v1/metrics
```

```json
{"cleared": 5, "message": "Cleared 5 metrics"}
```

### Clear a Specific Metric by Name

```bash
curl -X DELETE "http://localhost:9090/api/v1/metrics?name=my_metric"
```

---

## SSE Streaming

### Connect as Client (Python)

```python
import httpx

with httpx.stream("GET", "http://localhost:9090/metrics/stream",
                  headers={"Accept": "text/event-stream"}) as r:
    for line in r.iter_lines():
        if line.startswith("data:"):
            import json
            event = json.loads(line[5:])
            print(event)
```

### Connect as Client (JavaScript)

```javascript
const es = new EventSource('http://localhost:9090/metrics/stream');
es.onmessage = (event) => {
  const { metrics } = JSON.parse(event.data);
  console.log(metrics);
};
```

### Event Format

```json
{
  "timestamp": 1777461975860,
  "metrics": [
    {
      "name": "cpu_usage_user",
      "labels": {"cpu": "cpu-total", "host": "myhost"},
      "value": 0.14,
      "timestamp": 1777463430000
    },
    {
      "name": "memory_used_percent",
      "labels": {"host": "myhost"},
      "value": 67.5,
      "timestamp": 1777463430000
    }
  ]
}
```

Each event contains all metrics available at that moment (system + custom). The stream polls Telegraf every `PROMETHEUS_POLLER_INTERVAL_MS` milliseconds (default 500 ms).

### Browser / Live UI

Opening `http://localhost:9090/metrics/stream` in a browser serves an HTML page with an in-place updated table. Direct SSE access:

```bash
curl -N -H "Accept: text/event-stream" http://localhost:9090/metrics/stream
```

---

## Metric Types

Supported `metric_type` values in JSON Batch format (default: `gauge`):

| Type | Description | Example |
|------|-------------|---------|
| `gauge` | Instantaneous value | temperature, FPS, CPU usage |
| `counter` | Monotonic counter | request count, processed frames |
| `histogram` | Value distribution | request latency |
| `summary` | Statistical summary | response time percentiles |

---

## System Metrics (Telegraf)

Collected every 1 second, available at `:9273/metrics` (Prometheus format).

### CPU (`cpu`)

| Field | Description |
|-------|-------------|
| `usage_user` | % CPU usage by user processes |
| `usage_system` | % CPU usage by system processes |
| `usage_idle` | % CPU in idle state |

### RAM (`mem`)

| Field | Description |
|-------|-------------|
| `used_percent` | % memory used |
| `available_percent` | % memory available |
| `total` | Total memory (bytes) |
| `used` | Used memory (bytes) |

### CPU Frequency (`cpu_freq`)

Collected by the `scripts/read_cpu_freq.sh` script in InfluxDB Line Protocol format.

### Temperature (`temp`)

Filtered to `coretemp_package_id_*` (CPU package temperature). Tag: `sensor`.

### Intel Arc GPU (via `qmassa`)

| Field | Description |
|-------|-------------|
| `engine_usage_compute` | % compute engine usage |
| `engine_usage_render` | % render engine usage |
| `engine_usage_copy` | % copy engine usage |
| `engine_usage_video` | % video engine usage |
| `engine_usage_video_enh` | % video-enhance engine usage |
| `frequency` | GPU frequency |
| `power` | GPU power consumption |

### Intel NPU (`npu`) via `scripts/npu_reader.py`

| Prometheus Name | Field | Description |
|---|---|---|
| `npu_power` | `power` | NPU power draw in watts (derived from `VPU_ENERGY` delta) |
| `npu_frequency` | `frequency` | NPU display frequency in Hz |
| `npu_temperature` | `temperature` | NPU SoC temperature in °C (integer) |
| `npu_bandwidth` | `bandwidth` | NoC memory bandwidth delta in MB/s |
| `npu_tile_config` | `tile_config` | Active tile configuration |
| `npu_utilization` | `utilization` | % NPU utilization over the last interval (0–100) |
| `npu_memory_mb` | `memory_mb` | NPU memory usage in MB (`-1` on platforms without the sysfs node, e.g. MTL/ARL) |

**Requirements:**
- Intel NPU present and the `intel_vpu` driver loaded (`ls /sys/bus/pci/drivers/intel_vpu/`)
- `/sys/class/intel_pmt/` accessible inside the container (provided by `privileged: true` + `/sys:/sys:ro`)
- Supported generations: Meteor Lake (MTL), Arrow Lake (ARL/ARL-H/ARL-S), Lunar Lake (LNL), Panther Lake (PTL). On pre-PTL platforms, `npu_memory_mb` reports `-1`

---

## Endpoint Summary

### Input (POST)

| Format | Endpoint |
|--------|----------|
| JSON Batch | `POST /api/v1/metrics` |
| Simple | `POST /api/v1/metrics/simple` |
| InfluxDB Line Protocol | `POST /api/v1/metrics/influx` |
| InfluxDB-compatible | `POST /write` |
| OpenTelemetry (OTLP) | `POST /api/v1/metrics/otlp` |

### Output (GET)

| Format | Endpoint |
|--------|----------|
| JSON metrics list | `GET /api/v1/metrics` |
| JSON latest per name | `GET /api/v1/metrics/latest` |
| Metric names list | `GET /api/v1/metrics/names` |
| Prometheus text | `GET /metrics` |
| Basic health | `GET /health` |
| Detailed health | `GET /api/health` |
| Service statistics | `GET /api/v1/stats` |

### Delete

| Action | Endpoint |
|--------|----------|
| Clear all | `DELETE /api/v1/metrics` |
| Clear by name | `DELETE /api/v1/metrics?name=X` |

### SSE

| Endpoint | Description |
|----------|-------------|
| `GET /metrics/stream` | SSE stream (system + custom metrics, auto-negotiates HTML for browsers) |

---

## Response Models

| Endpoint | Response Model |
|----------|----------------|
| `GET /health` | `HealthResponse` |
| `GET /api/health` | `DetailedHealthResponse` |
| `POST /api/v1/metrics*` | `MetricsAcceptedResponse` |
| `GET /api/v1/metrics` | `MetricsListResponse` |
| `GET /api/v1/metrics/latest` | `MetricsLatestResponse` |
| `GET /api/v1/metrics/names` | `MetricNamesResponse` |
| `DELETE /api/v1/metrics` | `MetricsClearedResponse` |
| `GET /metrics` | `str` (Prometheus text format) |

---

## HTTP Status Codes

| Code | Scenario |
|------|----------|
| `200 OK` | Request successful |
| `201 Created` | Metric created (if applicable) |
| `204 No Content` | Request successful, no body (e.g., `/write` endpoint) |
| `400 Bad Request` | Invalid request format or missing required fields |
| `422 Unprocessable Entity` | Validation error (Pydantic) — invalid metric type, malformed JSON, etc. |
| `429 Too Many Requests` | Rate limit exceeded |
| `500 Internal Server Error` | Server error (unexpected exception) |
| `503 Service Unavailable` | Telegraf endpoint unreachable (for some operations) |

---

## Rate Limiting

Rate limiting is applied per client IP (unless `TRUST_FORWARDED_HEADERS=true`).

- **Limit**: `RATE_LIMIT_REQUESTS_PER_MINUTE` (default 1000 requests/minute)
- **Burst**: `RATE_LIMIT_BURST` (default 100 tokens available upfront)
- **Exempt paths**: `/health`, `/api/v1/stats`, SSE endpoints

**Response when rate limited:**
```
HTTP/1.1 429 Too Many Requests
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1704067260
```

## License

Copyright (C) 2025-2026 Intel Corporation

SPDX-License-Identifier: Apache-2.0

## Supporting Resources

- [How It Works (Architecture)](./how-it-works.md)
- [Configuration Guide](./get-started/environment-variables.md)
- [Troubleshooting](./troubleshooting.md)
