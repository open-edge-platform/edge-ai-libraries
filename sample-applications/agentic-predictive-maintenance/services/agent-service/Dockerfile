# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

FROM python:3.12-slim

LABEL org.opencontainers.image.title="APM Agent Service"
LABEL org.opencontainers.image.description="LangGraph multi-agent orchestration for agentic predictive maintenance"
LABEL org.opencontainers.image.vendor="Intel Corporation"

WORKDIR /app

RUN groupadd -r appuser && useradd -r -g appuser -u 1001 appuser

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

RUN mkdir -p /configs /configs/prompts && chown -R appuser:appuser /configs

USER appuser

EXPOSE 5002

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "5002", "--workers", "1"]
