# Metrics Manager

A unified metrics collection, ingestion, and relay service that combines Telegraf-based system metrics with a flexible REST API for custom metrics. Supports multiple input formats including JSON, InfluxDB Line Protocol, and OpenTelemetry (OTLP).

- **Get Started:** [docs/user-guide/get-started.md](docs/user-guide/get-started.md) — install and run in 5 minutes
- **Full Documentation:** [docs/user-guide/index.md](docs/user-guide/index.md)
- **Source code & docs:** <https://github.com/open-edge-platform/edge-ai-libraries/tree/main/metrics-manager>
- **Issues / feature requests:** <https://github.com/open-edge-platform/edge-ai-libraries/issues> (use the `metrics-manager` label)
- **Container image (Docker Hub):** [`intel/metrics-manager`](https://hub.docker.com/r/intel/metrics-manager) - tagged `intel/metrics-manager:<VERSION>` (e.g. `intel/metrics-manager:2026.1.0`)
- **Helm chart (OCI):** `oci://registry-1.docker.io/intel/metrics-manager:<VERSION>-helm` (see [docs/user-guide/deploy-with-helm.md](docs/user-guide/deploy-with-helm.md))

## Features

- **System Metrics Collection**: CPU, memory, temperature, GPU (Intel GPUs via qmassa), Intel NPU (via PMT sysfs)
- **Optional GPU exporter**: bundled `qmmd` Prometheus exporter (opt-in, see [docs/user-guide/get-started/environment-variables.md](docs/user-guide/get-started/environment-variables.md))
- **REST API**: Push custom metrics via JSON, InfluxDB Line Protocol, or OpenTelemetry format
- **SSE Streaming**: Real-time metrics streaming via Server-Sent Events (`GET /metrics/stream`)
- **Prometheus Compatible**: Metrics endpoint for Prometheus scraping
- **Custom Telegraf Config**: Mount your own Telegraf configuration
- **Rate Limiting**: IP-based request throttling with configurable limits
- **Correlation IDs**: Distributed tracing support with automatic ID propagation
- **Structured Logging**: JSON-formatted logs for log aggregators (ELK, Loki)
- **Memory Protection**: Automatic eviction when memory limits reached
- **Graceful Shutdown**: Clean handling of SIGTERM/SIGINT signals

## Architecture

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                              Metrics Manager                                     │
│                                                                                  │
│  ┌─────────────┐    ┌──────────────────┐    ┌───────────────────────────────┐    │
│  │  Telegraf   │    │     FastAPI      │    │       Custom Metrics          │    │
│  │  (System)   │--->│      Server      │<---│       REST API                │    │
│  │             │    │                  │    │                               │    │
│  │ • CPU       │    │ /metrics/stream  │    │ POST /api/v1/metrics          │    │
│  │ • Memory    │    │ /metrics         │    │ POST /api/v1/metrics/simple   │    │
│  │ • Temp      │    │ /health          │    │ POST /api/v1/metrics/influx   │    │
│  │ • GPU       │    │                  │    │ POST /api/v1/metrics/otlp     │    │
│  │ • NPU       │    │                  │    │                               │    │
│  └─────────────┘    └────────┬─────────┘    └───────────────────────────────┘    │
│                              │                                                   │
│                              ▼                                                   │
│                      ┌───────────────┐                                           │
│                      │  SSE Clients  │                                           │
│                      │  (dashboards) │                                           │
│                      └───────────────┘                                           │
│                                                                                  │
│  Ports:                                                                          │
│  • 9090: Metrics Manager API + SSE                                               │
│  • 9273: Telegraf Prometheus metrics                                             │
│  • 8186: Telegraf HTTP listener (InfluxDB Line Protocol)                         │
└──────────────────────────────────────────────────────────────────────────────────┘
```

## Quick Start

### Prerequisites

```bash
cd siv-telemetry/metrics-manager

# (Optional) If behind a proxy, edit .env and uncomment proxy settings
```

> **Note:** The Docker build automatically resolves Python dependencies.
> No local `uv lock` or Python installation is required.

### Pulling the published image (no build required)

Released images are published to Docker Hub as `intel/metrics-manager`:

```bash
docker pull intel/metrics-manager:2026.1.0
```

Pick the run invocation that matches your hardware:

**Minimal — CPU + memory + temperature only:**

```bash
docker run --rm \
  -p 9090:9090 -p 9273:9273 \
  -v /sys:/sys:ro -v /run:/run:ro \
  --pid host \
  intel/metrics-manager:2026.1.0
```

**With Intel® GPU telemetry** (adds `--device /dev/dri` so qmassa can
enumerate render nodes):

```bash
docker run --rm \
  --device /dev/dri \
  -p 9090:9090 -p 9273:9273 \
  -v /sys:/sys:ro -v /run:/run:ro \
  --pid host \
  intel/metrics-manager:2026.1.0
```

**With Intel® NPU telemetry** (NPU readings come from the `intel_pmt`
sysfs interface, which requires `--privileged`):

```bash
docker run --rm --privileged \
  -p 9090:9090 -p 9273:9273 \
  -v /sys:/sys:ro -v /run:/run:ro \
  --pid host \
  intel/metrics-manager:2026.1.0
```

> On hosts that have **both** an Intel® GPU and NPU, add `--device
> /dev/dri` to the NPU command above to enable qmassa as well.

On hosts without an Intel® GPU or NPU the corresponding readers detect
the missing hardware, log a single warning, and idle silently — other
metrics (CPU, memory, temperature) continue normally.

Then verify:

```bash
curl http://localhost:9090/health
curl -s http://localhost:9273/metrics | head
```

### Using Docker Compose

```bash
docker compose up --build

# Run with custom Telegraf configuration
TELEGRAF_CONFIG=./my-telegraf.conf docker compose up

# Run in background
docker compose up -d
```

### Using Docker

```bash
docker build -t metrics-manager .

docker run -d \
  --name metrics-manager \
  --privileged \
  -p 9090:9090 \
  -p 9273:9273 \
  -v /sys:/sys \
  -v /dev:/dev \
  metrics-manager
```

### On Kubernetes (Helm)

The same release is published as a Helm chart at the same OCI repository,
distinguished by the `-helm` tag suffix:

```bash
helm install metrics-manager \
  oci://registry-1.docker.io/intel/metrics-manager \
  --version 2026.1.0-helm \
  --namespace observability --create-namespace
```

The chart exposes Telegraf and the REST/SSE API as a `Service`, supports
`Deployment` or `DaemonSet` mode, and integrates with Prometheus Operator
via an opt-in `ServiceMonitor`. See [docs/user-guide/deploy-with-helm.md](docs/user-guide/deploy-with-helm.md) for the
complete reference.

## Building the Image

The image version is the **single source of truth** in [`VERSION`](VERSION) (currently
`2026.1.0`). Locally-built images are tagged `metrics-manager:<VERSION>` (no
registry prefix); the **official released image** on Docker Hub is
`intel/metrics-manager:<VERSION>`. Neither tag is `:latest` by default.

### With Make (recommended)

```bash
make version            # → 2026.1.0
make build              # → metrics-manager:2026.1.0    (local build)
make up                 # docker compose up -d
make logs               # tail container logs
make down               # stop & remove
make test               # build test image and run pytest
make clean              # remove built images, volumes, orphaned containers
make bump NEW=2026.2.0  # update VERSION + every file that mirrors it

# Helm chart (requires the `helm` CLI)
make helm-lint          # helm lint helm/metrics-manager
make helm-template      # render the chart with default values
make helm-package       # build dist/helm/metrics-manager-<VERSION>-helm.tgz
make generate-helm      # alias: helm-lint + helm-package
make helm-push          # push the packaged chart to oci://registry-1.docker.io/intel

# Override the tag for a one-off local build (e.g. a feature branch image)
make build TAG=dev      # → metrics-manager:dev

# Build with the published Docker Hub naming (matches what we release)
REGISTRY=intel/ make build              # → intel/metrics-manager:2026.1.0
```

### With Docker Compose directly

```bash
# Uses the TAG from .env (defaults to 2026.1.0)
docker compose build metrics-manager

# Override on the command line
TAG=2026.2.0-rc1 docker compose build metrics-manager

# Build and run in one step
docker compose up --build -d
```

### Releasing a new version

1. **Bump everywhere with one command** — `make bump NEW=2026.2.0` updates
   `VERSION`, `pyproject.toml`, `.env`, `.env.example`, `compose.yaml`,
   `app/settings.py`, `app/logging_config.py` and `docs/DOCKERHUB.md` in
   one go (see [Why so many files?](#why-so-many-files) below).
2. Review the change: `git diff`.
3. `make build` — the image will be tagged `metrics-manager:2026.2.0` and the
   OCI label `org.opencontainers.image.version` will be stamped automatically
   from the `VERSION` build arg.
4. Verify the running service reports the new version:

   ```bash
   curl -s http://localhost:9090/health | jq .version
   ```

5. Commit and (optionally) tag:

   ```bash
   git add -A && git commit -m "release: 2026.2.0" && git tag v2026.2.0
   ```

#### Why so many files?

`VERSION` is the single source of truth, but Python and Docker tooling
needs the value duplicated in a handful of places because each format is
read at a different time:

| File | Used by | When read |
|------|---------|-----------|
| `VERSION` | `Makefile`, `app/__init__.py` (dynamic) | Build time and runtime |
| `pyproject.toml` | `pip install .`, `python -m build` | Packaging |
| `.env` / `.env.example` | `docker compose` (without Make) | Build time |
| `compose.yaml` | `${TAG:-...}` and `VERSION:` build-arg fallbacks | Build time when no `TAG` env is set |
| `app/settings.py` | Pydantic default for `/health` `version` field | Runtime fallback when `SERVICE_VERSION` env var is unset |
| `app/logging_config.py` | Default `version` field in JSON log records | Runtime fallback |
| `docs/DOCKERHUB.md` | Long description published on the Docker Hub page | Manual sync at release time |
| `helm/metrics-manager/Chart.yaml` | Helm chart `version` (`<X.Y.Z>-helm`) and `appVersion` (`<X.Y.Z>`) | Build time when packaging the chart |

`make bump` keeps them all in sync so you don't have to remember.

### Verify

```bash
# Health check
curl http://localhost:9090/health

# Push a metric
curl -X POST http://localhost:9090/api/v1/metrics/simple \
  -H "Content-Type: application/json" \
  -d '{"name": "my_metric", "value": 42.5}'

# Read it back
curl http://localhost:9090/api/v1/metrics/latest
```

## Integration Examples

### Python Client

```python
import httpx

httpx.post("http://localhost:9090/api/v1/metrics/simple", json={
    "name": "inference_latency_ms",
    "value": 23.5,
    "tags": {"model": "yolov8", "device": "GPU"}
})
```

### SSE Client (real-time streaming)

```python
import httpx

with httpx.stream("GET", "http://localhost:9090/metrics/stream",
                  headers={"Accept": "text/event-stream"}) as r:
    for line in r.iter_lines():
        if line.startswith("data:"):
            print(line[5:])
```

Or open `http://localhost:9090/metrics/stream` in a browser for a live HTML dashboard.

### Grafana

1. Add data source: Prometheus
2. URL: `http://metrics-manager:9273`
3. Query example: `cpu_usage_percent{host="myhost"}`

### OpenTelemetry Collector

```yaml
exporters:
  otlphttp:
    endpoint: "http://metrics-manager:9090/api/v1/metrics/otlp"
service:
  pipelines:
    metrics:
      exporters: [otlphttp]
```

## Project Structure

```
metrics-manager/
├── app/                     # Python FastAPI application
│   ├── main.py              # Application entry with middleware
│   ├── settings.py          # Pydantic Settings configuration
│   ├── models.py            # Pydantic data models
│   ├── store.py             # Metrics storage with async persistence
│   ├── routes.py            # REST API routes
│   ├── sse.py               # SSE streaming endpoint (/metrics/stream)
│   ├── rate_limit.py        # Rate limiting middleware
│   ├── metrics.py           # Internal service metrics
│   ├── logging_config.py    # Structured logging setup
│   └── responses.py         # API response models
├── tests/                   # Pytest test suite
├── scripts/                 # System metrics scripts
├── helm/                    # Helm chart published as oci://.../metrics-manager:<VERSION>-helm
│   └── metrics-manager/
│       ├── Chart.yaml       # Chart metadata (version, appVersion)
│       ├── values.yaml      # Default values - all tunables
│       ├── .helmignore
│       └── templates/       # Deployment/DaemonSet, Service, ConfigMap,
│                            # PVC, ServiceAccount, ServiceMonitor, NOTES.txt
├── docs/                    # Detailed documentation
│   ├── API.md               # Full API reference
│   ├── ARCHITECTURE.md      # Architecture and data flow
│   ├── CONFIGURATION.md     # Environment variables and Telegraf config
│   ├── HELM.md              # Kubernetes deployment via the Helm chart
│   ├── INSTALLATION.md      # Step-by-step host setup
│   ├── TESTING.md           # Testing guide and smoke tests
│   └── TROUBLESHOOTING.md   # Common issues and solutions
├── telegraf.conf            # Default Telegraf config
├── compose.yaml             # Docker Compose config
├── Dockerfile               # Multi-stage Docker build
├── Makefile                 # Build / run / test targets (reads VERSION)
├── VERSION                  # Image version (single source of truth)
├── entrypoint.sh            # Container entrypoint
├── supervisord.conf         # Process management
└── pyproject.toml           # Python project config
```

## Documentation

| Document | Description |
|----------|-------------|
| [Get Started](docs/user-guide/get-started.md) | Quick start guide and installation instructions |
| [Installation](docs/user-guide/get-started/installation.md) | Step-by-step setup on a new machine, variants, integration examples |
| [System Requirements](docs/user-guide/get-started/system-requirements.md) | Supported platforms and hardware requirements |
| [Build from Source](docs/user-guide/get-started/build-from-source.md) | Building the metrics manager from source code |
| [Environment Variables](docs/user-guide/get-started/environment-variables.md) | Configuration through environment variables and Telegraf config |
| [Custom Metrics](docs/user-guide/get-started/custom-metrics.md) | Using the REST API for custom metrics |
| [Deploy with Helm](docs/user-guide/deploy-with-helm.md) | Kubernetes deployment via the published OCI Helm chart |
| [API Reference](docs/user-guide/api-reference.md) | All endpoints, formats, examples, response models |
| [How It Works](docs/user-guide/how-it-works.md) | Architecture, data flow, and component relationships |
| [Testing](docs/user-guide/get-started/testing.md) | Unit tests, smoke tests, development setup |
| [Troubleshooting](docs/user-guide/troubleshooting.md) | Common issues and solutions |
| [Release Notes](docs/user-guide/release-notes.md) | Version history and changelog |

## License

Copyright (C) 2025-2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0

## Reporting issues

Please open issues and feature requests in the upstream repository:
<https://github.com/open-edge-platform/edge-ai-libraries/issues>
(label them `metrics-manager`).
