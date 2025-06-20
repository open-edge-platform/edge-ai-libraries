# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

FROM python:3.12.10-slim AS build

ARG ARCH="cpu"
ARG USER_ID=1000
ARG USER_GROUP_ID=1000

RUN apt-get update -y && apt-get install -y --no-install-recommends --fix-missing \
    curl

RUN pip install --upgrade --no-cache pip setuptools && \
    pip install --no-cache torch~=2.7.1 torchvision~=0.22.1 --index-url https://download.pytorch.org/whl/cpu;

RUN pip install poetry

RUN poetry config virtualenvs.create false

RUN groupadd -g ${USER_GROUP_ID} appuser && useradd -m -s /bin/bash -u ${USER_ID} -g ${USER_GROUP_ID} appuser

WORKDIR /app

COPY poetry.lock pyproject.toml /app/
RUN poetry install --no-root

COPY . .
RUN mkdir -p /tmp/dataprep/videos
RUN mkdir -p /home/appuser/.cache/huggingface /app/ov-models && \
    chown -R appuser:appuser /home/appuser/.cache /app/ov-models

USER appuser

EXPOSE 8000

CMD ["gunicorn", "-b", "0.0.0.0:8000", "-k", "uvicorn.workers.UvicornWorker", "app:app", "--timeout", "300", "--log-level", "info", "--access-logfile", "-", "--error-logfile", "-", "--log-config", "/app/logging.conf"]