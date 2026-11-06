# Building from Source

This guide explains how to build Metrics Manager from source code for development, customization, or air-gapped deployments.

## Prerequisites

Before building, ensure you have:

- **System Requirements**: See [System Requirements](./system-requirements.md)
- **Source code**: Cloned the repository (`git clone https://github.com/open-edge-platform/edge-ai-libraries.git -b main`)
- **Platform familiarity**: Basic understanding of Docker and Docker Compose

## Building in a Docker Container (Recommended)

The recommended way to build is inside Docker, which handles all dependencies (Rust toolchain, Telegraf, Python) automatically.

### Step 1: Navigate to the Project

```bash
cd edge-ai-libraries/microservices/metrics-manager
```

### Step 2: Copy Environment Configuration

```bash
cp .env.example .env
```

Edit `.env` if needed (usually defaults work fine).

### Step 3: Build the Docker Image

```bash
docker compose build metrics-manager
```

This runs a multi-stage build:

1. **Rust builder**: Compiles qmassa and qmmd from their pinned upstream tags with locked dependencies.
2. **Telegraf stage**: Downloads the official pinned release archive and verifies its SHA-256 checksum. Telegraf is not rebuilt or patched locally.
3. **Go builder**: Compiles the six native telemetry collectors with the pinned Go toolchain.
4. **Python builder**: Installs runtime dependencies, optionally including OpenVINO.
5. **Test target**: Adds test dependencies and sources when explicitly selected.
6. **Accelerator stage**: For extended builds only, downloads the pinned Intel GPU/NPU userspace packages from official release assets, verifies SHA-256 digests and selects only the required packages. Pins are read directly from `versions.env`; firmware and debug packages are excluded.
7. **Production target**: Uses digest-pinned `python:3.12-slim-trixie` (Debian 13), applies available Debian updates, and assembles the API, collectors and supervisor. Extended builds install the accelerator packages with normal APT dependency checks. Downloaded packages are build-only mounts, not retained archive layers in the final image.

