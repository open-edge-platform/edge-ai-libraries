# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

FROM python:3.12-slim

LABEL org.opencontainers.image.title="APM Storage Service"
LABEL org.opencontainers.image.description="SQLite REST API for agentic predictive maintenance"
LABEL org.opencontainers.image.vendor="Intel Corporation"

WORKDIR /app

RUN groupadd -r appuser && useradd -r -g appuser -u 1001 appuser

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

RUN mkdir -p /data && chown appuser:appuser /data

USER appuser

EXPOSE 5001

CMD ["uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "5001", "--workers", "1"]
