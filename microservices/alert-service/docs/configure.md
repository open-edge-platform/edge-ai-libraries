# Configuration & Customization

## Environment Variables

All settings can be controlled via `.env` (or real environment variables). Run `make init-env` to create a starter `.env` from `.env.example`.

| Variable | Default | Description |
|---|---|---|
| `MQTT_MODE` | `embedded` | `embedded` = start Mosquitto via compose; `external` = use a remote broker |
| `MQTT_HOST` | `` | Hostname/IP of the external MQTT broker (ignored in embedded mode) |
| `MQTT_PORT` | `1883` | MQTT broker port |
| `MQTT_USERNAME` | `` | MQTT auth username (external mode only) |
| `MQTT_PASSWORD` | `` | MQTT auth password (external mode only) |
| `CONFIG_PATH` | `config/config.yaml` | Path to YAML config |
| `LOG_LEVEL` | `INFO` | Logging level |
| `DELIVERY_HANDLERS` | `` | Comma-separated list of handlers (`log`, `mqtt`, `websocket`). When set, overrides the per-subscription `delivery` list in `config.yaml`. Leave empty to use YAML config. |

---

## MQTT Mode

### Embedded (default)

The bundled `docker/docker-compose.yml` includes a Mosquitto broker that starts automatically when `MQTT_MODE=embedded`.

```bash
MQTT_MODE=embedded
MQTT_PORT=1883
DELIVERY_HANDLERS=log,mqtt
```

> In embedded mode, `MQTT_HOST`, `MQTT_USERNAME`, and `MQTT_PASSWORD` are ignored. The service auto-connects to the compose service named `mqtt`.

```bash
make up    # starts alert-service + Mosquitto
make logs  # verify MQTT published lines appear
```

### External

If you already have an MQTT broker running elsewhere (e.g., HiveMQ, EMQX, a cloud broker), set `MQTT_MODE=external` and point `MQTT_HOST` to it.

```bash
MQTT_MODE=external
MQTT_HOST=broker.example.com
MQTT_PORT=1883
MQTT_USERNAME=user
MQTT_PASSWORD=pass
DELIVERY_HANDLERS=log,mqtt
```

```bash
make up    # starts only alert-service (no Mosquitto container)
make logs  # verify MQTT published lines appear
```

---

## Delivery Handlers Override

The `DELIVERY_HANDLERS` environment variable lets you override the per-subscription `delivery` arrays in `config.yaml` without editing YAML:

```bash
# Log only
DELIVERY_HANDLERS=log

# Log + MQTT
DELIVERY_HANDLERS=log,mqtt

# All three handlers
DELIVERY_HANDLERS=log,mqtt,websocket
```

> **Priority:** If `DELIVERY_HANDLERS` is set, it applies to **all** subscriptions and the `delivery` arrays in `config.yaml` are ignored. If it is empty or unset, the YAML config is used as-is.

### Verifying Handler Output

After posting an alert, run:

```bash
make logs
```

You will see lines like:

```
alert-service  | ... [INFO] src.delivery.log: ALERT DELIVERED [CONCEALMENT]: ...
alert-service  | ... [INFO] src.delivery.mqtt: MQTT published: alert_type=CONCEALMENT topic=alerts/concealment
alert-service  | ... [INFO] src.delivery.websocket: WebSocket broadcast: alert_type=CONCEALMENT clients=1
```

If a handler is not producing output, check:

1. The subscription in `config/config.yaml` includes the handler's `type`.
2. The related environment variables (e.g. `MQTT_HOST`) are set in `.env`.
3. The target service (MQTT broker) is reachable.
4. For the WebSocket handler, at least one client is connected to `ws://localhost:8000/api/v1/ws`.

---

## Deduplication

The alert service includes an in-memory, TTL-based deduplication engine that prevents the same alert from being delivered multiple times within a configurable time window.

### How It Works

1. When an alert arrives, the dedup engine extracts the configured `fields` from the alert payload.
2. It hashes the extracted field values into a **dedup key**.
3. If the key already exists in the in-memory store (i.e., the same alert was seen within `window_seconds`), the alert is **dropped** as a duplicate.
4. If the key is new, the alert is delivered and the key is stored with a TTL.

### Per-Subscription Configuration

> **Note:** `alert_type` matching is **case-sensitive**. The value in the incoming alert must exactly match the subscription name (e.g. `CONCEALMENT`, not `concealment`).

