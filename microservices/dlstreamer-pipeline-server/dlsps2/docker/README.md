# DL Streamer Pipeline Server 2.0 - Docker Deployment

This directory contains Docker Compose configurations for deploying DL Streamer Pipeline Server 2.0 in various configurations.

## Available Configurations

### 1. **Standalone Pipeline Server** (Original)

**File:** `docker-compose.yml`

Runs only the DL Streamer Pipeline Server 2.0 with an MQTT broker for publishers.

```bash
# Start standalone
docker compose up -d

# View logs
docker compose logs -f

# Stop
docker compose down
```

**Services:**
- DL Streamer Pipeline Server (port 8080)
- MQTT Broker (port 1883)

**Configuration:**
- Edit `.env` to customize ports, logging, and external service endpoints

---

### 2. **Pipeline Server + Metrics Manager** (Extended - NEW)

**File:** `docker-compose-with-metrics.yml`

Runs both DL Streamer Pipeline Server 2.0 and Metrics Manager together for complete observability.

```bash
# Start with metrics
docker compose -f docker-compose-with-metrics.yml --env-file .env.metrics up -d

# View logs
docker compose -f docker-compose-with-metrics.yml --env-file .env.metrics logs -f

# Stop
docker compose -f docker-compose-with-metrics.yml --env-file .env.metrics down
```

**Services:**
- DL Streamer Pipeline Server (port 8080)
- Metrics Manager (port 9090)
- Telegraf Prometheus endpoint (port 9273)
- MQTT Broker (port 1883)

**Configuration:**
- Always pass `--env-file .env.metrics`. It holds the Metrics Manager settings and the DL Streamer base image this stack was tested with. The standalone `.env` is not used by this stack.

---

## Quick Start - Metrics Manager Integration

### Step 1: Prepare Environment

```bash
cd dlsps2/docker

# Edit .env.metrics as needed (ports, proxy, GPU_RENDER_GID, ...)
# Or keep your changes separate and pass that file instead:
cp .env.metrics .env.metrics.local
```

### Step 2: Start Combined Stack

```bash
# Start the stack
docker compose -f docker-compose-with-metrics.yml --env-file .env.metrics up -d

# Verify all services are healthy
docker compose -f docker-compose-with-metrics.yml --env-file .env.metrics ps
```

### Step 3: Verify Services

```bash
# DL Streamer health
curl http://localhost:8080/health

# Metrics Manager health
curl http://localhost:9090/health

# View system metrics
curl http://localhost:9273/metrics | head -20

# Stream metrics in real-time (SSE)
curl http://localhost:9090/metrics/stream
```

---

## Service Endpoints

### DL Streamer Pipeline Server (port 8080)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Health check |
| `/pipelines` | GET | List pipelines |
| `/pipelines?name=<id>` | GET | Load pipeline |
| `/pipelines?name=<id>` | POST | Run pipeline |
| `/pipelines?name=<id>` | DELETE | Stop pipeline |

### Metrics Manager (port 9090)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Basic health |
| `/api/v1/metrics` | POST | Ingest metrics (JSON batch) |
| `/api/v1/metrics/simple` | POST | Ingest single metric |
| `/api/v1/metrics/latest` | GET | Get latest metrics |
| `/metrics/stream` | GET | Real-time SSE stream |
| `/api/v1/stats` | GET | Service statistics |

### Telegraf Prometheus (port 9273)

```bash
curl http://localhost:9273/metrics
```

---

## Integration Examples

### Example 1: Pipeline Publishes Inference Metrics

DL Streamer runs a detection pipeline and publishes results to both MQTT and Metrics Manager:

```python
import httpx
import json

# After inference
latency_ms = 42.5
objects_detected = 5

# Push to Metrics Manager
httpx.post("http://metrics-manager:9090/api/v1/metrics", json={
    "metrics": [
        {
            "name": "inference_latency_ms",
            "fields": {"value": latency_ms},
            "tags": {"model": "yolov8", "device": "GPU"},
            "metric_type": "gauge"
        },
        {
            "name": "objects_detected",
            "fields": {"count": objects_detected},
            "tags": {"pipeline": "detection"},
            "metric_type": "gauge"
        }
    ]
})

# Metrics will appear in:
# - /api/v1/metrics/latest
# - /metrics/stream (SSE)
# - /metrics (Prometheus format)
```

