<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

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

This checkout targets the unreleased 2026.3.0 version. Until that image is
published, use the build-from-source instructions. Registry examples below use
the target release tag.

Instead of building from source, you can pull the pre-built Docker image from the registry:

```bash
docker pull intel/metrics-manager:2026.3.0
```

The image uses a digest-pinned `python:3.12-slim-trixie` base (Debian 13) and includes:

- Telegraf 1.40.3 (system metrics agent)
- qmassa 2.1.0 (Intel® GPU telemetry)
- Native Go collectors: `mm-plugin-cpu`, `mm-plugin-gpu`, `mm-plugin-npu`,
  `mm-plugin-proc`, `mm-plugin-membw`, plus the opt-in `mm-plugin-rapl`
- Python 3.12 runtime with FastAPI
- supervisord process manager

**GPU/NPU prerequisites:** The host must provide the appropriate GPU/NPU drivers
and telemetry interfaces. GPU collection uses qmassa and can require DRM,
perf or MSR access; NPU telemetry requires supported PMT data and read
permissions. Installing an image does not supply host kernel drivers.
The extended build adds OpenVINO and VAAPI userspace tooling, not kernel
drivers. See [hardware-specific requirements](./get-started/system-requirements.md#hardware-specific-notes).

**Next:** You can now run the image directly with `docker run` (see [Running Without Docker Compose](#running-without-docker-compose-docker-run) below), or continue below to build from source using Docker Compose.

---

## Installation Steps

### Step 1: Clone the Repository

```bash
git clone https://github.com/open-edge-platform/edge-ai-libraries.git -b main
cd edge-ai-libraries/microservices/metrics-manager
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

First build takes 3–10 minutes (compiles qmassa and Telegraf, then installs Python packages). Subsequent builds are cached and take under a minute.

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
  intel/metrics-manager:2026.3.0
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
  intel/metrics-manager:2026.3.0
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
  intel/metrics-manager:2026.3.0
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
  intel/metrics-manager:2026.3.0
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
  intel/metrics-manager:2026.3.0
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
  intel/metrics-manager:2026.3.0
```

See [Environment Variables](./get-started/environment-variables.md) for all available variables.

### Additional Native Collectors

For optional per-CPU powerstat, high-resolution temperature, IRQ, network,
storage, RAPL and Turbostat collection, follow
[Additional collectors in the native-enabled Docker image](./get-started/native-docker-collectors.md).
Use this image's native-consistent `ENABLE_*` flags or mounted `.conf` drop-ins,
not legacy Python-reader switch names or the bare-metal configuration helper.
The guide also covers the optional `host-nic-telemetry` deployment variant,
explicit service switching, and host-network port exposure. Bridge mode
remains the default; the host-NIC variant enables network collection unless
explicitly disabled.

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
  intel/metrics-manager:2026.3.0
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
  intel/metrics-manager:2026.3.0
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

The container loads `.conf` files recursively from the mounted `telegraf.d/`
directory, or the directory selected by `TELEGRAF_CONFIG_DIR`. Startup copies
them into a private snapshot without modifying the originals. Recreate the
selected container after changing these files.

For a bundled optional collector, prefer its enable flag. For example:

```bash
ENABLE_RAPL=true docker compose up -d --no-build --force-recreate metrics-manager
```

If custom configuration already declares the RAPL input, keep
`ENABLE_RAPL=false`: the flag controls automatic additions, not your custom
input. Enabling both is rejected as a conflict.
RAPL requires readable host energy counters; package power can appear even
when the hardware has no platform (`psys`) domain. See the complete
[additional native Docker collectors guide](./get-started/native-docker-collectors.md)
for prerequisites, other inputs and verification commands.

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

| Issue                    | Solution                                                 |
| ------------------------ | -------------------------------------------------------- |
| Port already in use      | Change ports in `.env` (e.g., `HOST_METRICS_PORT=19090`) |
| Build fails              | Run `docker builder prune` to clear cache                |
| Container will not start | Check logs: `docker logs metrics-manager`                |
| No GPU/NPU metrics       | Expected if hardware not present; other metrics continue |

See [Troubleshooting](./troubleshooting.md) for more issues.

---

## Next Steps

- **Push metrics**: See [API Reference](./api-reference.md)
- **Stream live**: Open `http://localhost:9090/metrics/stream` in a browser
- **Configure**: See [Environment Variables](./get-started/environment-variables.md)
- **Custom metrics**: See [Custom Metrics Scripts](./get-started/custom-metrics.md)
- **Kubernetes**: See [Helm Deployment](./get-started/deploy-with-helm.md)
- **Terminal dashboard**: Build and run the [standalone TUI](./get-started/terminal-dashboard.md)
- **Without Docker on the target host**: Install the [bare-metal package](./get-started/bare-metal-package.md)

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
Native metric migration <./get-started/native-metric-migration.md>
Additional Collectors in Docker <./get-started/native-docker-collectors.md>
./get-started/hardware-telemetry.md
./get-started/terminal-dashboard.md
./get-started/bare-metal-package.md
./get-started/testing.md

:::
hide_directive-->
