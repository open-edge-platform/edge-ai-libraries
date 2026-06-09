# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
FROM intel/dlstreamer:2026.1.0-ubuntu24-rc1.1

ARG APP_UID=1000
ARG APP_GID=1000

USER root

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app/audio_analyzer

RUN apt-get update \
    && apt-get install -y --no-install-recommends alsa-utils python3-venv \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./requirements.txt

RUN python3 -m venv "$VIRTUAL_ENV" \
    && "$VIRTUAL_ENV/bin/pip" install --upgrade pip \
    && "$VIRTUAL_ENV/bin/pip" install -r requirements.txt

COPY . .

RUN mkdir -p /app/audio_analyzer/models/openvino \
    && mkdir -p /app/audio_analyzer/models/dummy \
    && mkdir -p /app/audio_analyzer/chunks/dummy \
    && mkdir -p /app/audio_analyzer/storage/dummy \
    && mkdir -p /app/audio_analyzer/.cache/dummy \
    && touch /app/audio_analyzer/models/.keep \
    && touch /app/audio_analyzer/models/openvino/.keep \
    && touch /app/audio_analyzer/chunks/.keep \
    && touch /app/audio_analyzer/storage/.keep \
    && touch /app/audio_analyzer/.cache/.keep \
    && chown -R ${APP_UID}:${APP_GID} /app/audio_analyzer

USER ${APP_UID}:${APP_GID}

EXPOSE 8010

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8010/health', timeout=5).read()"

CMD ["python3", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8010"]
