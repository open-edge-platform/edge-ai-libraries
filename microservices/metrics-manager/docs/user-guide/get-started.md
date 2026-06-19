# Get Started

This guide provides step-by-step instructions to install and run Metrics Manager on your machine using Docker Compose.

## Prerequisites

- **Docker**: 24.0+ (`docker --version`)
- **Docker Compose**: 2.20+ (`docker compose version`)
- **Linux**: Kernel 5.4+ (for system metrics collection)
- **RAM**: 512 MB free
- **Disk**: 2 GB free (for Docker image build)

See [System Requirements](./get-started/system-requirements.md) for detailed hardware/software requirements.

---

## Pre-built Image (Optional)

Instead of building from source, you can pull the pre-built Docker image from the registry:

```bash
docker pull intel/metrics-manager:2026.1.0
```

The image is based on `python:3.12-slim` and includes:

- Telegraf 1.37.3 (system metrics agent)
- qmassa 1.3.1 (Intel® GPU telemetry)
- Intel® NPU reader (`npu_reader.py`)
- Python 3.12 runtime with FastAPI
- supervisord process manager

**GPU/NPU Drivers:** No proprietary drivers are bundled in the image. GPU and NPU metrics are read directly from sysfs (`/sys/`) at runtime, so no additional setup is needed on the host beyond accessing `/dev/dri/*` for GPUs.

