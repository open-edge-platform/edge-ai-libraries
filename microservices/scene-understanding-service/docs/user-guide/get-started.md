# Get Started

This page is the entry point for running the Scene Understanding Service.
Pick one of the two deployment paths and follow the linked guide.

## Before You Begin

- Confirm that your machine meets the
  [System Requirements](./get-started/system-requirements.md).
- Make sure you have a reachable **SceneScape** deployment (MQTT broker + REST
  API). The service is an event consumer — it needs SceneScape to produce
  meaningful output.
- Prepare your two config files (`scene-config.yaml` and `rules.yaml`). The
  service ships with samples under `configs/`; review the
  [Configuration Guide](./get-started/configuration.md) before editing them.

## Configure the Service

All runtime behavior is driven by **two YAML files** in a single directory
(`/app/configs` by default, or set `CONFIG_DIR`). The image bakes in working
samples so it starts out-of-the-box; supply your own files via a read-only
volume mount (e.g. `-v ./configs:/app/configs:ro`) to override them — **no code
changes required**.

1. **`scene-config.yaml`** — how the service connects to SceneScape and what it
   watches:

   - `scenescape_api` — SceneScape REST base URL (used for zone auto-discovery).
   - `mqtt` — broker host/port, TLS, and the SceneScape topic patterns to
     subscribe to.
   - `scenes` — the scenes/cameras to track, and a mapping of zone **names**
     (must match SceneScape region names) to zone **types**
     (`HIGH_VALUE`, `CHECKOUT`, `EXIT`, `RESTRICTED`).
   - `seaweedfs` / `alert_service` *(optional)* — evidence-frame storage and
     the downstream alert endpoint.

2. **`rules.yaml`** — how events are interpreted. This is where you adapt the
   service to your use case without touching code:

   - `rules` — each rule has a `trigger`, `conditions`, and `actions`
     (`alert` to raise an alert, or `escalate` to invoke a service).
   - `variables` / `session_flags` / `settings` — tunable thresholds, flags,
     and session knobs.
   - `services` — named escalation services (e.g. behavioral analysis) that
     rules can invoke.

A minimal `scene-config.yaml` looks like this:

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

A few identity/credential settings are supplied via environment variables
(`STORE_ID`, `SCENESCAPE_API_USER`, `SCENESCAPE_API_PASSWORD`, `ALERT_SERVICE_URL`).
MQTT and the SceneScape API URL are configured in `scene-config.yaml`, **not**
through environment variables.

See the [Configuration Guide](./get-started/configuration.md) for the full
field list, TLS setup, and how to disable behavioral analysis.

## Choose Deployment Path

<!--hide_directive::::{tab-set}
:::{tab-item}hide_directive--> **Run in Docker (Recommended)**
<!--hide_directive:sync: Docker hide_directive-->

The container image exposes the API on host port `8082` and reads its config
from `/app/configs`. The image bakes in the sample config, so it starts
out-of-the-box; mount your own `./configs` to override it.

See [Run with Docker Compose](./get-started/run-container.md) for the full step-by-step guide.

Quick start:

```bash
docker build -t intel/scene-understanding-service:latest .
docker run -p 8082:8082 \
  -v ./configs:/app/configs:ro \
  intel/scene-understanding-service:latest
curl --noproxy '*' http://127.0.0.1:8082/health
```

<!--hide_directive:::
:::{tab-item}hide_directive--> **Run on the Host**
<!--hide_directive:sync: Host hide_directive-->

Run the service directly with Python. This path is useful for development.

See [Run on the Host](./get-started/run-standalone.md) for the full step-by-step guide.

Quick start:

```bash
uv sync
uv run python main.py
```
<!--hide_directive:::
::::hide_directive-->

## Verify

Once the service is running:

```bash
curl --noproxy '*' http://127.0.0.1:8082/health
```

Expected response:

```json
{"status": "healthy"}
```

Service readiness (includes runtime stats):

```bash
curl --noproxy '*' http://127.0.0.1:8082/api/v1/lp/status
```

## Next Steps

- [API Reference](./api-reference.md) for endpoint details and examples
- [Configuration Guide](./get-started/configuration.md) to customize scenes, zones, and rules
- [Troubleshooting](./troubleshooting.md) for common startup issues

<!--hide_directive
:::{toctree}
:hidden:

./get-started/system-requirements.md
./get-started/configuration.md
./get-started/build-from-source.md
./get-started/run-container.md
./get-started/run-standalone.md

:::
hide_directive-->
