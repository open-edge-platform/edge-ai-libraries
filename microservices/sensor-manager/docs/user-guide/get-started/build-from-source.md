# Build from Source

## Build the Docker Image

```bash
cd edge-ai-libraries/microservices/sensor-manager
make build            # uses REGISTRY and TAG from .env
```

To build the image directly:

```bash
docker build -f docker/Dockerfile -t intel/sensor-manager:latest .
```

## Run Locally without Docker

```bash
uv sync --frozen --extra dev
SENSOR_MANAGER_PORT=8090 uv run python -m src
```

USB discovery requires `v4l2-ctl` (the `v4l-utils` package), and your user must be able to open
`/dev/video*` devices (member of the `video` group).

## Run Tests and Linters

```bash
make test       # unit tests
make coverage   # tests with coverage report in coverage/
make lint       # ruff check and format check
```

## Update the dlstreamer.onvif Library

The library is pinned to a DL Streamer commit in `pyproject.toml`
(`[tool.uv.sources] intel-dlstreamer`). To update it, change `rev` to the new commit SHA, run
`uv lock`, then run the tests and commit both `pyproject.toml` and `uv.lock`.
