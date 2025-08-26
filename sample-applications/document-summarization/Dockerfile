# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Multi-stage build: Build stage
FROM python:3.11-slim AS builder

# Set environment variables for PythonAdd commentMore actions
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends python3-dev \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir poetry==2.1.3

WORKDIR /app

# Copy the application code
COPY pyproject.toml ./
RUN poetry config virtualenvs.create false \
    && poetry install --only=main --no-root \
    && poetry cache clear pypi --all

# Download NLTK corpora (stopwords + punkt)
RUN mkdir -p /opt/share/nltk_data \
 && python -m nltk.downloader -d /opt/share/nltk_data stopwords punkt

FROM python:3.11-slim AS runtime

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME="/home/appuser" \
    PYTHONPATH="/app" \
    NLTK_DATA="/opt/share/nltk_data"

# Install only runtime system dependenciesAdd commentMore actions
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Required for document processing
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf /tmp/* \
    && rm -rf /var/tmp/*

# Create non-root userAdd commentMore actions
RUN groupadd -g 1001 appuser \
    && useradd -r -m -s /bin/bash -u 1001 -g 1001 appuser \
    && mkdir -p $HOME/.cache/huggingface \
    && chown -R appuser:appuser $HOME

# Copy Python packages from builder stageAdd commentMore actions
COPY --from=builder /opt/share/nltk_data /opt/share/nltk_data
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Set working directoryAdd commentMore actions
WORKDIR /app

# Copy application code
COPY --chown=appuser:appuser app ./app
COPY --chown=appuser:appuser ui ./ui

# Set ownership for nltk_data
RUN chown -R appuser:appuser /opt/share/nltk_data

# Switch to non-root userAdd commentMore actions
USER appuser

# Expose the port the app runs on
EXPOSE 8000

# Command to run the application
CMD uvicorn app.server:app --host 0.0.0.0 --port 8000