Deduplication is configured **per subscription** in `config/config.yaml`:

```yaml
subscriptions:
  - alert_type: CONCEALMENT
    dedup:
      enabled: true              # Toggle dedup on/off
      strategy: field_hash       # Strategy name (currently only field_hash)
      fields:                    # Fields to include in the dedup hash
        - metadata.poi_id
        - metadata.camera_id
      window_seconds: 30         # TTL — duplicates within this window are dropped
      on_missing: skip           # What to do if a field is missing: "skip" (skip dedup)
      hash:
        algorithm: sha1          # Hash algorithm (sha1, md5)
        truncate: 16             # Truncate hash to this many characters
```

### Configuration Reference

| Parameter | Type | Default | Description |
|---|---|---|---|
| `enabled` | bool | `false` | Enable or disable dedup for this subscription |
| `strategy` | string | `field_hash` | Dedup strategy (`field_hash`) |
| `fields` | list | `[]` | Dot-notation field paths to include in the hash (e.g. `metadata.poi_id`) |
| `window_seconds` | int | `30` | Time window in seconds — identical alerts within this window are dropped |
| `on_missing` | string | `skip` | Behaviour when a configured field is missing from the alert: `skip` = bypass dedup for this alert |
| `hash.algorithm` | string | `sha1` | Hash algorithm (`sha1` or `md5`) |
| `hash.truncate` | int | `16` | Truncate the hash to this many hex characters |

### Examples

**Dedup by person + camera (30 s window):**

```yaml
dedup:
  enabled: true
  strategy: field_hash
  fields:
    - metadata.poi_id
    - metadata.camera_id
  window_seconds: 30
```

**Dedup by zone only (2 min window):**

```yaml
dedup:
  enabled: true
  strategy: field_hash
  fields:
    - metadata.zone_id
  window_seconds: 120
```

**Disable dedup entirely:**

```yaml
dedup:
  enabled: false
```

### Verifying Deduplication

**Step 1 — Start the service and tail logs:**

```bash
make up
make logs
```

**Step 2 — Post the same alert twice within the dedup window:**

```bash
# First request — should be delivered
curl -X POST http://localhost:8000/api/v1/alerts \
  -H "Content-Type: application/json" \
  -d '{"alert_type":"CONCEALMENT","metadata":{"poi_id":"person-001","camera_id":"cam-north-01"},"timestamp":"2025-01-15T10:30:00Z"}'

# Second request (same poi_id + camera_id, within 30 s) — should be deduplicated
curl -X POST http://localhost:8000/api/v1/alerts \
  -H "Content-Type: application/json" \
  -d '{"alert_type":"CONCEALMENT","metadata":{"poi_id":"person-001","camera_id":"cam-north-01"},"timestamp":"2025-01-15T10:30:05Z"}'
```

**Step 3 — Check `make logs` output:**

```
# First alert — delivered
alert-service  | ... [INFO] src.delivery.log: ALERT DELIVERED [CONCEALMENT]: ...

# Second alert — deduplicated (no delivery log, only dedup log)
alert-service  | ... [INFO] src.dedup.engine: Duplicate alert detected: key=dedup:CONCEALMENT:f12f0454c181eaab
alert-service  | ... [INFO] src.worker: Alert deduplicated: alert_type=CONCEALMENT
```

**Step 4 — Wait for the window to expire, then post again:**

Wait 30 seconds (the `window_seconds` for CONCEALMENT), then post the same alert again — it should be delivered because the dedup key has expired.

**Step 5 — Verify different field values are NOT deduplicated:**

```bash
# Different camera_id — this is a new unique combination, should be delivered
curl -X POST http://localhost:8000/api/v1/alerts \
  -H "Content-Type: application/json" \
  -d '{"alert_type":"CONCEALMENT","metadata":{"poi_id":"person-001","camera_id":"cam-south-02"},"timestamp":"2025-01-15T10:30:00Z"}'
```

**Step 6 — Test with dedup disabled (INTRUSION):**

```bash
# INTRUSION has dedup disabled — every request should be delivered
curl -X POST http://localhost:8000/api/v1/alerts \
  -H "Content-Type: application/json" \
  -d '{"alert_type":"INTRUSION","metadata":{"zone_id":"restricted-area-1"},"timestamp":"2025-01-15T10:32:00Z"}'

# Post again immediately — should also be delivered (no dedup)
curl -X POST http://localhost:8000/api/v1/alerts \
  -H "Content-Type: application/json" \
  -d '{"alert_type":"INTRUSION","metadata":{"zone_id":"restricted-area-1"},"timestamp":"2025-01-15T10:32:01Z"}'
```

