# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Common base image with system dependencies
FROM python:3.13-slim AS python-base

# Setting env vars for python, pip and poetry
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=off \ 
    # off value above actually emplies, no cache will be used. Confusing.
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100 \
    POETRY_VERSION=1.8.5 \
    # Poetry installation location
    POETRY_HOME="/opt/poetry" \
    # Create the virtual environment dir .venv in the project's root
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    # Disable interactive prompts
    POETRY_NO_INTERACTION=1 \
    # Location where packages gets installed
    SETUP_PATH="/opt/projsetup" \
    # Location where virtual env is created
    VENV_PATH="/opt/projsetup/.venv"

# Add poetry and venv to path
ENV PATH="$PATH:$POETRY_HOME/bin:$VENV_PATH/bin"

# Install curl to be used for health checks in final stages
RUN apt update -y && apt install -y curl
# Upgrade pip to the latest version
RUN pip install --upgrade pip 

# Commenting out the packages used for GPU drivers installations - as something is not right here
#============================================================================
# RUN apt-get update && apt-get install --no-install-recommends --fix-missing -y \
#     wget \
#     gnupg2 \
#     apt-transport-https \
#     ca-certificates \
#     && apt-get clean \
#     && rm -rf /var/lib/apt/lists/*

# # Set up Intel APT repository with proper key handling
# RUN wget -qO - https://apt.repos.intel.com/intel-gpg-keys/GPG-PUB-KEY-INTEL-SW-PRODUCTS.PUB | \
#     apt-key add - && \
#     echo "deb https://apt.repos.intel.com/oneapi all main" > \
#     /etc/apt/sources.list.d/oneAPI.list

# # Install Intel oneAPI and OpenVINO runtime dependencies
# RUN apt-get update && apt-get install -y --no-install-recommends --fix-missing \
#     intel-oneapi-runtime-opencl \
#     intel-oneapi-runtime-compilers \
#     intel-oneapi-runtime-libs \
#     intel-oneapi-runtime-dpcpp-cpp \
#     intel-oneapi-python \
#     && apt-get clean \
#     && rm -rf /var/lib/apt/lists/*
# ============================================================================

# Common environment variables
ENV INTEL_OPENVINO_DIR=/opt/intel/openvino
ENV LD_LIBRARY_PATH=/opt/intel/openvino/runtime/lib/intel64:/opt/intel/openvino/runtime/3rdparty/tbb/lib:/opt/intel/openvino/runtime/3rdparty/hddl/lib:$LD_LIBRARY_PATH
ENV PYTHONPATH=/opt/intel/openvino/python:$PYTHONPATH
ENV OUTPUT_DIR=/data
ENV UPLOAD_DIR=/data/uploads
ENV AUDIO_DIR=/data/audio
ENV GGML_MODEL_DIR=/models/ggml
ENV OPENVINO_MODEL_DIR=/models/openvino


FROM python-base AS builder-base

# Install system dependencies
RUN apt-get update && apt-get install --no-install-recommends --fix-missing -y \
    git \
    build-essential \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install poetry 1.8.3 - based on $POETRY_VERSION env var
RUN curl -sSL https://install.python-poetry.org | python -

WORKDIR $SETUP_PATH
# Copy poetry configuration files
COPY pyproject.toml poetry.lock ./

# Install dependencies without dev dependencies
RUN poetry lock --no-update && poetry install --no-dev --no-interaction --no-ansi

# Development stage - with dev dependencies and hot reload
FROM python-base AS dev

ENV FASTAPI_ENV=development
WORKDIR $SETUP_PATH

# Copy the poetry installation and the virtual env to current image
COPY --from=builder-base $POETRY_HOME $POETRY_HOME
COPY --from=builder-base $SETUP_PATH $SETUP_PATH

# Install remaining dev dependencies
RUN poetry install --no-interaction --no-ansi

# In dev mode, the application code will be mounted to /app from host to allow hot-reloads
WORKDIR /app

EXPOSE 8000
# Run with reload for development and increased timeout
CMD ["uvicorn", "audio_analyzer.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--timeout-keep-alive", "200"]

# Production stage - optimized for deployment
FROM python-base AS prod

ENV FASTAPI_ENV=production
COPY --from=builder-base $SETUP_PATH $SETUP_PATH

WORKDIR /app
# Copy the application code for production
COPY . /app/

# Optionally download copyleft sources if requested
ARG COPYLEFT_SOURCES=false
RUN if [ "$COPYLEFT_SOURCES" = "true" ]; then \
        apt-get update && \
        # Get list of installed deb packages with copyleft licenses \
        sed -Ei 's/# deb-src /deb-src /' /etc/apt/sources.list && \
        apt-get update && \
        mkdir -p /copyleft_sources/deb && cd /copyleft_sources/deb && \
        echo -n $null > copyleft_package_list.txt && \
        for package in $(dpkg -l | awk '/^ii/ {print $2}' | cut -d: -f1); do \
            grep -l 'Copyleft\|GPL\|LGPL\|EPL\|MPL\|CDDL' /usr/share/doc/${package}/copyright; \
            exit_status=$?; \
            if [ $exit_status -eq 0 ]; then \
                echo $package >> copyleft_package_list.txt; \
                apt-get source -q --download-only $package; \
            fi; \
        done; \
        # Get source code for installed Python packages with copyleft licenses \
        mkdir -p /copyleft_sources/python && \
        cd /copyleft_sources/python && \
        apt-get update && apt-get install -y gcc build-essential libffi-dev python3-dev && \
        # Download python package sources with relevant licenses \
        pip3 freeze | cut -d= -f1 | while read pkg; do \
            meta=$(pip3 show $pkg 2>/dev/null); \
            lic=$(echo "$meta" | grep -i '^License:' | grep -E 'MPL|GPL|General Public License|EPL|Eclipse Public License|CDDL|LGPL'); \
            if [ ! -z "$lic" ]; then \
                echo "Downloading source for $pkg with license: $lic"; \
                pip3 download --no-binary :all: $pkg || true; \
            fi; \
        done; \
        apt-get remove --purge -y gcc build-essential libffi-dev python3-dev; \
    fi

EXPOSE 8000
# Create a mini script on-the-fly to run Gunicorn with Uvicorn worker
RUN echo '#!/bin/bash\n\
exec gunicorn audio_analyzer.main:app \
--workers=4 \
--worker-class=uvicorn.workers.UvicornWorker \
--bind=0.0.0.0:8000 \
--timeout=200 \
--keep-alive=200 \
--log-level=${LOG_LEVEL:-info} \
--forwarded-allow-ips="*" \
--access-logfile=- \
--error-logfile=-\n' > /app/gunicorn_start.sh && chmod +x /app/gunicorn_start.sh

# Run Gunicorn with Uvicorn workers for production
CMD ["/app/gunicorn_start.sh"]