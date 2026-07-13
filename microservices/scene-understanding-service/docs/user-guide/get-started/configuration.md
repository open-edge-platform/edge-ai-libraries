# Configuration

## Load Order

The service reads its configuration from two YAML files in a single directory:

1. `scene-config.yaml` — SceneScape connection, scenes, cameras, zones.
2. `rules.yaml` — rule definitions, thresholds, session flags, services.

The directory is `/app/configs` by default and can be changed with the
`CONFIG_DIR` environment variable. If the directory does not exist (local
development), the service falls back to the `configs/` directory next to the
source. A small set of environment variables supplies identity and
credentials (see below).

## Config Files

The image bakes in **sample** copies of both files under `configs/`, so the
service runs out-of-the-box. Every consuming application supplies its own
files via a read-only volume mount (e.g. `./configs:/app/configs:ro`), which
overrides the bundled samples.

### `scene-config.yaml`

| Section          | Required | Description                                                                 |
| ---------------- | -------- | --------------------------------------------------------------------------- |
| `scenescape_api` | Yes      | SceneScape REST base URL and paths, used for zone auto-discovery.           |
| `scenes`         | Yes      | List of scenes; each has a `scene_name`, `cameras`, and a `zones` mapping.  |
| `mqtt`           | Yes      | Broker host/port, TLS settings, and SceneScape topic patterns.             |
| `seaweedfs`      | No       | S3-compatible frame storage; required only when behavioral analysis is on. |
| `alert_service`  | No       | Downstream alert-service endpoint and enablement.                          |

Each `scenes[]` entry maps zone **names** (which must match the SceneScape
region names) to zone **types**: `HIGH_VALUE`, `CHECKOUT`, `EXIT`,
`RESTRICTED`. Rules trigger on the zone *type*.

```yaml
scenescape_api:
  base_url: https://web.scenescape.intel.com
  verify_ssl: false

scenes:
  - scene_name: example-scene
    cameras:
      - example-camera1
    zones:
      zone1: HIGH_VALUE
      zone2: CHECKOUT

mqtt:
  host: broker.scenescape.intel.com
  port: 1883
  use_tls: false
  # Topics shared with the behavioral-analysis worker (see env overrides below).
  ba_request_topic: ba/requests
  ba_result_topic: ba/results
```

### `rules.yaml`

| Section          | Description                                                            |
| ---------------- | --------------------------------------------------------------------- |
| `settings`       | Non-rule knobs (session timeout, frame-capture cadence).              |
| `variables`      | Default values for `${var:default}` substitution in rules.            |
| `session_flags`  | Boolean flags auto-set on the person session (zone-visit or external).|
| `services`       | Named escalation services rules can invoke (e.g. `behavioral_analysis`). |
| `rules`          | The rule list: each with a `trigger`, `conditions`, and `actions`.    |

Rule actions are either `alert` (produce an alert) or `escalate` (invoke a
named service such as behavioral analysis). Thresholds and rules can change
without code edits.

## Environment Variables

These are the only environment variables the service reads directly:

| Variable                 | Default              | Description                                              |
| ------------------------ | -------------------- | -------------------------------------------------------- |
| `CONFIG_DIR`             | `/app/configs`       | Directory containing `scene-config.yaml` and `rules.yaml`.|
| `STORE_ID`               | `store_001`          | Identifier included in all alert payloads.               |
| `SCENESCAPE_API_USER`    | _(empty)_            | SceneScape REST username for zone auto-discovery.        |
| `SCENESCAPE_API_PASSWORD`| _(empty)_            | SceneScape REST password.                                |
| `ENABLE_UI`              | `true`               | Enable the Gradio UI integration endpoints.              |
| `ALERT_SERVICE_URL`      | from `alert_service` | Overrides the downstream alert-service endpoint.         |
| `MQTT_HOST`              | `mqtt.host`          | MQTT broker host. Overrides `mqtt.host` in `scene-config.yaml`. |
| `MQTT_PORT`              | `mqtt.port`          | MQTT broker port. Overrides `mqtt.port` in `scene-config.yaml`. |
| `BA_REQUEST_TOPIC`       | `ba/requests`        | MQTT topic the service **publishes** BA frame-arrival requests to. Overrides `mqtt.ba_request_topic`. |
| `BA_RESULT_TOPIC`        | `ba/results`         | MQTT topic the service **subscribes** to for BA verdicts. Overrides `mqtt.ba_result_topic`. |

> The SceneScape API URL is configured in `scene-config.yaml`. MQTT broker
> host/port can be set either in `scene-config.yaml` (`mqtt.host` / `mqtt.port`)
> or overridden with the `MQTT_HOST` / `MQTT_PORT` environment variables.

> **BA topics are an integration contract.** The `BA_REQUEST_TOPIC` /
> `BA_RESULT_TOPIC` values **must be identical** on both this service and the
> behavioral-analysis worker that shares the same MQTT broker. Precedence is
> `env var` → `mqtt.ba_request_topic` / `mqtt.ba_result_topic` in
> `scene-config.yaml` → built-in default (`ba/requests` / `ba/results`). Define
> the value once (e.g. in a shared `.env`) and inject it into both services so
> they cannot drift.

Override at runtime by exporting the variables before starting the stack (they
flow through `docker compose` via `${BA_REQUEST_TOPIC:-ba/requests}`):

```bash
export BA_REQUEST_TOPIC=store_001/ba/requests
export BA_RESULT_TOPIC=store_001/ba/results
docker compose up -d
```

Or set them once in the deployment `.env` so both services pick up the same
values:

```dotenv
BA_REQUEST_TOPIC=store_001/ba/requests
BA_RESULT_TOPIC=store_001/ba/results
```

### Full `export` example

All variables the service reads, with their defaults. Export any you want to
override before `docker compose up` — unset ones fall back to `scene-config.yaml`
or the built-in defaults:

```bash
# Config / identity
export CONFIG_DIR=/app/configs
export STORE_ID=store_001

# SceneScape REST API (zone auto-discovery)
export SCENESCAPE_API_USER=admin
export SCENESCAPE_API_PASSWORD=changeme

# MQTT broker (overrides mqtt.host / mqtt.port in scene-config.yaml)
export MQTT_HOST=broker.scenescape.intel.com
export MQTT_PORT=1883

# BA integration contract (must match the behavioral-analysis worker)
export BA_REQUEST_TOPIC=ba/requests
export BA_RESULT_TOPIC=ba/results

# Downstream alert-service
export ALERT_SERVICE_URL=http://alert-service:8000

```

## TLS for MQTT

TLS is off by default (`mqtt.use_tls: false`), in which case `mqtt.ca_cert_path`
is ignored. When `mqtt.use_tls: true`, the CA cert is loaded from
`mqtt.ca_cert_path`, resolved **relative to `/app`** (so
`secrets/certs/scenescape-ca.pem` → `/app/secrets/certs/scenescape-ca.pem`); an
absolute path is used as-is. The cert is **not baked into the image** — mount
it via a volume (e.g. `./secrets:/app/secrets:ro`) so the resolved path exists,
otherwise the MQTT connection fails at startup.

## Disabling Behavioral Analysis

Behavioral analysis is opt-in through `rules.yaml`. To run without it:

- Provide a `rules.yaml` with `alert`-only actions (no `escalate`).
- Omit the `seaweedfs` block from `scene-config.yaml`.
- Do not deploy the behavioral-analysis container.

No code changes are needed — the feature simply stays idle.
