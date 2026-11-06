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
# - Native Go plugins for CPU, Intel GPU and Intel NPU telemetry, shared
#   verbatim with the bare-metal package
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
#
# Third-party component versions are pinned in ./versions.env (single source of
# truth). The ARG defaults below mirror that file so a plain `docker build .`
# keeps working; `make build` passes them explicitly and tests/test_versions.py
# fails the build if the two ever drift apart. Run `make sync-versions` after
# editing versions.env.
# =============================================================================

# Toolchain base images (mirrors versions.env).
ARG RUST_IMAGE=docker.io/library/rust:1.88
ARG PYTHON_IMAGE=docker.io/library/python:3.12-slim-trixie@sha256:4840d514c583a4d3d8cad3940e68dee6f0f6f3635c12fcd0a3d74c21a5b93a54
ARG GO_IMAGE=docker.io/library/golang:1.27@sha256:0c050feb47802ae436b9030833694a0b80160d08e3b3049ad30bf7c9e724e09d

# -----------------------------------------------------------------------------
# Stage 1: Build qmassa for GPU metrics
# -----------------------------------------------------------------------------
FROM ${RUST_IMAGE} AS qmassa-builder

# Upstream tags for the two workspace members (mirrors versions.env).
ARG QMASSA_VERSION=2.1.0
ARG QMMD_VERSION=0.2.0

# Use Docker's predefined proxy build arguments without redeclaring or
# persisting them, so build-environment values stay out of image history.

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
RUN cargo install --locked --git https://github.com/ulissesf/qmassa --tag qmmd-v${QMMD_VERSION} qmmd
RUN cargo install --locked --git https://github.com/ulissesf/qmassa --tag qmassa-v${QMASSA_VERSION} qmassa

# -----------------------------------------------------------------------------
# Stage 2: Fetch the official Telegraf binary
# -----------------------------------------------------------------------------
# The official upstream release archive is used so that the container image and
# the bare-metal .deb ship one identical, reproducible Telegraf binary. The
# archive is verified against a pinned SHA-256 digest BEFORE extraction, so a
# tampered, truncated or man-in-the-middled download aborts the build.
FROM debian:12-slim AS telegraf-builder

# Mirrors versions.env.
ARG TELEGRAF_VERSION=1.40.3
ARG TELEGRAF_SHA256=cbb95c43303db6e75e129a4eb8888ab1468009e61f6615e64a1cb82f50b0f4ce
ARG TELEGRAF_BASE_URL=https://dl.influxdata.com/telegraf/releases

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \
    apt-get install --yes --no-install-recommends ca-certificates curl && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Download over TLS only, verify the digest, then extract just the binary.
# `sha256sum --check --strict` exits non-zero on mismatch, failing the build.
RUN set -eux; \
    archive="telegraf-${TELEGRAF_VERSION}_linux_amd64.tar.gz"; \
    curl --fail --silent --show-error --location \
         --proto '=https' --tlsv1.2 \
         --output "/tmp/${archive}" "${TELEGRAF_BASE_URL}/${archive}"; \
    echo "${TELEGRAF_SHA256}  /tmp/${archive}" | sha256sum --check --strict -; \
    tar --extract --gzip --file "/tmp/${archive}" --directory /tmp \
        "telegraf-${TELEGRAF_VERSION}/usr/bin/telegraf"; \
    install -m 0755 "/tmp/telegraf-${TELEGRAF_VERSION}/usr/bin/telegraf" /usr/bin/telegraf; \
    rm -rf "/tmp/${archive}" "/tmp/telegraf-${TELEGRAF_VERSION}"; \
    /usr/bin/telegraf --version

# -----------------------------------------------------------------------------
# Stage 3: Build the native telemetry plugins
# -----------------------------------------------------------------------------
# The CPU, GPU and NPU collectors are Go programs that speak InfluxDB Line
# Protocol on stdout, so Telegraf runs them through inputs.execd. The very same
# binaries are shipped in the bare-metal .deb, which is why the collection
# logic lives here rather than in the container-only Python layer.
#
# Module dependencies are fetched from the module proxy and verified against the
# hashes in go.sum, so a tampered or substituted module fails the build. This
# stage therefore needs network access. -mod=readonly is what makes the build
# honest about it: the toolchain may download what go.mod already pins, but it
# refuses to edit go.mod or go.sum, so a missing or drifted requirement fails
# here instead of being silently rewritten into the image.
FROM ${GO_IMAGE} AS go-builder

