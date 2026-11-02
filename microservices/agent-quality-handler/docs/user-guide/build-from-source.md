# Build from Source

The Compose deployment builds the standalone agent service from `docker/Dockerfile`.

## Prerequisites

- Docker 24.0 or later
- Docker Compose 2.20 or later
- [uv](https://docs.astral.sh/uv/) 0.10 or later for local development
- A reachable external storage API; see [Get Started](./get-started.md)

## Clone and Build

```bash
git clone https://github.com/open-edge-platform/edge-ai-libraries.git -b main
cd edge-ai-libraries/microservices/agent-quality-handler

docker compose -f docker/compose.yaml build aqh-agent
```

To create the locked local environment and run the tests:

```bash
uv sync --frozen --group test
uv run --frozen --group test pytest
```

Update `uv.lock` after intentionally changing dependencies with `uv lock`.

To build and start the default fallback deployment in one command:

```bash
./start.sh --build
```

Deployment defaults, including `STORAGE_SERVICE_URL` and `LLM_MODE`, are
maintained in the configuration section of [`start.sh`](../../start.sh).
Existing environment values override those defaults.

Stop the deployment while preserving named volumes:

```bash
./start.sh down
```

Stop the deployment and remove its named volumes:

```bash
./start.sh clean
```

The default deployment includes the agent and a private MQTT broker.
`aqh-ovms` and `model-download` are profile-gated services and are pulled as
images. Detection Service and storage are external services and are not built
by this project.

## Verify

```bash
docker compose -f docker/compose.yaml ps
curl http://localhost:5002/health
```

There is no multi-file `compose.base.yaml` deployment, UI, or Nginx layer in
this standalone service.
