# syntax=docker/dockerfile:1
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN --mount=type=cache,id=okf-extractor-pip,target=/root/.cache/pip,sharing=locked \
    pip install -r /app/requirements.txt \
    && useradd --create-home --uid 1000 extractor
COPY . /app/okf_extractor/

ENV PYTHONUNBUFFERED=1 \
    OKF_EXTRACTOR_HOST=0.0.0.0 \
    OKF_EXTRACTOR_PORT=8080
USER extractor
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=5 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.getenv('OKF_EXTRACTOR_PORT', '8080') + '/health')"
ENTRYPOINT ["python", "-m", "okf_extractor"]