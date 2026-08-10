# Get Started

The Alert Agent Service is a generic multimodal alert action dispatcher. It accepts alert events from detection pipelines (video analytics, audio sensors, IoT devices, and more), optionally applies LLM-based reasoning via Google ADK and OpenVINO Model Server, and dispatches configurable action tools such as webhook notifications, MQTT publishing, snapshot saving, and structured logging.

## Features

- Dispatches alert actions via LLM-powered ADK or deterministic rule-based mode
- Accepts multimodal payloads — text, image, audio, video, and binary artifacts
- Built-in action tools: `log_alert`, `trigger_webhook`, `capture_snapshot`, `publish_mqtt`
- Subscription config for per-alert-name default tool routing and deduplication rules
- Escalation support — additional tools triggered after a consecutive-detection threshold
- MCP (Model Context Protocol) integration to extend the tool set dynamically
- Real-time SSE and WebSocket event streams for alert fanout to monitoring clients
- Hot-reload of tool and MCP configurations without service restart

## Prerequisites

- Docker Engine 24 or later
- Docker Compose v2 plugin (`docker compose`)
- Sufficient disk space for the LLM model (approximately 4 GB for the default Phi-4-mini-instruct model)

> **Note:** The default configuration uses `TARGET_DEVICE=GPU` for the OVMS LLM container. To run on CPU-only Intel devices, set `TARGET_DEVICE=CPU` in your environment. This increases LLM inference latency but requires no GPU.

See [System Requirements](./get-started/system-requirements.md) for full details.

## Deploy with Docker Compose

