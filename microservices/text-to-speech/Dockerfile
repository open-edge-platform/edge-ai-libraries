# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
FROM intel/dlstreamer:2026.2.0-ubuntu24

ARG APP_UID=1000
ARG APP_GID=1000

USER root

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app/text-to-speech

# Security hardening flagged by the weekly image scan:
#  - Full apt upgrade pulls in every published Ubuntu security point-release
#    (kernel headers, openssl/libssl3t64, curl, libxml2, glib, python3.12,
#    perl, etc.) without changing package names/major versions.
#  - certifi/setuptools/urllib3 are reinstalled via pip because the base
#    image's bundled system-Python copies lag behind the patched releases;
#    reinstalling (unpinned) pulls the latest available fix.
#  - The base image also leaves orphaned *older* dist-info metadata
#    directories behind for setuptools/urllib3 (not tracked by pip's own
#    RECORD, so `pip install --upgrade` doesn't clean them up). Scanners
#    keep flagging those stale/unused copies even though only the newest
#    version is ever imported, so drop every dist-info except the newest
#    per package name.
#  - NOTE: pip's vendored msgpack (CVE-2026-114613 / GHSA-6v7p-g79w-8964)
#    cannot be fixed here: it ships inside the apt `python3-pip` package,
#    which `python3.12-venv` depends on, and Ubuntu has not published a
#    newer `python3-pip` for noble yet (apt-cache policy candidate == installed).
RUN apt-get update \
    && apt-get install -y --no-install-recommends libsndfile1 python3-venv sox \
    && apt-get -y upgrade \
    && python3 -m pip uninstall -y --break-system-packages certifi \
    && python3 -m pip install --no-cache-dir --break-system-packages --upgrade \
         --ignore-installed pip setuptools urllib3 certifi \
    && for pkg in setuptools urllib3; do \
         latest=$(ls -d /usr/local/lib/python3.12/dist-packages/${pkg}-*.dist-info 2>/dev/null | sort -V | tail -1); \
         for d in /usr/local/lib/python3.12/dist-packages/${pkg}-*.dist-info; do \
           if [ -n "$latest" ] && [ "$d" != "$latest" ]; then rm -rf "$d"; fi; \
         done; \
       done; true \
    && rm -rf /var/lib/apt/lists/*


COPY requirements.txt ./requirements.txt

RUN python3 -m venv "$VIRTUAL_ENV" \
    && "$VIRTUAL_ENV/bin/pip" install --upgrade pip setuptools \
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
