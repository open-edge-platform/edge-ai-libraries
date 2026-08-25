# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# ---------------------------------------------------------------------------
# Stage 1 — dependency installer
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
COPY pyproject.toml ./
COPY uv.lock ./
RUN uv sync --no-dev --no-install-project 

# ---------------------------------------------------------------------------
# Stage 2 — lean runtime image
# ---------------------------------------------------------------------------
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    SNAPSHOT_DIR=/app/snapshots

RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m appuser

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH"

COPY --chown=appuser:appuser src/ ./src/
COPY --chown=appuser:appuser resources/tools.json ./resources/tools.json

RUN mkdir -p /app/snapshots /app/resources \
    && chown -R appuser:appuser /app/snapshots /app/resources

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -sf http://localhost:${PORT}/v1/health || exit 1

CMD ["sh", "-c", "uvicorn src.main:app --host 0.0.0.0 --port 8000"]
