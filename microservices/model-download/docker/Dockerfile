# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# ---- Stage 1: Build dependencies ----
FROM python:3.12-slim AS python-base

# Set the working directory in the container
WORKDIR /opt

# Install system dependencies required for uv and the application
RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
    libgl1 \
    libsm6 \
    curl \
    git \
    zstd \
    build-essential && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Only bin/ollama is kept; the archive also bundles large GPU runtime libraries.
# Not tracked by Dependabot (ARG/curl, not FROM); bump manually — see
# "Procedure: Bumping the Baked-In Ollama Binary" in .github/skills/model-download-dev/SKILL.md.
ARG OLLAMA_VERSION=v0.32.0
ARG OLLAMA_SHA256=56362d7609dfa9e35aaebb7c9cab25605d8f0528ec3d5d585dc83d6642002bab
RUN curl -fSL --retry 3 --connect-timeout 20 -o /tmp/ollama.tar.zst \
        "https://github.com/ollama/ollama/releases/download/${OLLAMA_VERSION}/ollama-linux-amd64.tar.zst" && \
    echo "${OLLAMA_SHA256}  /tmp/ollama.tar.zst" | sha256sum -c - && \
    mkdir -p /opt/bin && \
    tar --use-compress-program=unzstd -xf /tmp/ollama.tar.zst -C /opt/bin --strip-components=1 bin/ollama && \
    chmod 0755 /opt/bin/ollama && \
    rm -f /tmp/ollama.tar.zst

# Install uv
RUN pip install uv==0.13.4

# Copy project files
COPY pyproject.toml uv.lock /opt/

# ---- Stage 2: Final slim image ----
FROM python:3.12-slim

ARG UID=1000
ARG GID=1000
ENV PYTHONPATH=/opt
ENV MODELS_DIR=/opt/models

RUN apt-get update -y && apt-get upgrade -y && apt-get install -y --no-install-recommends \
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
COPY --from=python-base /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=python-base /usr/local/bin /usr/local/bin

COPY src /opt/src
COPY .github/skills/model-download-user /opt/.github/skills/model-download-user
COPY scripts /opt/scripts
COPY requirements /opt/requirements
COPY pyproject.toml /opt/
COPY docs/user-guide/_assets/openapi.yaml /opt/docs/user-guide/_assets/openapi.yaml

WORKDIR /opt

COPY docker/entrypoint.sh /opt/entrypoint.sh

RUN chown -R appuser:appuser /opt && \
    chmod +x /opt/entrypoint.sh && \
    chown -R appuser:appuser /usr/local

# Copy Ollama after the ownership step so the binary remains root-owned.
COPY --from=python-base /opt/bin/ollama /opt/bin/ollama

# Switch to non-root user
USER appuser

# Expose the port the app runs on
EXPOSE 8000

# Use our entrypoint script
ENTRYPOINT ["/opt/entrypoint.sh"]