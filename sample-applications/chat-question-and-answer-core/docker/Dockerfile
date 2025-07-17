# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
FROM python:3.11-slim AS python-base

# Define a build-time variable to determine if GPU drivers should be installed
ARG USE_GPU=false
ARG GPU_TYPE="none"  # Options: none, igpu, dgpu
ARG INSTALL_DRIVER_VERSION="24.39.31294"
ARG UID=1000
ARG GID=1000

RUN echo "USE_GPU is set to $USE_GPU"; \
    echo "GPU_TYPE is set to $GPU_TYPE"

# Copy drivers and set execute permissions on all .sh files
COPY ./drivers /tmp/drivers
RUN chmod +x /tmp/drivers/*.sh

# Install GPU drivers if required
RUN if [ "$USE_GPU" = "true" ]; then \
    if [ "$GPU_TYPE" != "igpu" ] && [ "$GPU_TYPE" != "dgpu" ]; then \
    echo "ERROR: GPU_TYPE must be set to 'igpu' or 'dgpu' when USE_GPU is set to true"; \
    exit 1; \
    fi && \
    if [ "$GPU_TYPE" = "igpu" ]; then \
    echo "Installing iGPU drivers"; \
    /tmp/drivers/install_igpu_drivers.sh; \
    elif [ "$GPU_TYPE" = "dgpu" ]; then \
    echo "Installing dGPU drivers version $INSTALL_DRIVER_VERSION"; \
    apt-get update && apt-get install -y --no-install-recommends ca-certificates libxml2; \
    /tmp/drivers/install_dgpu_drivers.sh; \
    fi; \
    else \
    if [ "$GPU_TYPE" != "none" ]; then \
    echo "USE_GPU is set to false. No GPU drivers will be installed. Only CPU is supported."; \
    fi; \
    apt-get clean && \
    rm -rf /tmp/drivers /var/lib/apt/lists/* /tmp/*; \
    fi

# Setting env vars for python, pip and poetry
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100 \
    POETRY_VERSION=1.8.3 \
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
ENV PATH="$POETRY_HOME/bin:$VENV_PATH/bin:$PATH"

# Upgrade pip and setuptools to the latest version to fix vuln
RUN /usr/local/bin/pip install --upgrade --no-cache-dir pip setuptools

# Create a non-root user
RUN groupadd -g ${GID} appuser && \
    useradd -m -s /bin/bash -u ${UID} -g ${GID} appuser && \
    chown -R appuser:appuser $HOME


FROM python-base AS builder-base
RUN apt-get update && apt-get install --no-install-recommends -y curl build-essential

# Install poetry. Installs in $POETRY_HOME with version $POETRY_VERSION
RUN curl -sSL https://install.python-poetry.org | python -

WORKDIR $SETUP_PATH
COPY poetry.lock pyproject.toml ./
# Install runtime (prod) deps. Uses $POETRY_VIRTUALENVS_IN_PROJECT to create venv.
RUN poetry install --only main


# `dev` image is used during development / testing
FROM python-base AS dev
ENV FASTAPI_ENV=development

# Install runtime dependency for opencv
RUN apt-get update && apt-get install --no-install-recommends --fix-missing -y \
    libgl1-mesa-glx \
    libglib2.0-0 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR $SETUP_PATH

# Copy the poetry installation and the virtual env to current image
COPY --from=builder-base $POETRY_HOME $POETRY_HOME
COPY --from=builder-base $SETUP_PATH $SETUP_PATH

# Install dev dependencies. Prod dependencies are already installed.
RUN poetry install --with dev

# Source code will be mounted here
WORKDIR /app

USER appuser

EXPOSE 8888

CMD uvicorn app.server:app --host 0.0.0.0 --port 8888 --reload

# `prod` image used for runtime
FROM python-base AS prod
ENV FASTAPI_ENV=production

WORKDIR /my-app

# Install runtime dependency for opencv
RUN apt-get update && apt-get install --no-install-recommends --fix-missing -y \
    libmagic-dev \
    libgl1-mesa-glx \
    libglib2.0-0 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy the poetry installation and the virtual env
COPY --from=builder-base $SETUP_PATH $SETUP_PATH

RUN sed -i 's/tokenizer.pad_token_id = model.config.eos_token_id/tokenizer.pad_token_id = tokenizer.eos_token_id/' \
    /opt/projsetup/.venv/lib/python3.11/site-packages/langchain_huggingface/llms/huggingface_pipeline.py

# Prepare directories for model cache and config
RUN mkdir -p /tmp/model_cache /tmp/model_config

# Copy application code and model config
COPY app ./app
COPY model_config/sample/template.yaml /tmp/model_config/default_model.yaml

# Set ownership to appuser
RUN chown -R appuser:appuser /my-app /tmp/model_cache /tmp/model_config/

USER appuser

EXPOSE 8888

CMD uvicorn app.server:app --host 0.0.0.0 --port 8888