**Next:** You can now run the image directly with `docker run` (see [Running Without Docker Compose](#running-without-docker-compose-docker-run) below), or continue below to build from source using Docker Compose.

---

## Installation Steps

### Step 1: Clone the Repository

```bash
git clone https://github.com/open-edge-platform/edge-ai-libraries.git -b main
cd edge-ai-libraries/metrics-manager
```

### Step 2: Configure Environment

Copy the example configuration file:

```bash
cp .env.example .env
```

The defaults work out of the box. Edit `.env` only if needed.

**Key settings:**

```bash
# Host ports (change if already in use)
HOST_METRICS_PORT=9090          # Metrics Manager REST API + SSE
HOST_TELEGRAF_PORT=9273         # Telegraf Prometheus endpoint
HOST_TELEGRAF_HTTP_PORT=8186    # Telegraf HTTP listener (InfluxDB Line Protocol)

# Logging
LOG_LEVEL=INFO                  # DEBUG | INFO | WARNING | ERROR
```

### Step 3: (Optional) Set Proxy Variables

If behind a corporate proxy, uncomment in `.env`:

```bash
http_proxy=http://proxy.example.com:8080
HTTP_PROXY=http://proxy.example.com:8080
https_proxy=http://proxy.example.com:8080
HTTPS_PROXY=http://proxy.example.com:8080
no_proxy=localhost,127.0.0.1
NO_PROXY=localhost,127.0.0.1
```

This passes proxy settings both to the Docker build and to the running container.

### Step 4: Build and Start

```bash
docker compose up --build
```

First build takes 3–10 minutes (downloads Rust toolchain to compile qmassa, Telegraf .deb, Python packages). Subsequent builds are cached and take under a minute.

To run in the background:

```bash
docker compose up --build -d
```

---

## Running Without Docker Compose (docker run)

If you prefer to run the container directly with `docker run` instead of Docker Compose, use the commands below. The image is pre-configured with all dependencies and environment defaults.

### Prerequisites for docker run

- **Docker**: 24.0+ (no Docker Compose needed)
- **Linux**: Kernel 5.4+
- **Host paths**: `/sys`, `/run`, and optionally `/dev/dri` must be accessible

### Minimal Setup (CPU + Memory + Temperature Only)

```bash
docker run --rm \
  -p 9090:9090 \
  -p 9273:9273 \
  -v /sys:/sys:ro \
  -v /run:/run:ro \
  --pid host \
  intel/metrics-manager:2026.1.0
```

Then verify:

```bash
curl http://localhost:9090/health
curl -s http://localhost:9273/metrics | head
```

### With Intel Arc GPU Support

Add `--device /dev/dri` so qmassa can access GPU devices:

```bash
docker run --rm \
  --device /dev/dri \
  -p 9090:9090 \
  -p 9273:9273 \
  -v /sys:/sys:ro \
  -v /run:/run:ro \
  --pid host \
  intel/metrics-manager:2026.1.0
```

Verify GPU metrics:

```bash
curl -s http://localhost:9273/metrics | grep gpu
```

### With Intel NPU Support

Run in privileged mode to access `/sys/class/intel_pmt`:

```bash
docker run --rm --privileged \
  -p 9090:9090 \
  -p 9273:9273 \
  -v /sys:/sys:ro \
  -v /run:/run:ro \
  --pid host \
  intel/metrics-manager:2026.1.0
```

Verify NPU metrics:

```bash
curl -s http://localhost:9273/metrics | grep npu
```

### With Both GPU and NPU

```bash
docker run --rm --privileged \
  --device /dev/dri \
  -p 9090:9090 \
  -p 9273:9273 \
  -v /sys:/sys:ro \
  -v /run:/run:ro \
  --pid host \
  intel/metrics-manager:2026.1.0
```

### With Custom Ports

Map to different host ports:

```bash
docker run --rm \
  -p 19090:9090 \
  -p 19273:9273 \
  -v /sys:/sys:ro \
  -v /run:/run:ro \
  --pid host \
  intel/metrics-manager:2026.1.0
```

Then access on the new ports:

```bash
curl http://localhost:19090/health
```

### With Environment Variables

Pass configuration via `-e`:

```bash
docker run --rm \
  -p 9090:9090 \
  -p 9273:9273 \
  -e LOG_LEVEL=DEBUG \
  -e CORS_ORIGINS=http://localhost:3000 \
  -e METRICS_RETENTION_SECONDS=600 \
  -v /sys:/sys:ro \
  -v /run:/run:ro \
  --pid host \
  intel/metrics-manager:2026.1.0
```

See [Environment Variables](./get-started/environment-variables.md) for all available variables.

### With Custom Metrics Directory (Volume Mount)

To persist custom metric scripts across container restarts, mount a volume:

```bash
mkdir -p ./my-scripts

docker run --rm \
  -p 9090:9090 \
  -p 9273:9273 \
  -v /sys:/sys:ro \
  -v /run:/run:ro \
  -v ./my-scripts:/app/custom-metrics \
  --pid host \
  intel/metrics-manager:2026.1.0
```

Drop your scripts in `./my-scripts/` (they must be executable: `chmod +x script.sh`).

### Background Execution

Run in the background:

```bash
docker run -d \
  --name metrics-manager \
  -p 9090:9090 \
  -p 9273:9273 \
  -v /sys:/sys:ro \
  -v /run:/run:ro \
  --pid host \
  intel/metrics-manager:2026.1.0
```

Stop it:

```bash
docker stop metrics-manager
docker rm metrics-manager
```

View logs:

```bash
docker logs -f metrics-manager
```

---

## Verify the Installation

Run these checks after the container starts:

### 1. Service Health

```bash
curl http://localhost:9090/health
```

Expected response: `{"status": "healthy", ...}`

### 2. System Metrics

```bash
curl http://localhost:9273/metrics | head -30
```

Should show CPU, memory, temperature metrics.

### 3. Push a Test Metric

```bash
curl -X POST http://localhost:9090/api/v1/metrics/simple \
  -H "Content-Type: application/json" \
  -d '{"name": "install_test", "value": 1.0}'
```

Expected response: `{"accepted": 1, ...}`

### 4. Query the Metric

```bash
curl http://localhost:9090/api/v1/metrics/latest
```

Should show your `install_test` metric.

---

## Installation Variants

### Custom Host Ports

If ports 9090, 9273, or 8186 are in use, override them in `.env`:

```bash
# .env
HOST_METRICS_PORT=19090
HOST_TELEGRAF_PORT=19273
HOST_TELEGRAF_HTTP_PORT=18186
```

Then access the service on the new ports:

```bash
curl http://localhost:19090/health
```

### Custom Telegraf Configuration

Use your own Telegraf config:

```bash
TELEGRAF_CONFIG=./my-telegraf.conf docker compose up
```

Or set permanently in `.env`:

```bash
TELEGRAF_CONFIG=./my-telegraf.conf
```

### Add Inputs on Top of Default Config

Drop `.conf` files in `telegraf.d/`:

```bash
mkdir -p telegraf.d

cat > telegraf.d/my-input.conf << 'EOF'
[[inputs.exec]]
  commands = ["/app/custom-metrics/my-sensor.sh"]
  interval = "5s"
  data_format = "influx"
EOF

docker compose up --build
```

### Restrict CORS Origins

By default all origins are allowed (`CORS_ORIGINS=*`). To restrict:

```bash
# .env
CORS_ORIGINS=http://my-dashboard.local:3000,http://localhost:3000
```

---

## Stopping and Removing

```bash
# Stop the service
docker compose down

# Stop and remove volumes (clears custom metrics)
docker compose down -v

# Remove built images
docker compose down --rmi local
```

---

## Exposed Ports

| Port   | Protocol   | Description                                            |
| ------ | ---------- | ------------------------------------------------------ |
| `9090` | HTTP / SSE | Metrics Manager REST API, SSE stream                   |
| `9273` | HTTP       | Telegraf Prometheus endpoint (system + custom metrics) |
| `8186` | HTTP       | Telegraf HTTP listener (InfluxDB Line Protocol)        |

---

## Troubleshooting Installation

| Issue                 | Solution                                                 |
| --------------------- | -------------------------------------------------------- |
| Port already in use   | Change ports in `.env` (e.g., `HOST_METRICS_PORT=19090`) |
| Build fails           | Run `docker builder prune` to clear cache                |
| Container won't start | Check logs: `docker logs metrics-manager`                |
| No GPU/NPU metrics    | Expected if hardware not present; other metrics continue |

See [Troubleshooting](./troubleshooting.md) for more issues.

---

## Next Steps

- **Push metrics**: See [API Reference](./api-reference.md)
- **Stream live**: Open `http://localhost:9090/metrics/stream` in a browser
- **Configure**: See [Environment Variables](./get-started/environment-variables.md)
- **Custom metrics**: See [Custom Metrics Scripts](./get-started/custom-metrics.md)
- **Kubernetes**: See [Helm Deployment](./get-started/deploy-with-helm.md)

## Supporting Resources

- [System Requirements](./get-started/system-requirements.md)
- [Building from Source](./get-started/build-from-source.md)
- [Troubleshooting](./troubleshooting.md)

## License

Copyright (C) 2025-2026 Intel Corporation

SPDX-License-Identifier: Apache-2.0

<!--hide_directive
:::{toctree}
:hidden:

./get-started/system-requirements.md
./get-started/build-from-source.md
./get-started/deploy-with-helm.md
./get-started/environment-variables.md
./get-started/custom-metrics.md
./get-started/testing.md

:::
hide_directive-->
