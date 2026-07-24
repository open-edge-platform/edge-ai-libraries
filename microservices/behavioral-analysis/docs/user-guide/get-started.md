# Get Started with the Behavioral Analysis Service

This page is the entry point for running the Behavioral Analysis Service.

For a detailed overview of the service architecture, capabilities, and design, see [How It Works](./index.md).

---

## Before You Begin

- Confirm that your machine meets the [System Requirements](./get-started/system-requirements.md).
- Ensure required dependencies are reachable: MQTT broker, SeaweedFS S3-compatible storage, and (if VLM is enabled) OpenVINO Model Server (OVMS).
- Obtain the **YOLO-Pose model** in OpenVINO IR format (`.xml` + `.bin`)
- Review [Configuration Guide](./get-started/configuration.md) before starting deployment.

---

## Configure the Service

All runtime behavior is driven by **environment variables and one YAML pattern file**:

> [!IMPORTANT]
> Configuration is mandatory for all runs: quick start, Docker deployment, and host deployment.
> The service may start with default values, but successful analysis requires deployment-specific configuration.

See [Configuration Guide](./get-started/configuration.md) for the full pattern DSL, environment variables, and VLM settings.

---

## Choose Deployment Path

### Run in Docker (Recommended)

The container image starts the service and reads its config from `/app/config/patterns.yaml`. Mount your own `patterns.yaml` to override the built-in example.

Before starting, complete deployment-specific settings in [Configuration Guide](./get-started/configuration.md).

The project `docker-compose.yml` starts the behavioral-analysis service. Ensure its Docker network is configured to communicate with your SeaweedFS, MQTT, and OVMS containers.

Full guide: [Run with Docker Compose](./get-started/run-container.md)

### Run on the Host

Run the service directly with Python. This path is useful for development and testing.

Before starting, complete deployment-specific settings in [Configuration Guide](./get-started/configuration.md).

Full guide: [Run Standalone](./get-started/run-standalone.md)

---

## Verify

Once the service is running, check that it's ready by monitoring logs and confirming MQTT connectivity.

The service logs key startup events:

```
INFO: Behavioral Analysis Service starting...
INFO: Loading YOLO-Pose model from /models/yolo_models/yolo26n-pose/yolo26n-pose.xml
INFO: SeaweedFS bucket health check passed
INFO: MQTT Consumer connected, subscribed to ba/requests
INFO: Service ready for analysis requests
```

Ensure the upstream system publishes requests to the `ba/requests` topic; the service will publish results to `ba/results`.

Startup logs confirm process readiness only; they do not validate deployment-specific configuration correctness.

---

## Next Steps

- [Configuration Guide](./get-started/configuration.md) — Customize patterns and environment variables
- [How It Works](./index.md) — Detailed architecture and request lifecycle
- [API Reference](./api-reference.md) — MQTT message schemas
- [Troubleshooting](./troubleshooting.md) — Common issues and solutions
