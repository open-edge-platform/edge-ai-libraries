# Build From Source

This page covers building the Scene Understanding Service from source. Use
this path when you need a code change. To run the prebuilt image without
rebuilding, see [run-container.md](run-container.md).

## Prerequisites

- Verify the [system requirements](system-requirements.md).
- Clone the repository and `cd` into the `scene-understanding-service/`
  directory.

## Build the Docker Image

The service is designed to build standalone — the build context is the service
directory itself and the `rule_engine` is bundled in-tree, so there are no
external source dependencies.

```bash
docker build -t intel/scene-understanding-service:latest .
```

To build a locally tagged image for Compose:

```bash
docker build -t scene-understanding-service:local .
```

To build an image the bundled `docker-compose.yml` picks up via `.env`, tag it
to match the `REGISTRY` / `RELEASE_TAG` values you set there (see
[run-container.md](run-container.md)):

```bash
docker build -t intel/scene-understanding-service:2026.2.0-rc1 .
```

The `Dockerfile` copies the whole service into `/app` (including the sample
`configs/`), installs dependencies with `uv`, and runs as a non-root user
(UID 1000). The API is exposed on port `8082`.

## Build a Python Environment (Standalone)

Create a virtual environment and install dependencies from source with `uv`:

```bash
uv sync
uv run python main.py
```

## Verifying the Build

After building and starting the service, confirm:

```bash
curl --noproxy '*' http://127.0.0.1:8082/health
```

A `{"status": "healthy"}` response confirms the build is functional.
