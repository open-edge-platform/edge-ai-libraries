# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
FROM openvino/ubuntu22_runtime:2026.1.0

ARG APP_UID=1000
ARG APP_GID=1000

USER root

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app/text-to-speech

RUN apt-get update \
    && apt-get install -y --no-install-recommends libsndfile1 python3-pip sox \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./requirements.txt

RUN python3 -m pip install --upgrade pip \
    && python3 -m pip install -r requirements.txt


COPY . .

# Ensure all relevant directories exist and contain a .keep file so Docker copies ownership
RUN mkdir -p /app/text-to-speech/models/openvino \
    && mkdir -p /app/text-to-speech/storage/dummy \
    && mkdir -p /app/text-to-speech/.cache/dummy \
    && touch /app/text-to-speech/models/.keep \
    && touch /app/text-to-speech/models/openvino/.keep \
    && touch /app/text-to-speech/storage/.keep \
    && touch /app/text-to-speech/.cache/.keep \
    && chown -R ${APP_UID}:${APP_GID} /app/text-to-speech

USER ${APP_UID}:${APP_GID}

EXPOSE 8011

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8011/health', timeout=5).read()"

CMD ["python3", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8011"]
