# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.10.11 /uv /uvx /bin/

WORKDIR /app

RUN groupadd -r appuser && useradd -r -g appuser -u 1001 appuser

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-group test --no-install-project

ENV PATH="/app/.venv/bin:$PATH"

COPY src/ ./src/

RUN mkdir -p /app/output && chown -R appuser:appuser /app/output

USER appuser

EXPOSE 5002

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "5002", "--workers", "1"]
