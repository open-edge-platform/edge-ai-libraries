# syntax=docker/dockerfile:1
# Copyright (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# =============================================================================
# Metrics Manager - Unified metrics collection, ingestion, and relay service
# =============================================================================
#
# This Dockerfile creates a combined image with:
# - Telegraf for system metrics collection (CPU, memory, GPU, temperature)
# - Python FastAPI service for metrics relay and custom metrics ingestion
# - qmassa for GPU metrics (Intel GPUs) - long-running, JSON FIFO output
# - qmmd Prometheus exporter (bundled, OPT-IN; not started by default)
# - npu_monitor_tool / npu_reader for Intel NPU telemetry via PMT sysfs
# - Supervisor for process management
#
# Mount points for custom configuration:
# - /etc/telegraf/telegraf.conf - Custom Telegraf configuration
# - /etc/telegraf/telegraf.d/    - Drop-in directory for additional configs
# - /app/custom-metrics          - Custom user metric scripts (.sh / .py),
#                                  auto-executed every 10s by Telegraf
# - /app/config                  - Additional configuration files
#
# Source repository / issues / docs:
#   https://github.com/open-edge-platform/edge-ai-libraries
#   (subdirectory: metrics-manager)
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: Build qmassa for GPU metrics
# -----------------------------------------------------------------------------
FROM docker.io/library/rust:1.88 AS qmassa-builder

# Proxy settings (passed from docker-compose build args)
ARG http_proxy
ARG HTTP_PROXY
ARG https_proxy
ARG HTTPS_PROXY
ARG no_proxy
ARG NO_PROXY

ENV http_proxy=${http_proxy} \
    HTTP_PROXY=${HTTP_PROXY} \
    https_proxy=${https_proxy} \
    HTTPS_PROXY=${HTTPS_PROXY} \
    no_proxy=${no_proxy} \
    NO_PROXY=${NO_PROXY}

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \
    apt-get install --yes --no-install-recommends libudev-dev && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install qmassa and qmmd directly from their upstream GitHub repository by
# tag instead of from crates.io. qmassa and qmmd live in the same Cargo
# workspace (https://github.com/ulissesf/qmassa) but are tagged independently
# (`qmassa-vX.Y.Z`, `qmmd-vX.Y.Z`), so each binary is installed with its own
# per-binary tag. `--bin` limits each install to the matching binary so the
# other workspace member is not rebuilt unnecessarily.
# The --locked flag is kept, so the build stays fully reproducible. This
# avoids build failures if a pinned crates.io version is ever yanked from
# the registry by the upstream maintainer.
RUN cargo install --locked --git https://github.com/ulissesf/qmassa --tag qmmd-v0.2.0 qmmd
RUN cargo install --locked --git https://github.com/ulissesf/qmassa --tag qmassa-v2.1.0 qmassa

# -----------------------------------------------------------------------------
# Stage 2: Build Telegraf from source with patched dependencies
# -----------------------------------------------------------------------------
# Built from source (instead of the upstream .deb) to patch known CVEs in
# bundled Go dependencies:
# Using golang:1.26 (1.26.3+) also resolves stdlib CVEs fixed in Go 1.26.3.
# Digest pinned for reproducible builds — decoupled from Docker Hub tag updates.
FROM golang:1.26.4@sha256:68cb6d68bed024785b69195b89af7ac7a444f27791435f98647edff595aa0479 AS telegraf-builder

ARG TELEGRAF_VERSION=1.38.4

ARG http_proxy
ARG HTTP_PROXY
ARG https_proxy
ARG HTTPS_PROXY
ARG no_proxy
ARG NO_PROXY

ENV http_proxy=${http_proxy} \
    HTTP_PROXY=${HTTP_PROXY} \
    https_proxy=${https_proxy} \
    HTTPS_PROXY=${HTTPS_PROXY} \
    no_proxy=${no_proxy} \
    NO_PROXY=${NO_PROXY}

RUN apt-get update && \
    apt-get install --yes --no-install-recommends git libudev-dev && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

