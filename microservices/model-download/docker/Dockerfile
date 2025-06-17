# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# --- Stage 1: Build dependencies ---
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV POETRY_VERSION=1.5.1
ENV POETRY_HOME=/opt/poetry
ENV PATH="/opt/poetry/bin:$PATH"

# Install system build dependencies and poetry
RUN apt-get update -y && \
    apt-get install -y --no-install-recommends \
    curl \
    git \
    build-essential && \
    curl -sSL https://install.python-poetry.org | python3 - && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy only dependency files
WORKDIR /app
COPY pyproject.toml poetry.lock ./

# Install dependencies in a temporary location
RUN poetry config virtualenvs.create false && \
    poetry install --only main --no-root --no-interaction --no-ansi && \
    rm -rf ~/.cache

# --- Stage 2: Final slim image ---
FROM python:3.11-slim

ENV HOME="/home/user"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Add non-root user and install runtime dependencies
RUN groupadd -g 1001 user && \
    useradd -m -s /bin/bash -u 1001 -g 1001 user && \
    mkdir -p $HOME/.cache/huggingface && \
    apt-get update -y && \
    apt-get install -y --no-install-recommends \
    git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && chown -R user:user $HOME

# Set the working directory in the container
WORKDIR /app

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy the rest of the application files into the container
COPY app /app

RUN chown -R user:user /app

USER user
# Expose the port the app runs on
EXPOSE 8000

# Command to run the application
CMD ["uvicorn", "--host", "0.0.0.0", "main:app"]