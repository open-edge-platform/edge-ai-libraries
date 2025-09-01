# Copyright (C) 2025 Intel Corporation
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
    VENV_PATH="/opt/projsetup/.venv"

# Add poetry and venv to path
ENV PATH="$POETRY_HOME/bin:$VENV_PATH/bin:$PATH"

# Upgrade pip and setuptools to the latest version to fix vuln
RUN /usr/local/bin/pip install --upgrade pip setuptools

# Create a non-root user
RUN groupadd -g 1001 intelgai && \
    useradd -m -s /bin/bash -u 1001 -g 1001 intelgai && \
    chown -R intelgai:intelgai $HOME


FROM python-base AS builder-base
RUN apt-get update && apt-get install --no-install-recommends -y curl build-essential && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Install poetry. Installs in $POETRY_HOME with version $POETRY_VERSION
RUN curl -sSL https://install.python-poetry.org | python -

WORKDIR $SETUP_PATH
COPY poetry.lock pyproject.toml ./
# Install runtime (prod) deps. Uses $POETRY_VIRTUALENVS_IN_PROJECT to create venv.
RUN poetry install --no-dev && \
    rm -rf ~/.cache/pypoetry/* ~/.cache/pip/*


# `dev` image is used during development / testing
FROM python-base AS dev
ENV FASTAPI_ENV=development

WORKDIR $SETUP_PATH

# Copy the poetry installation and the virtual env to current image
COPY --from=builder-base $POETRY_HOME $POETRY_HOME
COPY --from=builder-base $SETUP_PATH $SETUP_PATH

# Install dev dependencies. Prod dependencies are already installed.
RUN poetry install --with dev

# Source code will be mounted here
WORKDIR /app

EXPOSE 8000

CMD ["uvicorn", "--host", "0.0.0.0", "--reload", "app.main:app"]


# `prod` image used for runtime
FROM python-base AS prod
ENV FASTAPI_ENV=production

COPY --from=builder-base $SETUP_PATH $SETUP_PATH
COPY . /app/
WORKDIR /app

USER intelgai

EXPOSE 8000

CMD ["uvicorn", "--host", "0.0.0.0", "app.main:app"]