RUN git clone --depth 1 --branch v${TELEGRAF_VERSION} \
    https://github.com/influxdata/telegraf /telegraf

WORKDIR /telegraf

# Cache Go module downloads across builds to avoid re-fetching on every run.
RUN --mount=type=cache,target=/go/pkg/mod \
    --mount=type=cache,target=/root/.cache/go-build \
    go get github.com/rclone/rclone@v1.73.5 && \
    go get github.com/go-git/go-billy/v5@v5.9.0 && \
    go mod tidy
# NOTE: CVE-2026-34040 (HIGH) and CVE-2026-33997 (MEDIUM) in github.com/docker/docker
# cannot be patched yet — fix requires v29.3.1 which does not exist in the Go
# module proxy (latest: v28.5.2+incompatible). Transitive Telegraf dependency.
# Revisit when moby/moby v29.3.1 is published to the Go module registry.

# fs.LogOutput was removed from rclone/fs in rclone 1.71+; the remotefile
# plugin used it only for trace logging so dropping the assignment is safe.
# The outer `if` is a no-op if a future Telegraf release already adapts to
# the new API; the inner grep catches a block size change at build time.
RUN if grep -q 'fs\.LogOutput = func' plugins/outputs/remotefile/remotefile.go; then \
        sed -i '/fs\.LogOutput = func/,+2d' plugins/outputs/remotefile/remotefile.go; \
        if grep -q 'fs\.LogOutput' plugins/outputs/remotefile/remotefile.go; then \
            echo "ERROR: sed patch incomplete — fs.LogOutput block may have changed size in this Telegraf version" >&2; \
            exit 1; \
        fi; \
    fi

RUN --mount=type=cache,target=/go/pkg/mod \
    --mount=type=cache,target=/root/.cache/go-build \
    go build \
        -ldflags="-s -w -X github.com/influxdata/telegraf/internal.Version=${TELEGRAF_VERSION}" \
        -o /usr/bin/telegraf ./cmd/telegraf

# -----------------------------------------------------------------------------
# Stage 3: Build Python dependencies
# -----------------------------------------------------------------------------
FROM python:3.12-slim AS python-builder

# Proxy settings (passed from docker-compose build args)
ARG http_proxy
ARG HTTP_PROXY
ARG https_proxy
ARG HTTPS_PROXY
ARG no_proxy
ARG NO_PROXY

ENV http_proxy=${http_proxy} \
    HTTP_PROXY=${HTTP_PROXY} \
    https_proxy=${https_proxy} \
    HTTPS_PROXY=${HTTPS_PROXY} \
    no_proxy=${no_proxy} \
    NO_PROXY=${NO_PROXY}

# Install uv for fast package installation
RUN pip install --no-cache-dir uv==0.7.12

WORKDIR /app

# Copy dependency files (uv.lock is optional - will be generated if missing)
COPY pyproject.toml ./
COPY uv.lock* ./

# Install dependencies to a virtual environment
# Note: Not using --frozen so uv can resolve dependencies if lock is missing/stale
RUN uv venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
ENV UV_PROJECT_ENVIRONMENT="/opt/venv"
RUN uv sync --no-group test --no-group dev --no-install-project

# -----------------------------------------------------------------------------
# Stage 3: Test image
# -----------------------------------------------------------------------------
FROM python-builder AS test

WORKDIR /app

# Install test dependencies on top of the existing venv
RUN uv sync --group test --no-install-project

# Copy source code, tests, and all config files read by wiring tests
COPY app ./app
COPY tests ./tests
COPY scripts ./scripts
COPY helm ./helm
COPY pyproject.toml ./
COPY VERSION ./
COPY .env.example ./
COPY telegraf.conf ./
COPY compose.yaml ./
COPY supervisord.conf ./
COPY entrypoint.sh ./
COPY Dockerfile ./

CMD ["python", "-m", "pytest", "tests/", "-v", "--tb=short"]