For the two separately tagged RC1 builds, see
[Building both release-candidate variants](../../../README.md#building-both-release-candidate-variants).

**First build duration**: 3–10 minutes (depends on download speeds and CPU)

**Subsequent builds**: <1 minute (cached layers)

### Step 4: Start the Service

```bash
docker compose up
```

Or in the background:

```bash
docker compose up -d
```

### Step 5: Verify

```bash
curl http://localhost:9090/health
```

---

## Building Locally (Without Docker)

If you want to run the service locally without Docker, use the following approach:

### Prerequisites

- **Python 3.12+** (`python3 --version`)
- **uv**: follow the [uv installation instructions](https://docs.astral.sh/uv/getting-started/installation/)
- **Running telemetry backend**: Telegraf with a Prometheus endpoint and HTTP
  ingestion listener. The steps below run the API separately from this backend.
- **Git**

### Step 1: Clone and Navigate

```bash
git clone https://github.com/open-edge-platform/edge-ai-libraries.git -b main
cd edge-ai-libraries/microservices/metrics-manager
```

### Step 2: Create a Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

Or with uv (faster):

```bash
uv venv
source .venv/bin/activate
```

### Step 3: Install Dependencies

```bash
uv sync --group test
```

The test dependencies are a dependency group, not a `test` extra. Use
`uv sync --group test`; `pip install -e ".[test]"` does not install this group.

### Step 4: Configure the Environment

```bash
cp .env.example .env
```

Edit `.env` and set:

```bash
# Since Telegraf runs on the host (not in a container), use localhost
TELEGRAF_PORT=9273
TELEGRAF_HTTP_ENDPOINT=http://localhost:8186/write
PROMETHEUS_TELEGRAF_ENDPOINT=http://localhost:9273
```

### Step 5: Verify the Telemetry Backend

Check that your configured telemetry backend is reachable:

```bash
curl --fail http://127.0.0.1:9273/metrics | head
```

The example settings expect `127.0.0.1:9273` for metrics and `127.0.0.1:8186`
for writes. Adapt them to your backend and do not start a second Telegraf on
occupied ports. The container's
root-level `telegraf.conf` uses container paths and environment substitutions;
it is not a standalone host configuration.

### Step 6: Run the Application

```bash
.venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 9090
```

The service will start on `http://localhost:9090`.

### Step 7: Verify

```bash
curl http://localhost:9090/health
curl http://localhost:9273/metrics | head
```

---

## Running Tests

### Via Docker (Recommended)

```bash
# Run all tests
docker compose --profile test build metrics-manager-test
docker compose --profile test run --rm metrics-manager-test

# Run with coverage
docker compose --profile test run --rm metrics-manager-test \
  python -m pytest tests/ -v --cov=app --cov-report=term-missing
```

### Locally

If you installed dependencies locally:

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run with coverage
pytest --cov=app --cov-report=html
```

### Expected Output

```
========================= test session starts ==========================
tests/test_settings.py::...              PASSED
tests/test_logging_config.py::...        PASSED
tests/test_main.py::...                  PASSED
tests/test_models.py::...                PASSED
tests/test_store.py::...                 PASSED
tests/test_routes.py::...                PASSED
tests/test_metrics.py::...               PASSED
tests/test_rate_limit.py::...            PASSED
tests/test_sse.py::...                   PASSED
tests/test_versions.py::...              PASSED
tests/test_telegraf_integration.py::...  PASSED
```

This is an illustrative excerpt, not a fixed test count or timing guarantee.
The Telegraf wiring tests inspect configuration and do not require a running
Docker daemon. Binary-backed selection tests and live deployment tests have
separate prerequisites; see the [Testing Guide](./testing.md).

---

## Development Setup

For local development with hot-reload and debugging:

```bash
# Install dev dependencies
uv sync --group test --group dev

# Run with auto-reload
.venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 9090

# Run linting and formatting
black app/
ruff check app/
```

## Building the Helm Chart

If you are deploying to Kubernetes:

```bash
# Lint the Helm chart
make helm-lint

# Generate the chart package
make helm-package

# Push to OCI registry (requires authentication)
make helm-push
```

See [Helm Deployment](./deploy-with-helm.md) for full Kubernetes instructions.

## Customization

### Modifying Telegraf Configuration

The `telegraf.conf` file controls system metric collection. To customize:

1. Edit `telegraf.conf` in the metrics-manager root directory
2. Or mount a custom config: `TELEGRAF_CONFIG=./my-telegraf.conf docker compose up`
3. Add custom `.conf` files to `telegraf.d/`, or select another source directory
   with `TELEGRAF_CONFIG_DIR`. Startup recursively copies these files into a
   private snapshot without modifying the mounted originals.
4. Recreate the selected container to apply changes. Do not enable an automatic
   collector flag for an input already supplied by your custom configuration:
   overlapping inputs are rejected instead of collected twice.

See [Additional Native Docker Collectors](./native-docker-collectors.md) for a
complete example and [Environment Variables](./environment-variables.md) for
Telegraf configuration settings.

### Extending with Custom Inputs

Add Python or shell scripts to `/app/custom-metrics/`:

```bash
# Example: create a fan speed monitor
cat > /app/custom-metrics/fan_speed.sh << 'EOF'
#!/bin/sh
rpm=$(cat /sys/class/hwmon/hwmon0/fan1_input)
echo "fan_speed,sensor=cpu_fan rpm=${rpm}i"
EOF
chmod +x /app/custom-metrics/fan_speed.sh
```

The script runs every 10 seconds and outputs InfluxDB Line Protocol.

## Troubleshooting Build Issues

| Error                       | Solution                                                                                       |
| --------------------------- | ---------------------------------------------------------------------------------------------- |
| `Rust toolchain not found`  | First Docker build compiles Rust. Try `docker compose build --no-cache`.                       |
| `Module not found: app`     | Run from `edge-ai-libraries/microservices/metrics-manager` using the environment created by `uv sync`. |
| `Port 9090 already in use`  | For Compose, set `HOST_METRICS_PORT=19090`. For a local API, change the Uvicorn `--port` argument. |
| `Telegraf not found`        | Build the Docker image or configure an existing telemetry backend. |
| `Permission denied on /sys` | Check the collector-specific device/capability requirements; do not run the local API as root to grant collector access. |

## Supporting Resources

- [Get Started Guide](../get-started.md)
- [System Requirements](./system-requirements.md)
- [Testing Guide](./testing.md)
- [Environment Variables](./environment-variables.md)
- [Helm Deployment](./deploy-with-helm.md)
- [Troubleshooting](../troubleshooting.md)

## License

Copyright (C) 2025-2026 Intel Corporation

SPDX-License-Identifier: Apache-2.0
