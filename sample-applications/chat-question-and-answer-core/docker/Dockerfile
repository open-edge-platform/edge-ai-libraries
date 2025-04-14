# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
FROM python:3.11-slim AS python-base

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
    VENV_PATH="/opt/projsetup/.venv" \
    HOME="/home/intelgai"

# Add poetry and venv to path
ENV PATH="$POETRY_HOME/bin:$VENV_PATH/bin:$PATH"

# Upgrade pip and setuptools to the latest version to fix vuln
RUN /usr/local/bin/pip install --upgrade pip setuptools

# Create a non-root user
RUN groupadd -g 1001 intelgai && \
    useradd -m -s /bin/bash -u 1001 -g 1001 intelgai && \
    chown -R intelgai:intelgai $HOME


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
    libglib2.0-0

WORKDIR $SETUP_PATH

# Copy the poetry installation and the virtual env to current image
COPY --from=builder-base $POETRY_HOME $POETRY_HOME
COPY --from=builder-base $SETUP_PATH $SETUP_PATH

# Install dev dependencies. Prod dependencies are already installed.
RUN poetry install --with dev

# Source code will be mounted here
WORKDIR /app

USER intelgai

EXPOSE 8888

CMD uvicorn app.server:app --host 0.0.0.0 --port 8888 --reload

# `prod` image used for runtime
FROM python-base AS prod
ENV FASTAPI_ENV=production

# Install runtime dependency for opencv
RUN apt-get update && apt-get install --no-install-recommends --fix-missing -y \
    libgl1-mesa-glx \
    libglib2.0-0

COPY --from=builder-base $SETUP_PATH $SETUP_PATH

RUN sed -i 's/tokenizer.pad_token_id = model.config.eos_token_id/tokenizer.pad_token_id = tokenizer.eos_token_id/' \
    /opt/projsetup/.venv/lib/python3.11/site-packages/langchain_huggingface/llms/huggingface_pipeline.py

COPY . /app/
RUN rm -rf /app/tests /app/ui
WORKDIR /app

RUN mkdir /tmp/model_cache && \
    chown intelgai:intelgai /tmp/model_cache

USER intelgai

EXPOSE 8888

CMD uvicorn app.server:app --host 0.0.0.0 --port 8888