ARG VERSION=2026.3.0

WORKDIR /src
COPY native/ ./

# CGO is disabled so the result is a static binary that does not depend on the
# glibc of the final image. -trimpath keeps build paths out of the binary,
# which makes the output reproducible.
ENV CGO_ENABLED=0 GOFLAGS=-mod=readonly

RUN set -eux; \
    mkdir -p /out; \
    go vet ./...; \
    go test ./...; \
    for plugin in mm-plugin-cpu mm-plugin-gpu mm-plugin-npu mm-plugin-proc mm-plugin-membw mm-plugin-rapl; do \
        go build -trimpath -ldflags "-s -w -X main.version=${VERSION}" \
            -o "/out/${plugin}" "./cmd/${plugin}"; \
    done

# -----------------------------------------------------------------------------
# Stage 4: Build Python dependencies
# -----------------------------------------------------------------------------
FROM ${PYTHON_IMAGE} AS python-builder

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
ARG INSTALL_OPENVINO=false
RUN if [ "$INSTALL_OPENVINO" = "true" ]; then \
        uv sync --extra openvino --no-group test --no-group dev --no-install-project; \
    else \
        uv sync --no-group test --no-group dev --no-install-project; \
    fi

# -----------------------------------------------------------------------------
# Stage 5: Test image
# -----------------------------------------------------------------------------
FROM python-builder AS test

WORKDIR /app

# Install test dependencies on top of the existing venv
RUN uv sync --group test --no-install-project

# Copy source code, tests, and all config files read by wiring tests
COPY app ./app
COPY tests ./tests
COPY docs ./docs
COPY README.md ./
COPY native ./native
COPY helm ./helm
COPY pyproject.toml ./
COPY VERSION ./
COPY versions.env ./
COPY .env.example ./
COPY .dockerignore Makefile ./
COPY telegraf.conf ./
COPY compose.yaml ./
COPY supervisord.conf ./
COPY entrypoint.sh ./
COPY docker_collectors.py ./
COPY docker_accelerators.py ./
COPY Dockerfile ./

CMD ["python", "-m", "pytest", "tests/", "-v", "--tb=short"]

# -----------------------------------------------------------------------------
# Stage 6: Optional accelerator userspace packages
# -----------------------------------------------------------------------------
FROM ${PYTHON_IMAGE} AS accelerator-builder

ARG INSTALL_OPENVINO=false
COPY versions.env docker_accelerators.py /build/
RUN mkdir /runtime-debs && \
    if [ "$INSTALL_OPENVINO" = "true" ]; then \
        python /build/docker_accelerators.py --versions /build/versions.env --output /runtime-debs; \
    fi

# -----------------------------------------------------------------------------
# Stage 7: Final image
# -----------------------------------------------------------------------------
FROM ${PYTHON_IMAGE} AS production

ARG INSTALL_OPENVINO=false

ARG METRICS_MANAGER_UID=10001
ARG METRICS_MANAGER_GID=10001

# Copy qmassa and qmmd binaries from Rust build stage
COPY --from=qmassa-builder /usr/local/cargo/bin/qmassa /usr/local/bin/qmassa
COPY --from=qmassa-builder /usr/local/cargo/bin/qmmd /usr/local/bin/qmmd

# Copy the telemetry plugins. They live in /usr/libexec so the container and
# the bare-metal .deb refer to them by the very same path.
COPY --from=go-builder /out/ /usr/libexec/metrics-manager/

# Copy the official Telegraf binary (digest-verified in the fetch stage)
COPY --from=telegraf-builder /usr/bin/telegraf /usr/bin/telegraf

ENV DEBIAN_FRONTEND=noninteractive

