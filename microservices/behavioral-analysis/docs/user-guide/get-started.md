# Get Started

This page is the entry point for running the Behavioral Analysis Service.

For a detailed overview of the service architecture, capabilities, and design, see
[How It Works](./how-it-works).

## Before You Begin

- Confirm that your machine meets the [System Requirements](./get-started/system-requirements.md).
- Ensure deployment-specific dependencies are reachable:
  - `seaweedfs+mqtt` mode: MQTT broker, SeaweedFS S3-compatible storage, and OVMS if VLM is enabled
  - `standalone+api` mode: REST API clients and OVMS if VLM is enabled
- Obtain the **YOLO-Pose model** in OpenVINO IR format (`.xml` + `.bin`).
- If VLM is enabled, download and place the VLM model files before startup (for Docker Compose, under `DOWNLOADED_MODEL_PATH/vlm_models`).
- Review the [Configuration Guide](./get-started/configuration.md) before starting deployment.

## Configure the Service

All runtime behavior is driven by **environment variables and one YAML pattern file**:

> **Important:**
>
> - Configuration is mandatory for all runs: quick start, Docker
>   deployment, and host deployment.
>
> - The service may start with default values,
>   but successful analysis requires deployment-specific configuration.

See [Configuration Guide](./get-started/configuration.md) for the full pattern DSL, environment variables, and VLM settings.

## Choose Deployment Path

The service supports two deployment modes configured by the `DEPLOYMENT_MODE` environment variable:

| Mode | Primary Interface | Uses SeaweedFS | Uses MQTT | Typical Use Case |
| --- | --- | --- | --- | --- |
| `seaweedfs+mqtt` | Asynchronous queue processing | Yes | Yes | Production pipelines where upstream services write frames and publish analysis requests |
| `standalone+api` | Direct REST API (`POST /api/v1/analyze/batch`) | No | No | Local testing, integration testing, and direct API-driven deployments (OVMS service starts by default in Docker Compose) |

Default mode: `standalone+api` (as defined in the project `.env` file).

> **Tip:** Start with `standalone+api` unless you specifically need
> storage-backed async processing with SeaweedFS and MQTT.

### Run in Docker (Recommended)

The container image starts the service and reads its configuration from `/app/config/patterns.yaml`. Mount your own `patterns.yaml` to override the built-in example.

Before starting, complete deployment-specific settings in [Configuration Guide](./get-started/configuration.md).

The project `docker-compose.yml` starts the behavioral-analysis service. In the default `standalone+api` mode, it also starts `ovms-vlm`, so VLM model files must be present before launch. Ensure that the Docker network can reach all dependencies required by your selected deployment mode.

Full guide: [Run with Docker Compose](./get-started/run-container.md)

### Run on the Host

Run the service directly with Python. This path is useful for development and testing.

Before starting, complete deployment-specific settings in [Configuration Guide](./get-started/configuration.md).

Full guide: [Run Standalone](./get-started/run-standalone.md)

## Verify

Once the service is running, check that it is ready by monitoring logs and confirming mode-specific connectivity.

The service logs key startup events:

```text
INFO: Behavioral Analysis Service starting...
INFO: Loading YOLO-Pose model from /models/yolo_models/yolo26n-pose/yolo26n-pose.xml
INFO: SeaweedFS bucket health check passed
INFO: MQTT Consumer connected, subscribed to ba/requests
INFO: Service ready for analysis requests
```

For `seaweedfs+mqtt` mode, ensure the upstream system publishes requests to the `ba/requests` topic; the service publishes results to `ba/results`.

For `standalone+api` mode, send a test request to `POST /api/v1/analyze/batch` and confirm a valid JSON response.

Startup logs confirm process readiness only; they do not validate deployment-specific configuration correctness.

## Next Steps

- [Configuration Guide](./get-started/configuration.md) — Customize patterns and environment variables
- [How It Works](./how-it-works.md) — Detailed architecture and request lifecycle
- [API Reference](./api-reference.md) — MQTT message schemas
- [Troubleshooting](./troubleshooting.md) — Common issues and solutions

<!--hide_directive
:::{toctree}
:hidden:

./get-started/build-from-source.md
./get-started/configuration.md
./get-started/run-container.md
./get-started/run-standalone.md
./get-started/system-requirements.md

:::
hide_directive-->
