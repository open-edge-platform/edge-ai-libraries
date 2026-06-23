# Get Started

This page is the entry point for running the Alert Service microservice. Pick one of the two deployment paths and follow the linked guide.

## Before You Begin

- Confirm that your machine meets the [System Requirements](./get-started/system-requirements.md).
- Review the [Configuration Guide](./get-started/configuration.md) to understand subscription rules, deduplication windows, and delivery handlers.

## Choose Deployment Path

<!--hide_directive::::{tab-set}
:::{tab-item}hide_directive--> **Run in Docker (Recommended)**
<!--hide_directive:sync: Docker hide_directive-->

The container setup exposes the API on host port `8000`. By default, starting with `MQTT_MODE=embedded` launches a Mosquitto broker side-by-side with the alert service.

See [Run with Docker Compose](./get-started/run-container.md) for the full step-by-step guide.

Quick start:

```bash
make init-env        # creates .env from example template
make build           # builds the Docker image
make up              # starts containers (runs on port 8000)
curl http://localhost:8000/api/v1/health
```

<!--hide_directive:::
:::{tab-item}hide_directive--> **Run on the Host**
<!--hide_directive:sync: Host hide_directive-->

Run the service directly with Python. This path is useful for local development, debugging, and running tests.

See [Run on the Host](./get-started/run-standalone.md) for the full step-by-step guide.

Quick start:

```bash
make init-env        # creates .env from example template
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn src.main:app --host 127.0.0.1 --port 8000
```
<!--hide_directive:::
::::hide_directive-->

## Verify

Once the service is running:

```bash
curl http://localhost:8000/api/v1/health
```

Expected response:

```json
{"status": "healthy"}
```

## Next Steps

- [API Reference](./api-reference.md) for endpoint details and payload examples.
- [Configuration Guide](./get-started/configuration.md) to customize subscriptions and delivery routes.
- [Troubleshooting](./troubleshooting.md) for common startup, MQTT, or WebSocket issues.

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