### Example 2: Monitor with Prometheus + Grafana

Add to your `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: 'dlsps2-metrics'
    static_configs:
      - targets: ['localhost:9273']
```

Then query in Grafana:
```promql
# CPU usage
cpu_usage_percent{host="..."}

# Inference latency (custom metric)
inference_latency_ms{model="yolov8"}

# Pipeline throughput
rate(objects_detected[5m])
```

### Example 3: Real-Time Dashboard via SSE

```html
<!DOCTYPE html>
<html>
<head>
    <title>DL Streamer Metrics</title>
    <style>
        body { font-family: monospace; padding: 20px; }
        pre { background: #f0f0f0; padding: 10px; overflow-x: auto; }
    </style>
</head>
<body>
    <h1>Pipeline Metrics (Real-Time)</h1>
    <div id="metrics"></div>
    <script>
        const eventSource = new EventSource('http://localhost:9090/metrics/stream');
        eventSource.onmessage = function(event) {
            const data = JSON.parse(event.data);
            document.getElementById('metrics').innerHTML = 
                '<pre>' + JSON.stringify(data, null, 2) + '</pre>';
        };
        eventSource.onerror = function() {
            document.getElementById('metrics').innerHTML = 
                '<p style="color: red;">Connection lost. Reconnecting...</p>';
        };
    </script>
</body>
</html>
```

---

## Environment Variables

### Key Settings (in `.env.metrics`)

**Ports:**
```bash
REST_SERVER_PORT=8080          # DL Streamer API
HOST_METRICS_PORT=9090         # Metrics Manager API
HOST_TELEGRAF_PORT=9273        # Prometheus metrics
MQTT_PORT=1883                 # MQTT broker
```

**Logging:**
```bash
LOG_LEVEL=INFO                 # Metrics Manager log level
APP_LOG_LEVEL=INFO             # DL Streamer app logs
WEB_SERVER_LOG_LEVEL=WARNING   # DL Streamer web server logs
GST_DEBUG=1                    # GStreamer debug level
```

**Metrics:**
```bash
METRICS_RETENTION_SECONDS=300  # How long to keep custom metrics
MAX_METRICS_BATCH_SIZE=1000    # Max metrics per batch
HARDWARE_TELEMETRY_ENABLED=true # Collect CPU/GPU/NPU metrics
```

**Security:**
```bash
PRIVILEGED=true                # Hardware access (set false for restricted)
GPU_RENDER_GID=992             # GPU render group ID
```

**Proxy (if needed):**
```bash
http_proxy=http://proxy:911
https_proxy=http://proxy:912
no_proxy=localhost,127.0.0.1,10.0.0.0/8,broker,metrics-manager
```

---

## Troubleshooting

### Services won't start

```bash
# Check logs
docker compose -f docker-compose-with-metrics.yml --env-file .env.metrics logs -f

# Common issues:
# 1. Port in use: change REST_SERVER_PORT, HOST_METRICS_PORT in .env.metrics
# 2. Permission denied: ensure PRIVILEGED=true
# 3. GPU not found: verify GPU_RENDER_GID matches getent group render
```

### No metrics appearing

```bash
# Verify Metrics Manager is running
curl http://localhost:9090/health

# Check if Telegraf is collecting
curl http://localhost:9273/metrics | grep -E "^cpu_|^mem_"

# Manually push a test metric
curl -X POST http://localhost:9090/api/v1/metrics/simple \
  -H "Content-Type: application/json" \
  -d '{
    "name": "test_metric",
    "value": 42,
    "tags": {"test": "true"}
  }'

# Retrieve it
curl http://localhost:9090/api/v1/metrics/latest | jq '.test_metric'
```

### Can't reach metrics from DL Streamer

