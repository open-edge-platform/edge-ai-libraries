# API Reference

Base URL: `http://localhost:8000/api/v1` (default).

---

## `GET /health`

Checks the liveness status of the Alert Service.

### Response

```json
{
  "status": "healthy"
}
```

---

## `POST /alerts`

Ingests a raw alert payload and enqueues it for asynchronous deduplication and delivery.

### Request Body (JSON)

| Parameter | Type | Required | Description |
|---|---|---|---|
| `alert_type` | string | Yes | Case-sensitive type matching the configured subscriptions. |
| `metadata` | object | No | Contextual metadata (e.g. `camera_id`, `poi_id`, `zone_id`). |
| `timestamp` | string | No | ISO 8601 formatted timestamp. Defaults to current UTC time if omitted. |

*Note: Any additional custom fields are preserved in the raw payload for logging or strategy extraction but excluded in basic downstream formats.*

### Examples

**Minimal Payload:**

```bash
curl -X POST http://localhost:8000/api/v1/alerts \
  -H "Content-Type: application/json" \
  -d '{"alert_type": "LOITERING", "metadata": {"zone_id": "zone-5"}}'
```

**Full Payload:**

```bash
curl -X POST http://localhost:8000/api/v1/alerts \
  -H "Content-Type: application/json" \
  -d '{
    "alert_type": "CONCEALMENT",
    "metadata": {
      "poi_id": "person-001",
      "camera_id": "cam-north-01"
    },
    "timestamp": "2025-01-15T10:30:00Z",
    "source": "inference-engine-01",
    "confidence": 0.94
  }'
```

### Response

```json
{
  "status": "accepted",
  "alert_type": "CONCEALMENT",
  "timestamp": "2025-01-15T10:30:00Z"
}
```

---

## `WS /ws`

Establishes a WebSocket connection to stream processed alerts to clients in real time.

When an alert is successfully processed (and passes deduplication check), it is broadcast as a JSON string to all currently active WebSocket connections if the `websocket` delivery target is enabled.

### Outbound Message Payload

```json
{
  "alert_type": "CONCEALMENT",
  "metadata": {
    "poi_id": "person-001",
    "camera_id": "cam-north-01"
  },
  "timestamp": "2025-01-15T10:30:00Z"
}
```

### CLI Testing Example (Using websocat)

```bash
# Connect and listen
websocat ws://localhost:8000/api/v1/ws
```