# -----------------------------------------------------------------------------
# Stage 4: Final image
# -----------------------------------------------------------------------------
FROM python:3.12-slim AS production

# Proxy settings (passed from docker-compose build args)
ARG http_proxy
ARG HTTP_PROXY
ARG https_proxy
ARG HTTPS_PROXY
ARG no_proxy
ARG NO_PROXY

ENV http_proxy=${http_proxy} \
    HTTP_PROXY=${HTTP_PROXY} \
    https_proxy=${https_proxy} \
    HTTPS_PROXY=${HTTPS_PROXY} \
    no_proxy=${no_proxy} \
    NO_PROXY=${NO_PROXY}

# Copy qmassa and qmmd binaries from Rust build stage
COPY --from=qmassa-builder /usr/local/cargo/bin/qmassa /usr/local/bin/qmassa
COPY --from=qmassa-builder /usr/local/cargo/bin/qmmd /usr/local/bin/qmmd

# Copy Telegraf binary (built from source with patched dependencies)
COPY --from=telegraf-builder /usr/bin/telegraf /usr/bin/telegraf

ENV DEBIAN_FRONTEND=noninteractive

# Install supervisor via pip to avoid pulling Debian's python3.13 (CVE-2026-7210).
# perl-base is not needed at runtime; purging it removes several known CVEs.
RUN pip install --no-cache-dir pip==26.1 supervisor==4.3.0 && \
    (dpkg -s perl-base >/dev/null 2>&1 && dpkg --purge --force-remove-essential perl-base || true) && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Create Telegraf config directories
RUN mkdir -p /etc/telegraf /etc/telegraf/telegraf.d /var/log/telegraf

# Clear proxy from final image (not needed at runtime, set via environment)
ENV http_proxy= \
    HTTP_PROXY= \
    https_proxy= \
    HTTPS_PROXY= \
    no_proxy= \
    NO_PROXY=

# Copy Python virtual environment (built with same Python 3.12 version)
COPY --from=python-builder /opt/venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Create working directories
WORKDIR /app
RUN mkdir -p /app/custom-metrics /app/config

# Copy application files
COPY app ./app
COPY scripts ./scripts
COPY VERSION ./
COPY telegraf.conf /etc/telegraf/telegraf.conf
COPY supervisord.conf /etc/supervisor/supervisord.conf
COPY entrypoint.sh /entrypoint.sh

# Strip CRLF (handles files copied from Windows working directories)
RUN sed -i 's/\r$//' /entrypoint.sh /etc/telegraf/telegraf.conf /etc/supervisor/supervisord.conf && \
    find /app/scripts -name "*.sh" -o -name "*.py" | xargs sed -i 's/\r$//'

# Make scripts executable
RUN chmod +x /entrypoint.sh && \
    find /app/scripts -name "*.sh" -exec chmod +x {} + && \
    find /app/scripts -name "*.py" -exec chmod +x {} +

# Environment variables with defaults
ENV METRICS_PORT=9090
ENV TELEGRAF_PORT=9273
ENV LOG_LEVEL=INFO
ENV CORS_ORIGINS="*"
ENV CUSTOM_METRICS_DIR=/app/custom-metrics
ENV TELEGRAF_CONFIG_PATH=/etc/telegraf/telegraf.conf

# Expose ports
# 9090 - Metrics Manager API and SSE (/metrics/stream)
# 9273 - Telegraf Prometheus metrics
# 8186 - Telegraf HTTP listener (InfluxDB Line Protocol)
EXPOSE 9090 9273 8186

# OCI image metadata - version is read from the VERSION file at build time
# (single source of truth used by Makefile / docker compose).
ARG VERSION=unknown
LABEL org.opencontainers.image.title="metrics-manager" \
      org.opencontainers.image.description="Unified metrics collection, ingestion, and relay service" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.licenses="Apache-2.0"

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:9090/health', timeout=8)" || exit 1

# Use supervisor to manage both Telegraf and Python service
CMD ["/entrypoint.sh"]