### 1. Clone the Microservice
Go to the target directory of your choice and clone the microservice. If you want to clone a specific release branch, replace main with the desired tag. To learn more on partial cloning, check the [Repository Cloning guide](https://docs.openedgeplatform.intel.com/dev/OEP-articles/contribution-guide.html#repository-cloning-partial-cloning).

```bash
git clone --filter=blob:none --sparse --branch main https://github.com/open-edge-platform/edge-ai-libraries.git
cd edge-ai-libraries/
git sparse-checkout set microservices/alert-agent-service/
cd microservices/alert-agent-service/
```

### 2. Configure Environment Variables

Export variables with the required configuration:

```bash
# ----- Service -----
export PORT=8000
export LOG_LEVEL=INFO
export REGISTRY="intel/"
export TAG=2026.2.0-rc1

# ----- ADK / LLM -----
export AGENT_MODE=true
export LLM_URL=http://ovms-llm:9000/v3
export LLM_MODEL=OpenVINO/Phi-4-mini-instruct-int4-ov
export LLM_TIMEOUT=10.0
export TARGET_DEVICE=GPU          # GPU (default) or CPU
# ----- Webhook action tool (optional) -----
export WEBHOOK_URL=https://your-webhook-endpoint.example.com/hook
export WEBHOOK_SECRET=                # leave empty to skip HMAC signing

# ----- MQTT action tool (optional) -----
export MQTT_BROKER=                   # e.g. mqtt.example.com
export MQTT_PORT=1883
export MQTT_USERNAME=
export MQTT_PASSWORD=
export MQTT_BASE_TOPIC=alerts

# ----- Proxy (if required) -----
export http_proxy=
export https_proxy=
export no_proxy=localhost,127.0.0.1,ovms-llm
```

> **Note:** `WEBHOOK_URL` and `MQTT_BROKER` are optional. If not set, the corresponding tools are skipped gracefully when invoked.

### 3. Start the Services

For rule-based mode:

```bash
docker compose -f docker/docker-compose.yml up -d
```

For ADK / agent mode:

```bash
docker compose -f docker/docker-compose.yml --profile agent up -d
```

This starts up to three containers:

| Container | Description |
|-----------|-------------|
| `alert-agent-service` | The alert action dispatcher |
| `mqtt` | Local MQTT broker used by the MQTT action tool |
| `ovms-llm` | OpenVINO Model Server serving the Phi-4-mini-instruct LLM (agent mode only) |

In agent mode, the `ovms-llm` container is started only when you include `--profile agent`. Initial startup may take 2–5 minutes while the LLM model is downloaded and loaded. During that time, `alert-agent-service` may be up before the LLM is ready.

To build the image locally before starting:

```bash
docker compose -f docker/docker-compose.yml up -d --build
# add --profile agent to start ovms-llm as well
```

### 4. Verify the Service is Running

```bash
docker compose -f docker/docker-compose.yml ps
```

Check the health endpoint:

```bash
curl http://localhost:8000/api/v1/health
```

Expected response:

```json
{
  "status": "healthy",
  "adk_enabled": true,
  "mcp_enabled": true,
  "uptime_seconds": 12.4,
  "timestamp": "2026-06-15T07:30:00Z"
}
```

### 5. Access the API Documentation

Open the Swagger UI at:

```json
  http://localhost:8000/docs
```

### 6. Stop the Services

```bash
# rule-based mode
docker compose -f docker/docker-compose.yml down

# agent mode
docker compose -f docker/docker-compose.yml --profile agent down
```

---

## Sample Usage

### Dispatch a Text Alert

```bash
curl -X POST http://localhost:8000/api/v1/actions/execute \
  -H "Content-Type: application/json" \
  -d '{
      "data":{
        "source_id": "sensor-42",
        "alert_name": "TemperatureThreshold",
        "answer": "YES",
        "reason": "CPU temperature exceeded 90°C",
        "tools": ["log_alert", "trigger_webhook"]
      }
}'
```

### Dispatch an Image Alert (base64 JPEG)

```bash
curl -X POST http://localhost:8000/api/v1/actions/execute \
  -H "Content-Type: application/json" \
  -d '{
        "data":{
            "source_id": "cam-01",
            "alert_name": "CONCEALMENT",
            "answer": "YES",
            "reason": "Camera lens partially covered",
            "tools": ["log_alert", "capture_snapshot", "trigger_webhook"],
            "payloads": [
              {
                "kind": "image",
                "mime_type": "image/jpeg",
                "encoding": "base64",
                "data_base64": "<base64-encoded-jpeg>",
                "metadata": {"width": 1920, "height": 1080}
              }
            ]
          }
  }'
```

**Sample response:**

```json
{
  "event_id": "a3f7c2d1e8b04e5f90123456789abcde",
  "source_id": "cam-01",
  "alert_name": "CONCEALMENT",
  "actions_taken": ["capture_snapshot", "log_alert", "trigger_webhook"],
  "snapshot_path": "/app/snapshots/cam-01_CONCEALMENT_20260615_073045.jpg",
  "duration_ms": 312.5,
  "timestamp": "2026-06-15T07:30:45Z"
}
```

### Subscribe to Real-Time SSE Events

```bash
curl -N http://localhost:8000/api/v1/events
```

Example output:

```
event: init
data: {"message": "Connected to Alert Agent Service SSE stream", "adk_enabled": true, "mcp_enabled": true}

event: alert_action
data: {"event_id": "...", "source_id": "cam-01", "alert_name": "CONCEALMENT", "actions_taken": ["log_alert"], ...}

event: keepalive
data: {"ts": 1749971445.123}
```

### List Available Tools

```bash
curl http://localhost:8000/api/v1/tools
```

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `8000` | Port the service listens on |
| `LOG_LEVEL` | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `AGENT_MODE` | `true` | Enable ADK (LLM-reasoned) dispatch; set `false` for rule-based mode |
| `TARGET_DEVICE` | `GPU` | OVMS inference device — set to `CPU` for Intel devices without a discrete GPU |
| `LLM_URL` | `http://ovms-llm:9000/v3` | OpenAI-compatible LLM endpoint |
| `LLM_MODEL` | `OpenVINO/Phi-4-mini-instruct-int4-ov` | Model repository path / name |
| `LLM_TIMEOUT` | `10.0` | LLM request timeout in seconds |
| `ACTION_WORKERS` | `2` | Concurrent worker pool size for tool execution |
| `WEBHOOK_URL` | _(empty)_ | Default webhook endpoint for `trigger_webhook` |
| `WEBHOOK_SECRET` | _(empty)_ | HMAC-SHA256 secret for webhook request signing |
| `MQTT_BROKER` | _(empty)_ | MQTT broker hostname or IP |
| `MQTT_PORT` | `1883` | MQTT broker port |
| `MQTT_USERNAME` | _(empty)_ | MQTT broker username |
| `MQTT_PASSWORD` | _(empty)_ | MQTT broker password |
| `MQTT_BASE_TOPIC` | `alerts` | Base MQTT topic prefix |
| `SNAPSHOT_DIR` | `snapshots` | Directory for saving image snapshots |
| `RETRY_ATTEMPTS` | `3` | Number of retry attempts for failed tool invocations |
| `RETRY_INTERVAL_SECONDS` | `2.0` | Delay in seconds between retry attempts |
| `SUBSCRIPTION_CONFIG_PATH` | `resources/config.yaml` | Path to the subscription YAML configuration file |
| `MCP_ENABLED` | `true` | Enable MCP server integration |
| `MCP_CONFIG_FILE` | `resources/mcp_servers.json` | Path to the MCP servers configuration file |

### Subscription Configuration (`resources/config.yaml`)

The subscription config defines default routing rules per alert name. Request-level fields always override these defaults.

```yaml
subscriptions:
  - alert_name: CONCEALMENT
    tools:
      - log_alert
      - trigger_webhook
      - capture_snapshot
    tool_arguments:
      trigger_webhook:
        url: "${WEBHOOK_URL}"
    dedup:
      enabled: true
      strategy: field_hash
      fields:
        - source_id
      window_seconds: 30
      on_missing: skip
    escalation:
      threshold_consecutive: 3
      additional_tools:
        - publish_mqtt

  - alert_name: LOITERING
    tools:
      - log_alert
    dedup:
      enabled: true
      strategy: field_hash
      fields:
        - source_id
      window_seconds: 120
      on_missing: skip

  - alert_name: INTRUSION
    tools:
      - log_alert
      - trigger_webhook
    tool_arguments:
      trigger_webhook:
        url: "${WEBHOOK_URL}"
    dedup:
      enabled: false
```

> **Note:** The `${WEBHOOK_URL}` placeholder is resolved at runtime from the environment variable.

### MCP Server Configuration (`resources/mcp_servers.json`)

Configure external MCP servers to extend the tool set dynamically:

```json
{
  "servers": [
    {
      "name": "prometheus",
      "enabled": true,
      "transport": "http",
      "url": "http://prometheus-mcp-server:9090/mcp",
      "description": "Prometheus MCP Server",
      "timeout": 30.0
    }
  ]
}
```

Set `"enabled": false` to disable a server without removing its configuration.

### Docker Volumes

| Volume | Container Path | Description |
|--------|---------------|-------------|
| `./resources` | `/app/resources` | Subscription config, tools.json, and mcp_servers.json (mounted for live updates) |
| `snapshots` | `/app/snapshots` | Persistent storage for captured image snapshots |

---

## Troubleshooting

**The alert-agent-service fails to start, showing `Agent not initialised`:**
- Check that `ovms-llm` has passed its health check: `docker compose -f docker/docker-compose.yml --profile agent logs ovms-llm`
- The LLM model may still be loading. Wait up to 5 minutes and re-check.
- If running on a CPU-only device, ensure `TARGET_DEVICE=CPU` is set in your environment before running `docker compose -f docker/docker-compose.yml up` (add `--profile agent` when using agent mode).

**Webhook notifications are skipped:**
- Verify `WEBHOOK_URL` is set and reachable from within the container.
- Check logs: `docker compose -f docker/docker-compose.yml logs alert-agent-service | grep webhook`

**MQTT publishing is skipped:**
- Verify `MQTT_BROKER` is set and the broker is reachable.
- Ensure `MQTT_PORT`, `MQTT_USERNAME`, and `MQTT_PASSWORD` are correct.

**Container logs:**

```bash
docker compose -f docker/docker-compose.yml logs -f alert-agent-service
docker compose -f docker/docker-compose.yml --profile agent logs -f ovms-llm
```

---

## Run Unit Tests

1. **Install `uv`** (if not already installed):

   ```bash
   pip install uv
   ```

2. **Create and activate a virtual environment**:

   ```bash
   uv venv
   source .venv/bin/activate
   ```

3. **Install dependencies**:

   ```bash
   uv sync
   ```

4. **Run tests**:

   ```bash
   uv run pytest tests/ -v
   ```

---

## Run in a Kubernetes Cluster

See [Deploy with Helm Chart](./get-started/deploy-with-helm-chart.md) for details.

## Learn More

- [**System Requirements**](./get-started/system-requirements.md)
- [**Deploy with Helm Chart**](./get-started/deploy-with-helm-chart.md)
- [**API Reference**](./api-reference.md)

<!--hide_directive
:::{toctree}
:hidden:

./get-started/system-requirements
./get-started/deploy-with-helm-chart

:::
hide_directive-->
