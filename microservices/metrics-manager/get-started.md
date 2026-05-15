# Get Started

This guide provides step-by-step instructions to install and run Metrics Manager on your machine using Docker Compose.

## Prerequisites

**System Requirements**

- **OS**: Linux (kernel 5.4+) — Ubuntu 22.04 LTS, Debian 12, or RHEL 9 recommended
- **Docker**: 24.0+ (`docker --version`)
- **Docker Compose**: 2.20+ (`docker compose version`)
- **RAM**: 512 MB free (for service + Telegraf)
- **Disk**: 2 GB free (for Docker image build)

> **Note:** The service uses Linux-specific paths (`/sys`, `/proc`, `/dev/dri`). It cannot collect system metrics on Windows or macOS hosts, but the REST API and SSE streaming work on any platform.

**Optional Hardware**

| Hardware | Collected Metrics |
|----------|-------------------|
| Any CPU | CPU usage, frequency, temperature |
| Any RAM | Memory usage |
| Intel Arc GPU | GPU engine usage, frequency, power |
| Intel NPU (MTL/ARL/LNL/PTL) | NPU power, frequency, temperature, utilization |

If Intel GPU or NPU is absent, the service starts normally — those metric sources are silently skipped.

---

## Quick Start

### Step 1: Clone the Repository

```bash
git clone https://github.com/open-edge-platform/edge-ai-libraries.git
cd edge-ai-libraries/metrics-manager
```

### Step 2: Configure Environment

Copy the example configuration file:

```bash
cp .env.example .env
```

The defaults work out of the box. Edit `.env` only if you need to change ports or have a corporate proxy.

**Key settings in `.env`:**

```bash
# Host ports (change if something already uses 9090, 9273, or 8186)
HOST_METRICS_PORT=9090          # Metrics Manager REST API + SSE
HOST_TELEGRAF_PORT=9273         # Telegraf Prometheus endpoint
HOST_TELEGRAF_HTTP_PORT=8186    # Telegraf HTTP listener (InfluxDB Line Protocol)

# Logging
LOG_LEVEL=INFO                  # DEBUG | INFO | WARNING | ERROR
```

### Step 3: (If behind a corporate proxy) Set Proxy Variables

Uncomment and fill in the proxy section in `.env`:

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

## Verify the Installation

Run these checks after the container starts:

### 1. Service Health

```bash
curl http://localhost:9090/health
```

Expected output:
```json
{
  "status": "healthy",
  "version": "2026.1.0",
  "uptime_seconds": 3600.5,
  "checks": {"store": true}
}
```

### 2. Detailed Status

```bash
curl http://localhost:9090/api/health
```

Shows connected clients, store statistics, and Telegraf endpoint.

### 3. System Metrics from Telegraf

```bash
curl http://localhost:9273/metrics | head -30
```

Should show CPU, memory, temperature, and GPU/NPU metrics (if available).

### 4. Push a Custom Metric

```bash
curl -X POST http://localhost:9090/api/v1/metrics/simple \
  -H "Content-Type: application/json" \
  -d '{"name": "install_test", "value": 1.0}'
```

Expected response: `{"accepted": 1, ...}`

### 5. Read the Metric Back

```bash
curl http://localhost:9090/api/v1/metrics/latest
```

Should show your `install_test` metric.

---

## Common Setup Variants

### Without Intel GPU (no qmassa)

No changes needed. The container starts qmassa, which logs `No DRM devices found` and exits. The qmassa reader (`scripts/qmassa_reader.py`) detects the missing FIFO, logs one warning, then sleeps silently. Other metrics continue normally.

### Without Intel NPU

No changes needed. The NPU reader (`scripts/npu_reader.py`) detects the missing `intel_vpu` driver, logs a single warning, and enters idle mode. This prevents Telegraf from restarting the reader. CPU, RAM, GPU, and temperature metrics continue normally.

### Custom Host Ports

If ports 9090, 9273, or 8186 are already in use, override them in `.env`:

```bash
HOST_METRICS_PORT=19090
HOST_TELEGRAF_PORT=19273
HOST_TELEGRAF_HTTP_PORT=18186
```

Then access the service on the new ports:

```bash
curl http://localhost:19090/health
```

### Custom Telegraf Configuration

To use your own Telegraf config instead of the default:

```bash
TELEGRAF_CONFIG=./my-telegraf.conf docker compose up
```

Or set permanently in `.env`:

```bash
TELEGRAF_CONFIG=./my-telegraf.conf
```

To add inputs on top of the default config, drop `.conf` files in the `telegraf.d/` directory:

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

## Next Steps

- **Push metrics**: See [API Reference](./docs/user-guide/api-reference.md) for all ingestion formats
- **Stream live**: Open `http://localhost:9090/metrics/stream` in a browser for a live HTML table
- **Configure**: See [Configuration Guide](./docs/user-guide/get-started/environment-variables.md) for all tuning options
- **Custom metrics**: See [Custom Metrics Scripts](./docs/user-guide/get-started/custom-metrics.md) for easy metric collection
- **Kubernetes**: See [Helm Deployment](./docs/user-guide/get-started/deploy-with-helm.md) for production deployments
- **Troubleshoot**: See [Troubleshooting](./docs/user-guide/troubleshooting.md) for common issues

---

## Stopping and Removing

```bash
# Stop the service
docker compose down

# Stop and remove volumes (clears stored custom metrics)
docker compose down -v

# Remove built images
docker compose down --rmi local
```

---

## Exposed Ports Reference

| Port | Protocol | Description |
|------|----------|-------------|
| `9090` | HTTP / SSE | Metrics Manager REST API, SSE stream (`/metrics/stream`) |
| `9273` | HTTP | Telegraf Prometheus endpoint (system + custom metrics) |
| `8186` | HTTP | Telegraf HTTP listener (InfluxDB Line Protocol direct write) |

## Directory Reference

| Path (host) | Path (container) | Purpose |
|-------------|------------------|---------|
| `./telegraf.conf` | `/etc/telegraf/telegraf.conf` | Default Telegraf configuration |
| `./telegraf.d/` | `/etc/telegraf/telegraf.d/` | Additional Telegraf configs (drop-in) |
| Docker volume `custom-metrics` | `/app/custom-metrics` | Persistent storage for custom metric scripts |
| `/sys` (host) | `/sys:ro` | Kernel sysfs for temperature, NPU, CPU frequency |
| `/run` (host) | `/run:ro` | Runtime socket access |
| `/dev/dri` (host) | `/dev/dri` | GPU device access for Intel Arc metrics |

## License

Copyright (C) 2025-2026 Intel Corporation

SPDX-License-Identifier: Apache-2.0

## Supporting Resources

- [Installation Guide](./docs/user-guide/get-started/installation.md)
- [System Requirements](./docs/user-guide/get-started/system-requirements.md)
- [Testing Guide](./docs/user-guide/get-started/testing.md)
- [Building from Source](./docs/user-guide/get-started/build-from-source.md)
- [Configuration Guide](./docs/user-guide/get-started/environment-variables.md)
- [Custom Metrics Scripts](./docs/user-guide/get-started/custom-metrics.md)
- [Helm Deployment](./docs/user-guide/get-started/deploy-with-helm.md)
- [API Reference](./docs/user-guide/api-reference.md)
- [Troubleshooting](./docs/user-guide/troubleshooting.md)
