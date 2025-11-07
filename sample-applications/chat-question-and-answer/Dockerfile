# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# --- Stage 1: Build dependencies ---
FROM python:3.11-slim AS python-base

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system build dependencies (added libpq-dev, gcc, python3-dev for psycopg/pg_config support)
RUN apt-get update -y && \
    apt-get install -y --no-install-recommends \
    libjemalloc-dev \
    libpq-dev gcc python3-dev \
    curl && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* && \
    pip install --no-cache-dir --upgrade pip setuptools poetry

# Copy only dependency files
WORKDIR /app
COPY pyproject.toml poetry.lock README.md ./

# Install dependencies in a temporary location
RUN poetry config virtualenvs.create false && \
    poetry install --only main --no-root && \
    rm -rf ~/.cache

# --- Stage 2: Final slim image ---
FROM python:3.11-slim

ENV HOME="/home/appuser"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Add non-root user
RUN groupadd -g 1001 appuser && \
    useradd -m -s /bin/bash -u 1001 -g 1001 appuser && \
    mkdir -p $HOME/.cache/huggingface && \
    chown -R appuser:appuser $HOME

# Install only runtime dependencies (added libpq5)
RUN apt-get update -y && \
    apt-get install -y --no-install-recommends \
    libjemalloc2 libpq5 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /my-app

# Copy installed packages from python-base
COPY --from=python-base /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=python-base /usr/local/bin /usr/local/bin

# Copy application code
COPY app ./app

# Set permissions
RUN chown -R appuser:appuser /my-app

USER appuser

EXPOSE 8080

CMD uvicorn app.server:app --host 0.0.0.0 --port 8080
