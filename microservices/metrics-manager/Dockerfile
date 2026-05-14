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

RUN cargo install --locked qmassa@1.3.1
RUN cargo install --locked qmmd@0.1.1

# -----------------------------------------------------------------------------
# Stage 2: Build Python dependencies
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
# Stage 4: Final image (Python 3.12 base with Telegraf)
# Using Python base for venv compatibility, Telegraf installed via .deb
# -----------------------------------------------------------------------------
FROM python:3.12-slim AS production

# Telegraf version - pinned for reproducible builds
ARG TELEGRAF_VERSION=1.37.3

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

# Copy qmassa binary from the build stage
COPY --from=qmassa-builder /usr/local/cargo/bin/qmassa /usr/local/bin/qmassa
COPY --from=qmassa-builder /usr/local/cargo/bin/qmmd /usr/local/bin/qmmd

ENV DEBIAN_FRONTEND=noninteractive

# Install Telegraf (pinned version via direct .deb download), supervisor, and curl
RUN apt-get update && \
    apt-get install --yes --no-install-recommends \
        supervisor \
        curl && \
    # Download and install Telegraf .deb directly (pinned version, no GPG issues)
    curl -fsSL "https://dl.influxdata.com/telegraf/releases/telegraf_${TELEGRAF_VERSION}-1_amd64.deb" -o /tmp/telegraf.deb && \
    dpkg -i /tmp/telegraf.deb && \
    rm /tmp/telegraf.deb && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

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
    CMD curl -f http://localhost:9090/health || exit 1

# Use supervisor to manage both Telegraf and Python service
CMD ["/entrypoint.sh"]
