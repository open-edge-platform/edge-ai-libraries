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
export STORAGE_SERVICE_URL=http://host.docker.internal:5001
docker compose -f docker/compose.yaml up --build -d
```

For LLM mode:

```bash
export STORAGE_SERVICE_URL=http://host.docker.internal:5001
export LLM_MODE=llm
docker compose -f docker/compose.yaml --profile llm up --build -d
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

There is no `setup.sh`, multi-file `compose.base.yaml` deployment, UI, or Nginx layer in this standalone service.
