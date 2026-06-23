# Configuration Guide

The Alert Service uses a hybrid configuration pipeline combining a central subscription file with environment variables.

## Load Order

The service loads configuration in the following order:

1. **Environment Variables / `.env`**: Loaded via Pydantic Settings on startup.
2. **YAML Configuration File (`config.yaml`)**: Loaded from the path set by `CONFIG_PATH` (defaults to `config/config.yaml`). Environment variable placeholders (like `${WEBHOOK_URL}`) are resolved during parsing.
3. **Delivery Handlers Overrides**: If the `DELIVERY_HANDLERS` environment variable is set, it overrides all per-subscription `delivery` list settings in `config.yaml`.

---

## Environment Variables

All global variables can be configured via real environment variables or set in the `.env` file at the root directory.

| Variable | Default | Description |
|---|---|---|
| `MQTT_MODE` | `embedded` | `embedded` = auto-connect to Mosquitto compose container;<br>`external` = connect to external host. |
| `MQTT_HOST` | *(empty)* | Host/IP address of the external MQTT broker (ignored in embedded mode). |
| `MQTT_PORT` | `1883` | Port of the MQTT broker. |
| `MQTT_USERNAME` | *(empty)* | Username for external MQTT authentication (optional). |
| `MQTT_PASSWORD` | *(empty)* | Password for external MQTT authentication (optional). |
| `CONFIG_PATH` | `config/config.yaml` | Path to the YAML configuration file. |
| `LOG_LEVEL` | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`). |
| `WEBHOOK_URL` | *(empty)* | Webhook destination URL. |
| `DELIVERY_HANDLERS` | *(empty)* | Comma-separated list of active handlers (`log`, `mqtt`, `websocket`). Overrides YAML configuration delivery lists. |

---

## Configuration File (`config.yaml`)

The subscription file controls retry behavior and routing subscriptions. Here is a breakdown of all parameters.

### Global Service Settings (`service`)

| Parameter | Type | Default | Description |
|---|---|---|---|
| `retry_attempts` | integer | `3` | Maximum number of delivery retries on failure. |
| `retry_interval_seconds` | integer | `5` | Time delay in seconds between retries. |

### Subscription Settings (`subscriptions`)

Each item in the `subscriptions` list defines how to ingest, deduplicate, and route a specific `alert_type`.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `alert_type` | string | *(required)* | Name of the incoming alert type (case-sensitive matching). |
| `dedup` | object | *(required)* | Deduplication configuration block. |
| `delivery` | list | `[]` | List of delivery targets to forward the alert to. |

#### Deduplication Settings (`dedup`)

| Parameter | Type | Default | Description |
|---|---|---|---|
| `enabled` | boolean | `false` | Turn deduplication on or off for this alert type. |
| `strategy` | string | `field_hash` | Deduplication strategy. Only `field_hash` is currently supported. |
| `fields` | list | `[]` | Dot-notation JSON paths (e.g. `metadata.camera_id`) to extract from the payload for hashing. |
| `window_seconds` | integer | `30` | Sliding window size (TTL) in seconds during which matching hashes are suppressed. |
| `on_missing` | string | `skip` | Actions on missing fields: `skip` (skips deduplication, always deliver), or empty string. |
| `hash.algorithm` | string | `sha1` | Hash algorithm: `sha1` or `md5`. |
| `hash.truncate` | integer | `16` | Characters to truncate the digest hex string. |

#### Delivery Target Settings (`delivery`)

Each entry in the `delivery` list represents a forwarding target.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `type` | string | `log` | Transport type: `log`, `mqtt`, `webhook`, `websocket`. |
| `url` | string | *(empty)* | Destination URL (used when `type` is `webhook`). Supports variable placeholders like `${WEBHOOK_URL}`. |
| `topic` | string | *(empty)* | MQTT topic to publish to (used when `type` is `mqtt`, defaults to `alerts/<alert_type_lowercase>`). |

---

## Delivery Handlers Override

To override subscriptions and route all processed alerts to a specific set of targets (for instance, during debugging), set the `DELIVERY_HANDLERS` environment variable:

```bash
# Force log-only output globally
DELIVERY_HANDLERS=log

# Force log and websocket output globally
DELIVERY_HANDLERS=log,websocket
```

When `DELIVERY_HANDLERS` is set, all subscriptions in `config.yaml` discard their local `delivery` arrays and use the overridden list instead.
