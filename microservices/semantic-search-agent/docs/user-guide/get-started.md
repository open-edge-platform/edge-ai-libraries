# Get Started

This page is the entry point for running the Semantic Search Agent microservice. Pick one of the two deployment paths and follow the linked guide.

## Before You Begin

- Confirm that your machine meets the [System Requirements](./get-started/system-requirements.md).
- Review the [Configuration Guide](./get-started/configuration.md) to understand matching strategies, VLM backends, and caching options.
- Decide whether you need VLM support:
  - For **exact matching only**, no external model server is needed.
  - For **semantic or hybrid matching**, you need a configured VLM backend (OVMS, OpenVINO local, or OpenAI).

## Choose Deployment Path

<!--hide_directive::::{tab-set}
:::{tab-item}hide_directive--> **Run in Docker (Recommended)**
<!--hide_directive:sync: Docker hide_directive-->

The container setup exposes the API on host port `8080` and Prometheus metrics on port `9090`. An optional Redis container is included in the Compose file for persistent caching.

See [Run with Docker Compose](./get-started/run-container.md) for the full step-by-step guide.

Quick start:

```bash
cp .env.example .env        # copy and edit environment file
cd docker
docker compose build        # build the image
docker compose up -d        # start containers (API on port 8080)
curl http://localhost:8080/api/v1/health
```

<!--hide_directive:::
:::{tab-item}hide_directive--> **Run on the Host**
<!--hide_directive:sync: Host hide_directive-->

Run the service directly with Python. This path is useful for local development, debugging, and running tests.

See [Run on the Host](./get-started/run-standalone.md) for the full step-by-step guide.

Quick start:

```bash
cp .env.example .env        # copy and edit environment file
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8080
```
<!--hide_directive:::
::::hide_directive-->

## Verify

Once the service is running:

```bash
curl http://localhost:8080/api/v1/health
```

Expected response:

```json
{
  "status": "healthy",
  "service": "semantic-search-agent",
  "version": "2026.1.0",
  "vlm_backend": "ovms",
  "vlm_status": "connected",
  "uptime_seconds": 5.12
}
```

## Next Steps

- [API Reference](./api-reference.md) for endpoint details and payload examples.
- [Configuration Guide](./get-started/configuration.md) to customize matching strategies and VLM backends.
- [Troubleshooting](./troubleshooting.md) for common startup or VLM connectivity issues.

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
