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

> MQTT host/port and the SceneScape API URL are configured in
> `scene-config.yaml`, **not** through environment variables.

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
