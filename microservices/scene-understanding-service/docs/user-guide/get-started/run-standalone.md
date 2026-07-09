# Run On the Host

Use this path when you want to run the service directly with Python on the
host, typically for development.

## Prerequisites

### Python Setup

The service uses [`uv`](https://docs.astral.sh/uv/) and Python 3.11+. From the
`scene-understanding-service/` directory:

```bash
uv sync
```

This creates a virtual environment and installs the dependencies declared in
`pyproject.toml`.

### Config

- Edit `configs/scene-config.yaml` and `configs/rules.yaml`. For details, see
  the [Configuration Guide](./configuration.md).
- When running on the host (no `/app/configs`), the service automatically
  falls back to the `configs/` directory next to the source. Set `CONFIG_DIR`
  to point elsewhere if needed.
- Supply SceneScape credentials via environment variables:

  ```bash
  export SCENESCAPE_API_USER=admin
  export SCENESCAPE_API_PASSWORD=...   # type secrets directly; do not commit
  ```

## Running the Service

### Start

```bash
uv run python main.py
```

Default bind address:

- host: `0.0.0.0`
- port: `8082`

Equivalent `uvicorn` command:

```bash
uv run uvicorn main:app --host 0.0.0.0 --port 8082
```

### Verify

```bash
curl --noproxy '*' http://127.0.0.1:8082/health
curl --noproxy '*' http://127.0.0.1:8082/api/v1/lp/status
```

## Running Tests

```bash
uv run pytest tests/ -v
```

## API Use Cases and Examples

For endpoint details and examples, see the [API Reference](../api-reference.md).

## Notes

- The service performs SceneScape zone discovery at startup and then
  subscribes to the configured MQTT topics.
- There is no hard startup dependency on SceneScape — the MQTT connection is
  retried in the background.
- Behavioral analysis and evidence capture require the optional `seaweedfs`
  block and a reachable behavioral-analysis worker; otherwise leave them out.
