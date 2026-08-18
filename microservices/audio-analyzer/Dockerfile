# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
FROM intel/dlstreamer:2026.2.0-ubuntu24-rc1

ARG APP_UID=1000
ARG APP_GID=1000
# HF_TOKEN: HuggingFace token required to download gated pyannote models.
# Pass at build time with --build-arg HF_TOKEN=<token> or at runtime via -e HF_TOKEN=<token>.
ARG HF_TOKEN=""

USER root

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    HF_TOKEN=${HF_TOKEN}

WORKDIR /app/audio_analyzer

# Upgrade linux-libc-dev (and any other packages with available security fixes) to remediate
# known kernel-header CVEs (e.g. CVE-2026-31402/31637/43011/43037/43038/43185/43304/43501/
# 45988/46043/46135/52955/52989/52993/53002) inherited from the base image before installing
# app dependencies.
RUN apt-get update \
    && apt-get upgrade -y --only-upgrade linux-libc-dev \
    && apt-get install -y --no-install-recommends alsa-utils ffmpeg libsndfile1 python3-venv \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./requirements.txt

RUN python3 -m venv "$VIRTUAL_ENV" \
    && "$VIRTUAL_ENV/bin/pip" install --upgrade pip \
    && "$VIRTUAL_ENV/bin/pip" install -r requirements.txt \
    && ("$VIRTUAL_ENV/bin/pip" uninstall -y torchcodec || true)

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

# Port is overridable so deployments can bind the port their orchestration
# expects (VSS's compose, for example, maps the container's port 8000).
ENV AUDIO_ANALYZER_SERVER_PORT=8010

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python3 -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('AUDIO_ANALYZER_SERVER_PORT','8010')+'/health', timeout=5).read()"

CMD ["sh", "-c", "exec python3 -m uvicorn main:app --host 0.0.0.0 --port \"${AUDIO_ANALYZER_SERVER_PORT:-8010}\""]