```bash
# Verify network connectivity
docker exec dlsps2-pipeline-server ping -c 1 metrics-manager

# Check DNS
docker exec dlsps2-pipeline-server getent hosts metrics-manager

# Verify service is healthy
curl http://localhost:9090/health
```

### Port already in use

```bash
# Find what's using the port
lsof -i :9090  # for Metrics Manager

# Change in .env.metrics
HOST_METRICS_PORT=9091

# Restart
docker compose -f docker-compose-with-metrics.yml --env-file .env.metrics down
docker compose -f docker-compose-with-metrics.yml --env-file .env.metrics up -d
```

---

## Advanced Configuration

### Custom Telegraf Configuration

Mount custom Telegraf config for Metrics Manager:

```yaml
# In docker-compose-with-metrics.yml
metrics-manager:
  volumes:
    - ./my-telegraf.conf:/etc/telegraf/telegraf.conf:ro
```

Or via environment:
```bash
# In .env.metrics
TELEGRAF_CONFIG=./my-telegraf.conf
```

### OpenTelemetry export to Metrics Manager

Enabled by default in `docker-compose-with-metrics.yml`. DL Streamer pushes its per-pipeline metrics (`fps_per_pipeline`, `frame_fps_per_pipeline`, ...) to the Metrics Manager OTLP endpoint. Override in `.env.metrics`:
```bash
ENABLE_OPEN_TELEMETRY=true
OTEL_COLLECTOR_HOST=metrics-manager
OTEL_COLLECTOR_PORT=9090
OTEL_COLLECTOR_PATH=/api/v1/metrics/otlp
OTEL_EXPORTER_OTLP_PROTOCOL=http/json   # Metrics Manager accepts OTLP JSON only, not protobuf
OTEL_EXPORT_INTERVAL_MILLIS=10000
```

Verify after starting a pipeline:
```bash
curl -s http://localhost:9090/api/v1/metrics/latest | jq -r '.metrics | keys[]' | grep fps_per_pipeline
```

### External Services Integration

Configure in `.env.metrics`:
```bash
# InfluxDB
INFLUXDB_HOST=influxdb.example.com
INFLUXDB_PORT=8086
INFLUXDB_USER=root
INFLUXDB_PASS=secret

# OPC-UA
OPCUA_SERVER_IP=plc.example.com
OPCUA_SERVER_PORT=4840

# S3 Storage
S3_STORAGE_HOST=minio.example.com
S3_STORAGE_PORT=9000
```

---

## Switching Between Configurations

```bash
# Switch from standalone to metrics
docker compose down                          # Stop standalone
docker compose -f docker-compose-with-metrics.yml --env-file .env.metrics up -d  # Start with metrics

# Revert to standalone
docker compose -f docker-compose-with-metrics.yml --env-file .env.metrics down
docker compose up -d  # Restart with original config
```

---

## Files in This Directory

| File | Purpose |
|------|---------|
| `docker-compose.yml` | Standalone DL Streamer + MQTT (original) |
| `docker-compose-with-metrics.yml` | DL Streamer + Metrics Manager (NEW) |
| `.env` | Environment variables for standalone |
| `.env.metrics` | Environment for the metrics stack, passed with `--env-file .env.metrics` |
| `Dockerfile` | DL Streamer image build definition |
| `run.sh` | Container entrypoint script |
| `mosquitto/` | MQTT broker configuration |
| `README.md` | This file |

---

## See Also

- [Metrics Manager Documentation](../../metrics-manager/docs/)
- [DL Streamer Pipeline Server Documentation](../docs/)
- [Edge AI Libraries Repository](https://github.com/open-edge-platform/edge-ai-libraries)

---

## Support

For issues or questions:
1. Check service logs: `docker compose logs -f`
2. Run health checks: `curl http://localhost:8080/health`
3. Open an issue: [GitHub Issues](https://github.com/open-edge-platform/edge-ai-libraries/issues)

---

## License

SPDX-License-Identifier: Apache-2.0
Copyright (C) 2026 Intel Corporation
