# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# ---- Stage 1: resolve and install Python dependencies ----
FROM python:3.12.14-slim@sha256:2f17fc044b579bab302c2e8054d3a686e2cb9a83de48e70534b94cd8ebbe06a9 AS builder

# git is needed only to fetch the pinned dlstreamer package.
RUN apt-get update && \
    apt-get install -y --no-install-recommends git && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv==0.9.10

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

# ---- Stage 2: runtime image ----
FROM python:3.12.14-slim@sha256:2f17fc044b579bab302c2e8054d3a686e2cb9a83de48e70534b94cd8ebbe06a9

ARG UID=1000
ARG GID=1000

RUN apt-get update && \
    apt-get install -y --no-install-recommends v4l-utils && \
    rm -rf /var/lib/apt/lists/*

RUN groupadd -g ${GID} appuser && \
    useradd -m -s /usr/sbin/nologin -u ${UID} -g ${GID} -G video appuser

COPY --from=builder /opt/venv /opt/venv
COPY src /app/src

ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    XDG_CACHE_HOME=/tmp/.cache \
    SENSOR_MANAGER_PORT=8090

WORKDIR /app
USER appuser

EXPOSE 8090

HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request as r; r.build_opener(r.ProxyHandler({})).open('http://127.0.0.1:' + os.environ.get('SENSOR_MANAGER_PORT', '8090') + '/api/v1/health', timeout=4)"]

CMD ["python", "-m", "src"]
