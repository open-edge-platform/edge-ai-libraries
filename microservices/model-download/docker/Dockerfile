# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# ---- Stage 1: Build dependencies ----
FROM python:3.11-slim AS python-base

# Add uv to PATH
ENV PATH="/opt/.local/bin:$PATH"

# Set the working directory in the container
WORKDIR /opt

# Install system dependencies required for uv and the application
RUN apt-get update && apt-get install -y \
    libgl1 \
    libsm6 \
    curl \
    git \
    build-essential && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | UV_INSTALL_DIR=/opt/.local/bin sh

# Copy project files
COPY pyproject.toml uv.lock /opt/

# Install base dependencies using uv
RUN uv sync \
    && rm -rf ~/.cache

# ---- Stage 2: Final slim image ----
FROM python:3.11-slim

ARG UID=1001
ARG GID=1001
ENV PYTHONPATH=/opt
ENV MODELS_DIR=/opt/models

RUN apt-get update -y && apt-get install -y --no-install-recommends \
    libmagic-dev \
    libglib2.0-0 \
    libgl1 \
    libsm6 \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean
RUN groupadd -g ${GID} appuser && \
    useradd -m -s /bin/bash -u ${UID} -g ${GID} appuser

# Copy installed dependencies from python-base
COPY --from=python-base /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=python-base /usr/local/bin /usr/local/bin
COPY --from=python-base /opt/.local/bin/uv /usr/local/bin/uv

COPY src /opt/src
COPY scripts /opt/scripts
COPY pyproject.toml /opt/
COPY docs/user-guide/api-docs/openapi.yaml /opt/docs/user-guide/api-docs/openapi.yaml

WORKDIR /opt

COPY docker/entrypoint.sh /opt/entrypoint.sh

RUN chown -R appuser:appuser /opt && \
    chmod +x /opt/entrypoint.sh && \
    chown -R appuser:appuser /usr/local

# Switch to non-root user
USER appuser

# Expose the port the app runs on
EXPOSE 8000

# Use our entrypoint script
ENTRYPOINT ["/opt/entrypoint.sh"]