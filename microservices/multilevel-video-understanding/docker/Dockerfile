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
    POETRY_VERSION=2.4.1 \
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

RUN groupadd appuser && useradd -m -s /bin/bash -g appuser appuser

# Add poetry and venv to path
ENV PATH="$POETRY_HOME/bin:$VENV_PATH/bin:$PATH"
ENV HOME=/home/appuser

# Install dependencies to be used in final stages
RUN apt update -y && apt install -y curl

# Upgrade pip to the latest version
RUN pip install --upgrade pip 

FROM python-base AS builder-base

# Install system dependencies
RUN apt-get update -y && apt-get install --no-install-recommends --fix-missing -y \
    git \
    build-essential \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install poetry 2.4.1 - based on $POETRY_VERSION env var
RUN pip install --no-cache-dir "poetry==${POETRY_VERSION}"

WORKDIR $SETUP_PATH
# Copy poetry configuration files
COPY pyproject.toml poetry.lock ./

# Install dependencies without dev dependencies
RUN poetry lock && poetry install --no-root --no-interaction --no-ansi

# Install video-chunking-utils from OEP/EAL source.
RUN git clone --depth 1 https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries
RUN pip install $SETUP_PATH/edge-ai-libraries/libraries/video-chunking-utils/ && \
    rm -rf $SETUP_PATH/edge-ai-libraries

# JWT token clean up
RUN [ -f $VENV_PATH/lib/python3.13/site-packages/skimage/data/_fetchers.py ] && \
    sed -i '/>>>.*token=/d' $VENV_PATH/lib/python3.13/site-packages/skimage/data/_fetchers.py
    
# Production stage - optimized for deployment
FROM python-base AS prod

ENV FASTAPI_ENV=production
COPY --from=builder-base $SETUP_PATH $SETUP_PATH

# Install dependencies to be used in runtime
RUN apt-get update -y && apt-get install --no-install-recommends -y \
    libsm6 \
    libxext6 \
    libxrender1 \
    libgl1

# Download copyleft sources if requested
RUN mkdir -p /copyleft_sources/deb
WORKDIR /copyleft_sources/deb
RUN sed -Ei "s/Types: deb/Types: deb deb-src/g" /etc/apt/sources.list.d/debian.sources && \
    apt-get update -y && \
    apt-get install --no-install-recommends -y libglib2.0-0 && \
    apt-get source --no-install-recommends -q --download-only glib2.0

WORKDIR /app

# Copy the application code for production
COPY . /app/

# Pre-create the runtime prompt-registry cache mountpoint. The container runs
# with a read-only root filesystem, so the bind mount target must already
# exist inside the image as an empty directory.
RUN mkdir -p /home/appuser/.cache/.multilevel-video-understanding \
    && chown -R appuser:appuser /app /home/appuser/.cache

# Drop pip from the runtime image. pip ships its own vendored dependency inventory
# (pip/_vendor/vendor.txt + bom.cdx.json) pinning setuptools 70.3.0 and msgpack 1.1.2,
# which scanners report as installed packages - independent of pyproject.toml,
# poetry.lock or any setuptools upgrade. Nothing at runtime needs pip.
RUN rm -rf /usr/local/lib/python3.13/site-packages/pip \
           /usr/local/lib/python3.13/site-packages/pip-*.dist-info \
           /usr/local/lib/python3.13/ensurepip \
           /usr/local/bin/pip /usr/local/bin/pip3 /usr/local/bin/pip3.13 \
           $VENV_PATH/lib/python3.13/site-packages/pip \
           $VENV_PATH/lib/python3.13/site-packages/pip-*.dist-info \
           $VENV_PATH/bin/pip $VENV_PATH/bin/pip3 $VENV_PATH/bin/pip3.13

USER appuser

EXPOSE 8000

# Run Uvicorn for production
CMD ["uvicorn", "video_analyzer.main:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-keep-alive", "180"]