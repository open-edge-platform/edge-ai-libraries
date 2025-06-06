# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

FROM python:3.12.10-slim AS build

ARG ARCH="cpu"

RUN apt-get update -y && apt-get install -y --no-install-recommends --fix-missing \
    curl

RUN pip install --upgrade --no-cache pip setuptools && \
    pip install --no-cache torch~=2.7.1 torchvision~=0.22.1 --index-url https://download.pytorch.org/whl/cpu;

RUN pip install poetry

RUN poetry config virtualenvs.create false

WORKDIR /app

COPY poetry.lock pyproject.toml /app/
RUN poetry install --no-root

COPY . .
RUN mkdir -p /tmp/dataprep/videos
RUN mkdir -p /app/ov-models
EXPOSE 8000

CMD ["gunicorn", "-b", "0.0.0.0:8000", "-k", "uvicorn.workers.UvicornWorker", "app:app", "--timeout", "300", "--log-level", "debug"]