Both should produce `ALERT DELIVERED` lines in `make logs`.

---

## MQTT Guide

### Start Only the MQTT Broker (embedded mode)

```bash
docker compose -f docker/docker-compose.yml --profile embedded up -d mqtt
```

### Install MQTT CLI Tools

```bash
# Ubuntu / Debian
sudo apt-get install -y mosquitto-clients
```

This gives you `mosquitto_sub` (subscribe) and `mosquitto_pub` (publish).

### Subscribe to Alert Topics

Open a terminal and subscribe to all alert topics:

```bash
# Subscribe to all alerts (wildcard)
mosquitto_sub -h localhost -p 1883 -t "alerts/#" -v

# Or subscribe to a specific alert type
mosquitto_sub -h localhost -p 1883 -t "alerts/concealment" -v
```

Keep this terminal open — messages will appear here in real time.

### Publish a Test Message Directly to MQTT

In a separate terminal, publish a message directly to the broker (bypasses the alert service):

```bash
mosquitto_pub -h localhost -p 1883 -t "alerts/concealment" \
  -m '{"alert_type":"CONCEALMENT","metadata":{"poi_id":"person-99","camera_id":"cam-east"},"timestamp":"2025-06-01T12:00:00Z"}'
```

You should see the message appear in the `mosquitto_sub` terminal.

### End-to-End MQTT Verification

Test the full flow: REST API → alert service → MQTT broker → subscriber.

```bash
# Terminal 1: Subscribe to MQTT topics
mosquitto_sub -h localhost -p 1883 -t "alerts/#" -v

# Terminal 2: Post an alert via the REST API
curl -X POST http://localhost:8000/api/v1/alerts \
  -H "Content-Type: application/json" \
  -d '{"alert_type":"CONCEALMENT","metadata":{"poi_id":"person-001","camera_id":"cam-north-01"},"timestamp":"2025-01-15T10:30:00Z","source":"test"}'

# Terminal 3: Check service logs to confirm both handlers fired
make logs
```

**Expected output in Terminal 1 (mosquitto_sub):**

```
alerts/concealment {"alert_type": "CONCEALMENT", ...}
```

**Expected output in Terminal 3 (make logs):**

```
alert-service  | ... [INFO] src.delivery.log: ALERT DELIVERED [CONCEALMENT]: ...
alert-service  | ... [INFO] src.delivery.mqtt: MQTT published: alert_type=CONCEALMENT topic=alerts/concealment
```

---

## WebSocket Testing Guide

The alert service exposes a native **WebSocket endpoint** at `ws://localhost:8000/api/v1/ws`. When the `websocket` delivery handler is enabled, every alert is broadcast as a JSON message to all connected WebSocket clients in real time.

### Using `websocat` (CLI)

```bash
# Install websocat
# Ubuntu/Debian:
sudo apt-get install -y websocat
# Or via cargo:
cargo install websocat
```

Connect and listen for alerts:

```bash
# Terminal 1: connect to the WebSocket endpoint
websocat ws://localhost:8000/api/v1/ws

# Terminal 2: post an alert
curl -X POST http://localhost:8000/api/v1/alerts \
  -H "Content-Type: application/json" \
  -d '{"alert_type":"CONCEALMENT","metadata":{"poi_id":"person-001","camera_id":"cam-north-01"},"timestamp":"2025-01-15T10:30:00Z","source":"test"}'
```

**Expected output in Terminal 1:**

```json
{"alert_type": "CONCEALMENT", "metadata": {"poi_id": "person-001", "camera_id": "cam-north-01"}, "timestamp": "2025-01-15T10:30:00Z"}
```

### Using `wscat` (Node.js CLI)

```bash
npm install -g wscat
```

```bash
# Terminal 1: connect
wscat -c ws://localhost:8000/api/v1/ws

# Terminal 2: post an alert (same curl command as above)
```

### Using Python (`websockets`)

```bash
pip install websockets
```

```python
import asyncio
import websockets

async def listen():
    async with websockets.connect("ws://localhost:8000/api/v1/ws") as ws:
        print("Connected — waiting for alerts...")
        async for message in ws:
            print(f"Alert received: {message}")

asyncio.run(listen())
```

Run it, then post an alert from another terminal:

