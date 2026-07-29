# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
FROM intel/dlstreamer:2026.1.0-ubuntu24

ARG APP_UID=1000
ARG APP_GID=1000
ARG NPU_DRIVER_VERSION="1.33.0"
ARG NPU_DRIVER_BUILD="v1.33.0.20260529-26625960453-ubuntu2404"
ARG LEVEL_ZERO_VERSION="1.27.0-1~24.04~ppa2"
ARG LEVEL_ZERO_PPA_SNAPSHOT="20260324T100000Z"
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

RUN apt-get update \
    && apt-get install -y --no-install-recommends alsa-utils ffmpeg libsndfile1 python3-venv \
    && rm -rf /var/lib/apt/lists/*

# Install Intel NPU user-space runtime/compiler stack plus oneAPI Level Zero loader.
RUN mkdir -p /tmp/npu_deps && cd /tmp/npu_deps \
    && apt-get update \
    && apt-get install -y --no-install-recommends libtbb12 curl \
    && curl -L --retry 5 --retry-delay 5 --retry-all-errors -O https://github.com/intel/linux-npu-driver/releases/download/v${NPU_DRIVER_VERSION}/linux-npu-driver-${NPU_DRIVER_BUILD}.tar.gz \
    && tar -xf linux-npu-driver-${NPU_DRIVER_BUILD}.tar.gz \
    && curl -L --retry 5 --retry-delay 5 --retry-all-errors -O https://snapshot.ppa.launchpadcontent.net/kobuk-team/intel-graphics/ubuntu/${LEVEL_ZERO_PPA_SNAPSHOT}/pool/main/l/level-zero-loader/libze1_${LEVEL_ZERO_VERSION}_amd64.deb \
    && dpkg -i ./*.deb \
    && ldconfig \
    && test -e /usr/lib/x86_64-linux-gnu/libze_loader.so.1 \
    && rm -rf /tmp/npu_deps \
    && apt-get purge -y curl \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./requirements.txt

RUN python3 -m venv "$VIRTUAL_ENV" \
    && "$VIRTUAL_ENV/bin/pip" install --upgrade pip \
    && "$VIRTUAL_ENV/bin/pip" install -r requirements.txt \
    && "$VIRTUAL_ENV/bin/pip" uninstall -y torchcodec || true

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
