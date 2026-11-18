# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
FROM python:3.11-slim AS python-base

ARG UID=1000
ARG GID=1000

# Copy drivers and set execute permission on sh files
COPY ./drivers/install_gpu_drivers.sh /tmp/drivers/install_gpu_drivers.sh
RUN chmod +x /tmp/drivers/install_gpu_drivers.sh

# Install GPU drivers
ARG INSTALL_DRIVER_VERSION="26.31.39395"

RUN echo "Installing GPU drivers version $INSTALL_DRIVER_VERSION"; \
    apt-get update && apt-get install -y --no-install-recommends ca-certificates libxml2; \
    /tmp/drivers/install_gpu_drivers.sh; \
    apt-get clean && \
    rm -rf /tmp/drivers /var/lib/apt/lists/* /tmp/*

# Install the Intel NPU user-space stack: the NPU
# driver/compiler/firmware plus the oneAPI Level Zero loader (libze1). The
# loader is mandatory — without libze_loader.so.1 the NPU plugin cannot
# enumerate the device. The final test fails the build if it is missing.
ARG NPU_DRIVER_VERSION="1.38.0"
ARG NPU_DRIVER_BUILD="v1.38.0.20260910-34487311128-ubuntu2404"
ARG LEVEL_ZERO_VERSION="1.32.0-1~24.04~ppa1"
ARG LEVEL_ZERO_PPA_SNAPSHOT="20260830T100000Z"

RUN mkdir -p /tmp/npu_deps && cd /tmp/npu_deps \
    && echo "Installing Intel NPU driver version ${NPU_DRIVER_VERSION}" \
    && apt-get update && apt-get install -y --no-install-recommends curl ca-certificates libtbb12 \
    && curl -L --retry 5 --retry-delay 5 --retry-all-errors -O https://github.com/intel/linux-npu-driver/releases/download/v${NPU_DRIVER_VERSION}/linux-npu-driver-${NPU_DRIVER_BUILD}.tar.gz \
    && tar -xf linux-npu-driver-${NPU_DRIVER_BUILD}.tar.gz \
    && curl -L --retry 5 --retry-delay 5 --retry-all-errors -O https://snapshot.ppa.launchpadcontent.net/kobuk-team/intel-graphics/ubuntu/${LEVEL_ZERO_PPA_SNAPSHOT}/pool/main/l/level-zero-loader/libze1_${LEVEL_ZERO_VERSION}_amd64.deb \
    && dpkg -i ./*.deb \
    && ldconfig \
    && test -e /usr/lib/x86_64-linux-gnu/libze_loader.so.1 \
    && rm -rf /tmp/npu_deps /var/lib/apt/lists/*

# Setting env vars for python and pip
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100 \
    # Location where packages gets installed
    SETUP_PATH="/opt/projsetup" \
    # Location where virtual env is created
    VENV_PATH="/opt/projsetup/.venv"

# Add venv to path
ENV PATH="$VENV_PATH/bin:$PATH"

# Upgrade pip and setuptools to the latest version to fix vuln
RUN /usr/local/bin/pip install --upgrade --no-cache-dir pip==26.1.2 setuptools wheel

# Create a non-root user
RUN groupadd -g ${GID} appuser && \
    useradd -m -s /bin/bash -u ${UID} -g ${GID} appuser && \
    chown -R appuser:appuser $HOME


FROM python-base AS builder-base
RUN apt-get update && apt-get install --no-install-recommends -y curl build-essential

# Install uv from official image
COPY --from=ghcr.io/astral-sh/uv:0.11.21 /uv /usr/local/bin/uv

WORKDIR $SETUP_PATH
COPY pyproject.toml uv.lock ./
RUN uv venv "$VENV_PATH"
ENV UV_PROJECT_ENVIRONMENT="$VENV_PATH"
# Install runtime deps from pyproject dependency groups.
RUN uv sync --no-dev --group openvino --no-install-project

# `dev` image is used during development / testing
FROM python-base AS dev
ENV FASTAPI_ENV=development

WORKDIR $SETUP_PATH

# Copy uv and the virtual env to current image
COPY --from=builder-base /usr/local/bin/uv /usr/local/bin/uv
COPY --from=builder-base $SETUP_PATH $SETUP_PATH

ENV UV_PROJECT_ENVIRONMENT="$VENV_PATH"

# Install test/openvino/ollama groups on top of runtime/openvino deps.
RUN uv sync --group openvino --group test --group ollama --no-install-project

# Source code will be mounted here
WORKDIR /app

USER appuser

EXPOSE 8888

CMD ["uvicorn", "app.server:app", "--host", "0.0.0.0", "--port", "8888", "--reload"]


# `prod` image used for runtime
FROM python-base AS prod
ENV FASTAPI_ENV=production

WORKDIR /my-app

RUN apt-get update && apt-get install --no-install-recommends --fix-missing -y \
    libmagic-dev && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy the virtual env and dependency metadata
COPY --from=builder-base $SETUP_PATH $SETUP_PATH


# Prepare directories for model cache and config
RUN mkdir -p /tmp/model_cache /tmp/model_config

# Copy application code and model config
COPY app ./app
COPY model_config/sample/openvino_template.yaml /tmp/model_config/default_model.yaml

# Set ownership to appuser
RUN chown -R appuser:appuser /my-app /tmp/model_cache /tmp/model_config

USER appuser

EXPOSE 8888

CMD ["uvicorn", "app.server:app", "--host", "0.0.0.0", "--port", "8888"]
