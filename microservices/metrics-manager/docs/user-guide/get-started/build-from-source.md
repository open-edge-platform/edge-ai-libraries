# Building from Source

This guide explains how to build Metrics Manager from source code for development, customization, or air-gapped deployments.

## Prerequisites

Before building, ensure you have:

- **System Requirements**: See [System Requirements](./system-requirements.md)
- **Source code**: Cloned the repository (`git clone https://github.com/open-edge-platform/edge-ai-libraries.git`)
- **Familiarity**: Basic understanding of Docker and Docker Compose

## Building in a Docker Container (Recommended)

The recommended way to build is inside Docker, which handles all dependencies (Rust toolchain, Telegraf, Python) automatically.

### Step 1: Navigate to the Project

```bash
cd edge-ai-libraries/metrics-manager
```

### Step 2: Copy Environment Configuration

```bash
cp .env.example .env
```

Edit `.env` if needed (usually defaults work fine).

### Step 3: Build the Docker Image

```bash
docker compose build
```

This runs a multi-stage build:

1. **Stage 1**: Compiles qmassa (Intel GPU reader) from Rust source
2. **Stage 2**: Installs Python dependencies (production only, no test packages)
3. **Stage 3**: Creates a test image with test dependencies (optional)
4. **Stage 4**: Production image based on `python:3.12-slim` with Telegraf, qmassa, and supervisord

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

- **Python 3.10+** (`python3 --version`)
- **uv** (fast Python package manager): `pip install uv` or see https://docs.astral.sh/uv/
- **Telegraf** installed on the system (for system metrics)
- **qmassa binary** (for GPU metrics) — compile from https://github.com/ulissesf/qmassa or skip if not needed
- **Git**

### Step 1: Clone and Navigate

```bash
git clone https://github.com/open-edge-platform/edge-ai-libraries.git
cd edge-ai-libraries/metrics-manager
```

### Step 2: Create Virtual Environment

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

Or with pip:

```bash
pip install -e ".[test]"
```

### Step 4: Configure Environment

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

### Step 5: Start Telegraf

On your host machine, start Telegraf with the bundled config:

```bash
telegraf --config telegraf.conf
```

This exposes metrics on `http://localhost:9273/metrics` and listens for writes on `http://localhost:8186/write`.

### Step 6: Run the Application

```bash
uvicorn app.main:app --reload --port 9090
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
tests/test_npu_monitor_tool.py::...      PASSED
tests/test_npu_reader.py::...            PASSED
tests/test_telegraf_integration.py::...  SKIPPED (requires Docker)
========================= 179 passed in 1.70s ==========================
```

---

## Development Setup

For local development with hot-reload and debugging:

```bash
# Install dev dependencies
uv sync --group test --group dev

# Run with auto-reload
uvicorn app.main:app --reload --port 9090

# Run linting and formatting
black app/
ruff check app/
```

## Building the Helm Chart

If you're deploying to Kubernetes:

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
3. Or drop additional `.conf` files in the `telegraf.d/` directory

See [Configuration Guide](./environment-variables.md) for Telegraf customization examples.

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

| Error | Solution |
|-------|----------|
| `Rust toolchain not found` | First Docker build compiles Rust. Try `docker compose build --no-cache`. |
| `Module not found: app` | Ensure you're in the `metrics-manager/` directory and have run `uv sync` or `pip install -e .` |
| `Port 9090 already in use` | Change port in `.env`: `HOST_METRICS_PORT=19090` |
| `Telegraf not found` | Install Telegraf: `apt-get install telegraf` (Debian/Ubuntu) or use Docker |
| `Permission denied on /sys` | Ensure you run with `--privileged` (Docker) or as root (local) |

## Supporting Resources

- [Installation Guide](./installation.md)
- [System Requirements](./system-requirements.md)
- [Testing Guide](./testing.md)
- [Configuration Guide](./environment-variables.md)
- [Helm Deployment](./deploy-with-helm.md)
- [Troubleshooting](../troubleshooting.md)

## License

Copyright (C) 2025-2026 Intel Corporation

SPDX-License-Identifier: Apache-2.0
