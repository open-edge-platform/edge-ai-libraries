# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
FROM intel/dlstreamer:2026.2.0-ubuntu24-rc2

ARG APP_UID=1000
ARG APP_GID=1000

USER root

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app/text-to-speech

RUN apt-get update \
    && apt-get install -y --no-install-recommends libsndfile1 python3-venv sox \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./requirements.txt

RUN python3 -m venv "$VIRTUAL_ENV" \
    && "$VIRTUAL_ENV/bin/pip" install --upgrade pip \
    && "$VIRTUAL_ENV/bin/pip" install -r requirements.txt


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

# TEXT_TO_SPEECH_WORKERS: number of uvicorn worker PROCESSES (not threads).
# Each Kokoro/inference call is guarded by a per-model threading.Lock (see
# components/tts/base.py::_get_inference_lock) because kokoro-onnx's
# tokenizer/phonemizer relies on the espeak C library's global state, which
# is not thread-safe — so within ONE process, concurrent requests still
# queue behind that lock no matter how many threads uvicorn itself uses.
# Separate OS processes each get their own Python interpreter, memory and
# model instance, sidestepping the shared-state concern entirely and giving
# genuine concurrency for overlapping requests (e.g. a speculative draft's
# pre-synthesis running alongside the real turn's TTS calls). Defaults to 1
# (previous single-process behaviour) so this is opt-in per deployment;
# each additional worker loads its own full model copy (~1GB) and pays a
# separate cold-start on its first request.
ENV TEXT_TO_SPEECH_WORKERS=1

CMD ["sh", "-c", "exec python3 -m uvicorn main:app --host 0.0.0.0 --port 8011 --workers ${TEXT_TO_SPEECH_WORKERS:-1}"]
