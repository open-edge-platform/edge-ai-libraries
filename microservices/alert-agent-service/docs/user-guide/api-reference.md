# API Reference

**Version: 1.0.0**

The Alert Agent Service exposes a REST API at `http://<host>:<PORT>` (default port: `9001`).
Interactive API documentation (Swagger UI) is available at `http://<host>:9001/docs`.

---

## Endpoints Summary

### Actions

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/alerts` | Flexible JSON alert ingestion (alert-service compatible) |
| `POST` | `/api/v1/actions/execute` | Dispatch alert actions (main entry point) |

### Streaming

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/events` | Server-Sent Events stream for real-time alert fanout |
| `GET` | `/api/v1/ws` | WebSocket stream (mirrors SSE events) |

### Tools

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/tools` | List all registered action tools (built-in + MCP) |
| `POST` | `/api/v1/tools/{name}/invoke` | Manually invoke a built-in tool (testing/debugging) |
| `POST` | `/api/v1/tools/reload` | Hot-reload `resources/tools.json` without restart |

### MCP

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/mcp/status` | Get connection status of all configured MCP servers |
| `GET` | `/api/v1/mcp/tools` | List all tools discovered from MCP servers |
| `POST` | `/api/v1/mcp/reload` | Reconnect to MCP servers and refresh the tool registry |
| `POST` | `/api/v1/mcp/tools/{name}/invoke` | Manually invoke an MCP tool (testing/debugging) |

### Subscriptions

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/subscriptions` | List all loaded subscription entries from config |

### Observability

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/health` | Liveness probe |

---

## POST /api/v1/alerts

Accept a flexible JSON alert payload, matching the alert-service API contract. This endpoint normalises the incoming payload and dispatches it through the standard action pipeline. Downstream callers that already integrate with alert-service can use this endpoint without changes.

### Request Body

Any JSON object. The following fields are recognised and mapped:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `alert_type` | string | `"UNKNOWN"` | Alert type identifier |
| `source_id` | string | `"unknown"` | Originating source identifier |
| `alert_name` | string | value of `alert_type` | Name of the triggered alert |
| `answer` | string | `"YES"` | Detection result (`YES` / `NO`) |
| `reason` | string | `""` | Human-readable explanation |
| `metadata` | object | `{}` | Arbitrary metadata |
| `timestamp` | string | auto-generated | ISO-8601 timestamp |
| `tools` | array | `["log_alert"]` | Tool names to invoke |
| `payloads` | array | `[]` | Multimodal payload list |

### Example Request

```bash
curl -X POST http://localhost:9001/api/v1/alerts \
  -H "Content-Type: application/json" \
  -d '{
    "alert_type": "fire_detection",
    "source_id": "cam-01",
    "metadata": {"confidence": 0.95},
    "timestamp": "2026-06-19T08:30:00Z"
  }'
```

### Response

```json
{
  "status": "accepted",
  "alert_type": "fire_detection",
  "timestamp": "2026-06-19T08:30:00+00:00"
}
```

---

## POST /api/v1/actions/execute

Submit an alert with optional multimodal payloads. The service dispatches configured tools via ADK (LLM-reasoned) or rule-based mode, then fans the result out to all SSE/WebSocket subscribers.

### Request Body

```json
{
  "event_id": "string (auto-generated UUID if omitted)",
  "source_id": "string (required) — camera ID, sensor ID, device ID",
  "alert_name": "string (required) — matches subscription config entries",
  "answer": "YES | NO (default: YES) — tools only execute when YES",
  "reason": "string — human-readable explanation of the detection",
  "consecutive_count": "integer >= 1 (default: 1) — for escalation logic",
  "escalated": "boolean (default: false)",
  "tools": ["log_alert", "trigger_webhook", ...],
  "tool_arguments": {
    "trigger_webhook": {"url": "https://..."}
  },
  "escalation": {
    "threshold_consecutive": 3,
    "additional_tools": ["publish_mqtt"]
  },
  "payloads": [
    {
      "kind": "text | image | audio | video | binary",
      "mime_type": "string (e.g. image/jpeg)",
      "encoding": "base64 | uri | raw",
      "data_base64": "string (base64-encoded bytes)",
      "uri": "string (remote or local URI)",
      "data_text": "string (plain text, when kind=text and encoding=raw)",
      "metadata": {}
    }
  ],
  "dedup": {
    "enabled": false,
    "strategy": "field_hash",
    "fields": ["source_id"],
    "window_seconds": 30,
    "on_missing": "skip"
  }
}
```