# Install capabilities-required system tools.
# - dmidecode: memory technology discovery (DDR4/DDR5/etc.)
# - pciutils: lspci-based PCI/GPU branding discovery
# - libva-utils: vainfo for runtime VAAPI codec capability detection
# - util-linux: lsblk for storage device enumeration
# - hwinfo: extended hardware information probing
# Install supervisor via pip to avoid pulling Debian's python3.13 (CVE-2026-7210).
# perl-base is not needed at runtime; purging it removes several known CVEs.
RUN --mount=type=bind,from=accelerator-builder,source=/runtime-debs,target=/runtime-debs \
    set -eu; \
    apt-get update; \
    apt-get upgrade --yes --no-install-recommends; \
    packages="dmidecode pciutils util-linux hwinfo"; \
    if [ "$INSTALL_OPENVINO" = "true" ]; then \
        packages="$packages vainfo intel-media-va-driver ocl-icd-libopencl1 libze1 libtbb12 /runtime-debs/*.deb"; \
    fi; \
    apt-get install --yes --no-install-recommends $packages && \
    pip install --no-cache-dir pip==26.2.1 supervisor==4.3.0 && \
    rm -rf /usr/local/lib/python3.12/site-packages/pip \
        /usr/local/lib/python3.12/site-packages/pip-*.dist-info \
        /usr/local/lib/python3.12/site-packages/setuptools* \
        /usr/local/bin/pip /usr/local/bin/pip3 /usr/local/bin/pip3.12 && \
    (dpkg -s perl-base >/dev/null 2>&1 && dpkg --purge --force-remove-essential perl-base || true) && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Create Telegraf config directories
RUN mkdir -p /etc/telegraf /etc/telegraf/telegraf.d /var/log/telegraf \
        /etc/supervisor/conf.d && \
    touch /etc/supervisor/conf.d/placeholder.conf

# Preserve empty runtime defaults without retaining build-time proxy values.
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
RUN mkdir -p /app/custom-metrics /app/config /etc/telegraf/telegraf.d

# Copy application files
COPY app ./app
COPY docker_collectors.py ./
COPY native/packaging/etc/telegraf-*.conf.example /usr/share/metrics-manager/telegraf-examples/
COPY VERSION ./
COPY telegraf.conf /etc/telegraf/telegraf.conf
COPY supervisord.conf /etc/supervisor/supervisord.conf
COPY entrypoint.sh /entrypoint.sh

# Verify the native collectors run in the final image, not just the build stage.
RUN set -eux; \
    for plugin in /usr/libexec/metrics-manager/mm-plugin-*; do \
        "$plugin" -version; \
    done

# Strip CRLF (handles files copied from Windows working directories)
RUN sed -i 's/\r$//' /entrypoint.sh /etc/telegraf/telegraf.conf /etc/supervisor/supervisord.conf

RUN chmod +x /entrypoint.sh && \
    groupadd --gid ${METRICS_MANAGER_GID} metrics-manager && \
    useradd --uid ${METRICS_MANAGER_UID} --gid ${METRICS_MANAGER_GID} \
        --create-home --shell /usr/sbin/nologin metrics-manager && \
    chown -R ${METRICS_MANAGER_UID}:${METRICS_MANAGER_GID} \
        /app /tmp /var/log/telegraf /etc/telegraf /etc/supervisor

# Environment variables with defaults
ENV METRICS_PORT=9090
ENV TELEGRAF_PORT=9273
ENV TELEGRAF_HTTP_PORT=8186
ENV HARDWARE_TELEMETRY_ENABLED=true
ENV QMASSA_FIFO_PATH=/app/qmassa.fifo
ENV LOG_LEVEL=INFO
ENV CORS_ORIGINS="*"
ENV CUSTOM_METRICS_DIR=/app/custom-metrics
ENV TELEGRAF_CONFIG_PATH=/etc/telegraf/telegraf.conf

# Expose ports
# 9090 - Metrics Manager API and SSE (/metrics/stream)
# 9273 - Telegraf Prometheus metrics
# 8186 - Telegraf HTTP listener (InfluxDB Line Protocol)
EXPOSE 9090 9273 8186

# No USER directive: host telemetry (PMT sysfs, dmidecode) is readable only by
# root, so the image defaults to root; override with CONTAINER_USER to opt out.

# OCI image metadata - version is read from the VERSION file at build time
# (single source of truth used by Makefile / docker compose).
ARG VERSION=2026.3.0
ENV SERVICE_VERSION=${VERSION}
LABEL org.opencontainers.image.title="metrics-manager" \
      org.opencontainers.image.description="Unified metrics collection, ingestion, and relay service" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.licenses="Apache-2.0"

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://localhost:' + os.environ['METRICS_PORT'] + '/health', timeout=8)" || exit 1

# Use supervisor to manage both Telegraf and Python service
CMD ["/entrypoint.sh"]