```bash
# Terminal 1: start the WebSocket listener
python3 ws_listener.py

# Terminal 2: post an alert
curl -X POST http://localhost:8000/api/v1/alerts \
  -H "Content-Type: application/json" \
  -d '{"alert_type":"CONCEALMENT","metadata":{"poi_id":"person-001","camera_id":"cam-north-01"},"timestamp":"2025-01-15T10:30:00Z","source":"test"}'
```

### Using a Browser

```html
<script>
  const ws = new WebSocket('ws://localhost:8000/api/v1/ws');
  ws.onopen = () => console.log('Connected to alert service');
  ws.onmessage = (event) => {
    const alert = JSON.parse(event.data);
    console.log('Alert received:', alert);
  };
  ws.onclose = () => console.log('Disconnected');
</script>
```

### Verifying WebSocket Events

**Step 1 — Start the service:**

```bash
make up
```

**Step 2 — Connect a WebSocket client:**

```bash
websocat ws://localhost:8000/api/v1/ws
```

**Step 3 — Confirm the connection in service logs:**

```bash
make logs
```

```
alert-service  | ... [INFO] src.delivery.ws_manager: WebSocket client connected (1 total)
```

**Step 4 — Post an alert from another terminal:**

```bash
curl -X POST http://localhost:8000/api/v1/alerts \
  -H "Content-Type: application/json" \
  -d '{"alert_type":"CONCEALMENT","metadata":{"poi_id":"person-001","camera_id":"cam-north-01"},"timestamp":"2025-01-15T10:30:00Z","source":"test"}'
```

**Step 5 — Check the WebSocket client output:**

The `websocat` terminal should print the alert JSON:

```json
{"alert_type": "CONCEALMENT", "metadata": {"poi_id": "person-001", "camera_id": "cam-north-01"}, "timestamp": "2025-01-15T10:30:00Z"}
```

**Step 6 — Confirm broadcast in service logs:**

```
alert-service  | ... [INFO] src.delivery.websocket: WebSocket broadcast: alert_type=CONCEALMENT clients=1
```

**Step 7 — Disconnect and verify cleanup:**

Close the `websocat` session (`Ctrl+C`). The service logs should show:

```
alert-service  | ... [INFO] src.delivery.ws_manager: WebSocket client disconnected (0 remaining)
```

If no WebSocket clients are connected when an alert is posted, the handler skips the broadcast silently (a debug-level log is emitted).

---

## MQTT-over-WebSocket Testing

The Mosquitto broker also exposes an **MQTT-over-WebSocket** listener on **port 9001**. This is separate from the native WebSocket endpoint above — it allows MQTT clients to connect using WebSocket transport.

> **Note:** Tools like `websocat` or `wscat` will **not** work with port 9001 — they speak raw WebSocket but Mosquitto expects the MQTT protocol layered on top. Use an MQTT client library with WebSocket transport instead.

### Using Python (`paho-mqtt` with WebSockets)

```bash
pip install paho-mqtt
```

A ready-made script is available at `tests/ws_subscriber.py`:

```python
import paho.mqtt.client as mqtt

def on_connect(client, userdata, flags, rc, properties=None):
    print(f"Connected (rc={rc})")
    client.subscribe("alerts/#")

def on_message(client, userdata, msg):
    print(f"[{msg.topic}] {msg.payload.decode()}")

client = mqtt.Client(
    callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
    transport="websockets",
)
client.connect("localhost", 9001)
client.on_connect = on_connect
client.on_message = on_message
client.loop_forever()
```

```bash
# Terminal 1: start the MQTT-over-WebSocket subscriber
python3 tests/ws_subscriber.py

# Terminal 2: post an alert
curl -X POST http://localhost:8000/api/v1/alerts \
  -H "Content-Type: application/json" \
  -d '{"alert_type":"CONCEALMENT","metadata":{"poi_id":"person-001","camera_id":"cam-north-01"},"timestamp":"2025-01-15T10:30:00Z","source":"test"}'
```

### Using a Browser (MQTT.js)

```html
<script src="https://unpkg.com/mqtt/dist/mqtt.min.js"></script>
<script>
  const client = mqtt.connect('ws://localhost:9001');
  client.on('connect', () => {
    console.log('Connected');
    client.subscribe('alerts/#');
  });
  client.on('message', (topic, msg) => {
    console.log(`[${topic}]`, msg.toString());
  });
</script>
```

**Next:** [Getting Started](get-started.md)