### Response Body

```json
{
  "event_id": "string",
  "source_id": "string",
  "alert_name": "string",
  "actions_taken": ["log_alert", "trigger_webhook"],
  "snapshot_path": "string | null",
  "duration_ms": 312.5,
  "timestamp": "2026-06-15T07:30:45Z"
}
```

### Key Behaviours

- When `answer=NO`, the request returns immediately with `actions_taken=[]` and no tools are executed.
- When deduplication is active and the event is a duplicate within the window, the request returns immediately with `actions_taken=[]`.
- Tool list resolution order: request `tools` field → subscription config default → fallback to `["log_alert"]`.
- `capture_snapshot` is executed before the ADK agent so the snapshot path is available to subsequent tools.
- The response `actions_taken` lists only the tools that completed successfully.

---

## GET /api/v1/events (SSE)

Connects to the Server-Sent Events stream and receives real-time alert dispatch events.

### Event Types

| Event | Description |
|-------|-------------|
| `init` | Emitted on connect — confirms service info |
| `alert_action` | Emitted after each successful dispatch |
| `keepalive` | Emitted every 15 seconds to prevent proxy timeouts |
| `error` | Emitted on unexpected SSE-level errors |

### Example `alert_action` Event Data

```json
{
  "event_id": "a3f7c2d1...",
  "source_id": "cam-01",
  "alert_name": "CONCEALMENT",
  "answer": "YES",
  "reason": "Camera lens partially covered",
  "actions_taken": ["log_alert", "capture_snapshot"],
  "tools_requested": ["log_alert", "capture_snapshot", "trigger_webhook"],
  "consecutive_count": 1,
  "escalated": false,
  "snapshot_path": "/app/snapshots/cam-01_CONCEALMENT_20260615_073045.jpg",
  "payload_kinds": ["image"],
  "duration_ms": 312.5,
  "timestamp": "2026-06-15T07:30:45Z"
}
```

---

## GET /api/v1/health

Liveness probe — always returns `200 OK` while the process is alive.

### Response Body

```json
{
  "status": "healthy",
  "adk_enabled": true,
  "mcp_enabled": true,
  "uptime_seconds": 120.3,
  "timestamp": "2026-06-15T07:30:00Z"
}
```

---

## GET /api/v1/tools

Lists all registered action tools and their status.

### Response Body

```json
{
  "tools": [
    {
      "name": "log_alert",
      "enabled": true,
      "description": "Log the alert event to application logs.",
      "requires_env": []
    },
    {
      "name": "trigger_webhook",
      "enabled": true,
      "description": "Send an HTTP POST webhook notification.",
      "requires_env": ["WEBHOOK_URL"]
    },
    {
      "name": "capture_snapshot",
      "enabled": true,
      "description": "Save the image payload to disk.",
      "requires_env": []
    },
    {
      "name": "publish_mqtt",
      "enabled": true,
      "description": "Publish the alert to an MQTT broker.",
      "requires_env": ["MQTT_BROKER"]
    }
  ],
  "count": 4
}
```

---

## GET /api/v1/mcp/status

Returns the connection status of all configured MCP servers.

### Response Body

```json
{
  "enabled": true,
  "servers": [
    {
      "name": "prometheus",
      "connected": true,
      "tool_count": 6
    }
  ],
  "total_tools": 6
}
```

---

## GET /api/v1/subscriptions

Lists all subscription entries loaded from the subscription config file.

### Response Body

```json
{
  "subscriptions": [
    {
      "alert_name": "CONCEALMENT",
      "tools": ["log_alert", "trigger_webhook", "capture_snapshot"],
      "tool_arguments": {"trigger_webhook": {"url": "https://..."}},
      "dedup": {"enabled": true, "strategy": "field_hash", "fields": ["source_id"], "window_seconds": 30},
      "escalation": {"threshold_consecutive": 3, "additional_tools": ["publish_mqtt"]}
    }
  ],
  "count": 1
}
```

---

<!--hide_directive
```{eval-rst}
.. swagger-plugin:: ./_assets/openapi.yaml
```
hide_directive-->
