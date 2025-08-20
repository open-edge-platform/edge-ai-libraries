# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

FROM python:3.12-slim AS build

# Install poetry
RUN pip install --upgrade --no-cache-dir pip setuptools
RUN pip install --no-cache-dir poetry

# Set working directory
WORKDIR /app

# Copy poetry files
COPY pyproject.toml poetry.lock /app/

# Install dependencies using poetry
RUN poetry config virtualenvs.create false && poetry install --no-root --only=main

FROM python:3.12-slim

ARG USER_ID=1000
ARG USER_GROUP_ID=1000

# Create non-root user
RUN groupadd -g ${USER_GROUP_ID} sceneuser && useradd -m -s /bin/bash -u ${USER_ID} -g ${USER_GROUP_ID} sceneuser

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from build stage
COPY --from=build /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=build /usr/local/bin /usr/local/bin
COPY --from=build /app/poetry.lock /app/poetry.lock

# Set working directory
WORKDIR /app

# Copy application source
COPY src/scene_intelligence /app/scene_intelligence
COPY config /app/config
COPY src/webserver /app/webserver

# Change ownership to non-root user
RUN chown -R sceneuser:sceneuser /app
USER sceneuser

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8080/health || exit 1

# Run the application
CMD ["python", "-m", "scene_intelligence.main"]
