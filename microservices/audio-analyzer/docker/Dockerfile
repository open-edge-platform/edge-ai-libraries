# syntax=docker/dockerfile:1
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
# ================================================================
# PRODUCTION IMAGE — Ubuntu 24.04, multi-stage build.
#
# No GStreamer, librealsense, or rdkafka are installed; the service does
# not use them. The OpenVINO runtime present in the final image is the
# single pip-installed `openvino` wheel pulled in by requirements-slim.txt
# — no OpenVINO package is installed at the OS level.
#
# Variants:
#   --build-arg IMAGE_VARIANT=full   (production default) -- everything in
#       slim, plus the openai/whispercpp ASR providers, diarization
#       (pyannote.audio) and sentiment analysis (speechbrain). See
#       requirements-optional.txt.
#   --build-arg IMAGE_VARIANT=slim   -- openvino-genai Whisper
#       transcription + VSS/MinIO ingestion + on-first-run OpenVINO model
#       export only, for deployments that only need the default ASR path
#       and want the smallest image. See requirements-slim.txt for the
#       exact package list and the reasoning for what is/isn't included.
#
# Optional Chinese/English FunASR Paraformer provider (requirements-cjk.txt):
#   --build-arg INSTALL_CJK=true adds the funasr/modelscope packages. Off
#   by default so the standard image is unchanged for existing consumers.
#
# GPU/NPU userspace runtime:
#   --build-arg INSTALL_GPU_NPU_RUNTIME=true (production default) installs
#   the Intel compute-runtime (GPU) and linux-npu-driver (NPU) userspace
#   packages, following the same install pattern as
#   microservices/multimodal-embedding-serving/docker/Dockerfile. Exact
#   package/version provenance is documented next to the ARGs below. The
#   OpenVINO GPU/NPU plugin .so files ship inside the pip `openvino` wheel
#   itself, so only these userspace driver libraries are needed for the
#   plugins to dlopen successfully -- no system OpenVINO package is
#   installed.
#
# See docs/audio-analyzer-image-optimization.md for measured image sizes,
# the build-variant matrix, and the rationale behind package selections.
#
# Build (from microservices/audio-analyzer/):
#   docker build -f docker/Dockerfile -t audio-analyzer:local .
#   docker build -f docker/Dockerfile -t audio-analyzer:slim-cpu \
#       --build-arg IMAGE_VARIANT=slim --build-arg INSTALL_GPU_NPU_RUNTIME=false .
#   docker build -f docker/Dockerfile -t audio-analyzer:full-cjk \
#       --build-arg INSTALL_CJK=true .
# ================================================================

ARG IMAGE_VARIANT=full

# ---------------------------------------------------------------- builder --
FROM ubuntu:24.04 AS builder

ARG IMAGE_VARIANT
ARG DEBIAN_FRONTEND=noninteractive
# INSTALL_CJK: set to "true" to add the optional FunASR Paraformer provider for
# Chinese/English ASR (requirements-cjk.txt). Off by default so the standard
# image and its existing consumers stay unchanged.
ARG INSTALL_CJK="false"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app/audio_analyzer

# python3.12 ships in Ubuntu 24.04's (noble) default archive -- no deadsnakes
# PPA or source build required, unlike older Ubuntu releases.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3.12 python3.12-venv python3-pip ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-slim.txt requirements-optional.txt requirements-cjk.txt requirements-lock.txt ./

# requirements-lock.txt is a freeze-based constraints file covering both
# variants: `pip install -c` only constrains packages that are actually
# being installed, so full-only entries are ignored when building slim.
RUN python3.12 -m venv "$VIRTUAL_ENV" \
    && "$VIRTUAL_ENV/bin/pip" install --upgrade pip \
    && "$VIRTUAL_ENV/bin/pip" install -r requirements-slim.txt -c requirements-lock.txt \
    && if [ "$IMAGE_VARIANT" = "full" ]; then \
        "$VIRTUAL_ENV/bin/pip" install -r requirements-optional.txt -c requirements-lock.txt; \
    fi \
    # Optional Chinese/English FunASR Paraformer provider. Only installed
    # when the image is built with --build-arg INSTALL_CJK=true; the
    # default build is unchanged for existing consumers. Not constrained
    # via requirements-lock.txt.
    && if [ "$INSTALL_CJK" = "true" ]; then \
        "$VIRTUAL_ENV/bin/pip" install -r requirements-cjk.txt; \
    fi \
    && ("$VIRTUAL_ENV/bin/pip" uninstall -y torchcodec || true) \
    # triton (~0.9GB installed) is a hard dependency of openai-whisper on
    # x86_64 Linux (full variant only), but is only ever imported lazily
    # behind CUDA-only code paths (whisper/timing.py: `if x.is_cuda`).
    # This service's openai provider is CPU-only by design (config.yaml),
    # so that code path never executes and triton is never needed.
    && ("$VIRTUAL_ENV/bin/pip" uninstall -y triton || true) \
    # Strip bundled test directories from installed packages. Conservative
    # pattern: only directories literally named "tests" or "test" directly
    # under a package/dist-info tree -- not a recursive wildcard over
    # arbitrary depth -- to avoid touching anything that happens to have
    # "test" as a meaningful non-test path component.
    && find "$VIRTUAL_ENV/lib/python3.12/site-packages" -maxdepth 2 \
        -type d \( -name "tests" -o -name "test" \) -prune -exec rm -rf {} + \
    # Remove pip itself and its bundled vendor libs from the venv that will
    # be copied into the runtime stage -- the application never invokes
    # pip at runtime (model export shells out to `optimum-cli`, a console
    # script backed by the `optimum` package already installed above, not
    # by pip). Re-installing dependencies later requires rebuilding the
    # image, which is the intended workflow.
    && rm -rf "$VIRTUAL_ENV"/lib/python3.12/site-packages/pip* \
        "$VIRTUAL_ENV"/lib/python3.12/site-packages/setuptools* \
        "$VIRTUAL_ENV"/lib/python3.12/site-packages/wheel* \
        "$VIRTUAL_ENV"/bin/pip* \
    && find "$VIRTUAL_ENV" -type d -name "__pycache__" -prune -exec rm -rf {} +

# ---------------------------------------------------------------- runtime --
FROM ubuntu:24.04 AS runtime

ARG APP_UID=1000
ARG APP_GID=1000
ARG DEBIAN_FRONTEND=noninteractive

# --- Intel GPU/NPU userspace runtime (OPTIONAL) ---------------------------
# Only required if models.asr.device / models.diarization.device / sentiment
# device is set to GPU or NPU. CPU-only deployments (the documented
# default) do not need this layer. No system-level OpenVINO package is
# installed here -- the GPU/NPU plugin .so files ship inside the pip
# `openvino` package itself; only these userspace driver/runtime libs let
# the plugins dlopen. Re-validate the pinned versions below if the pip
# `openvino` version changes.
ARG INSTALL_GPU_NPU_RUNTIME=true
ARG GPU_DRIVER_VERSION="26.18.38308.1"
ARG IGC_VERSION="2.34.4+21428"
ARG NPU_DRIVER_VERSION="1.33.0"
ARG NPU_DRIVER_BUILD="v1.33.0.20260529-26625960453-ubuntu2404"
ARG LEVEL_ZERO_VERSION="1.32.0-1~24.04~ppa1"

# Optional corporate TLS-inspection CA (NOT baked into the repo or the image
# by default -- this RUN step is a no-op unless a build invoker explicitly
# supplies one). Some corporate networks terminate/re-sign outbound HTTPS
# through an SSL-inspecting proxy; the CA that re-signs that traffic is not
# in Ubuntu's default trust store, which can make the curl calls below fail
# with "unable to get local issuer certificate". For such environments, pass
# the environment's own approved root CA (PEM) at build time via a BuildKit
# secret -- it is never written into the Dockerfile, never committed to the
# repo, and only read for the duration of this RUN step:
#   docker build --secret id=corporate_ca,src=/path/to/corporate-ca.pem ...
# TLS verification is never disabled (no curl -k/--insecure); if no secret
# is supplied, this is a pure no-op and behaves exactly as before.
#
# IMPORTANT: the CA is installed and the driver downloads below both happen
# in this SAME RUN step, and the CA file + its trust-store entry are removed
# again (via `update-ca-certificates --fresh`) before this step/layer
# completes. A later `RUN rm` in a subsequent layer would still leave the
# certificate's bytes recoverable in image history, so cleanup must happen
# within this one layer for the CA to be genuinely build-only.
RUN --mount=type=secret,id=corporate_ca,required=false \
    if [ "$INSTALL_GPU_NPU_RUNTIME" = "true" ]; then \
        apt-get update && apt-get install -y --no-install-recommends \
            ca-certificates curl libnuma1 ocl-icd-libopencl1 libtbb12 \
        && CORPORATE_CA_INSTALLED=0 \
        && if [ -s /run/secrets/corporate_ca ]; then \
            cp /run/secrets/corporate_ca /usr/local/share/ca-certificates/corporate-ca.crt \
            && update-ca-certificates \
            && CORPORATE_CA_INSTALLED=1; \
        fi \
        && mkdir -p /tmp/gpu_deps && cd /tmp/gpu_deps \
        && curl -fL --retry 5 --retry-delay 5 --retry-all-errors -O \
            "https://github.com/intel/compute-runtime/releases/download/${GPU_DRIVER_VERSION}/libze-intel-gpu1_${GPU_DRIVER_VERSION}-0_amd64.deb" \
        && curl -fL --retry 5 --retry-delay 5 --retry-all-errors -O \
            "https://github.com/intel/compute-runtime/releases/download/${GPU_DRIVER_VERSION}/intel-opencl-icd_${GPU_DRIVER_VERSION}-0_amd64.deb" \
        && curl -fL --retry 5 --retry-delay 5 --retry-all-errors -O \
            "https://github.com/intel/compute-runtime/releases/download/${GPU_DRIVER_VERSION}/libigdgmm12_22.10.0_amd64.deb" \
        && curl -fL --retry 5 --retry-delay 5 --retry-all-errors -O \
            "https://github.com/intel/intel-graphics-compiler/releases/download/v2.34.4/intel-igc-core-2_${IGC_VERSION}_amd64.deb" \
        && curl -fL --retry 5 --retry-delay 5 --retry-all-errors -O \
            "https://github.com/intel/intel-graphics-compiler/releases/download/v2.34.4/intel-igc-opencl-2_${IGC_VERSION}_amd64.deb" \
        && dpkg -i ./*.deb && cd / && rm -rf /tmp/gpu_deps \
        && mkdir -p /tmp/npu_deps && cd /tmp/npu_deps \
        && curl -fL --retry 5 --retry-delay 5 --retry-all-errors -O \
            "https://github.com/intel/linux-npu-driver/releases/download/v${NPU_DRIVER_VERSION}/linux-npu-driver-${NPU_DRIVER_BUILD}.tar.gz" \
        && tar -xf "linux-npu-driver-${NPU_DRIVER_BUILD}.tar.gz" \
        && curl -fL --retry 5 --retry-delay 5 --retry-all-errors -O \
            "https://ppa.launchpadcontent.net/kobuk-team/intel-graphics/ubuntu/pool/main/l/level-zero-loader/libze1_${LEVEL_ZERO_VERSION}_amd64.deb" \
        && dpkg -i ./*.deb && ldconfig \
        && test -e /usr/lib/x86_64-linux-gnu/libze_loader.so.1 \
        && cd / && rm -rf /tmp/npu_deps \
        && apt-get purge -y curl && apt-get autoremove -y \
        && if [ "$CORPORATE_CA_INSTALLED" = "1" ]; then \
            rm -f /usr/local/share/ca-certificates/corporate-ca.crt \
            && update-ca-certificates --fresh; \
        fi; \
    fi \
    && rm -rf /var/lib/apt/lists/*

# Audio/runtime OS libraries + bare python3.12 interpreter (no venv/pip
# toolchain needed here -- the fully built venv is copied from the
# builder stage below). ffmpeg/libsndfile1 are required by librosa/
# soundfile for audio decoding; alsa-utils provides ALSA userspace
# utilities some audio codecs probe for at import time. ca-certificates is
# required for any outbound TLS call made from this stage at runtime
# (Hugging Face Hub model downloads during on-first-run `optimum-cli`
# export, MinIO/VSS HTTPS calls, etc.) -- Ubuntu's base image does not
# ship a CA trust store, so without this package every HTTPS request
# fails with "No CA certificates were loaded from the system".
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3.12 alsa-utils ffmpeg libsndfile1 ca-certificates \
    && rm -rf /var/lib/apt/lists/* /usr/share/doc/* /usr/share/man/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    AUDIO_ANALYZER_SERVER_PORT=8010

WORKDIR /app/audio_analyzer

COPY --from=builder /opt/venv /opt/venv
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
    && groupadd -g ${APP_GID} appuser 2>/dev/null || true \
    && useradd -m --no-log-init -u ${APP_UID} -g ${APP_GID} appuser 2>/dev/null || true \
    && chown -R ${APP_UID}:${APP_GID} /app/audio_analyzer

USER ${APP_UID}:${APP_GID}

EXPOSE 8010

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python3.12 -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('AUDIO_ANALYZER_SERVER_PORT','8010')+'/health', timeout=5).read()"

CMD ["sh", "-c", "exec python3.12 -m uvicorn main:app --host 0.0.0.0 --port \"${AUDIO_ANALYZER_SERVER_PORT:-8010}\""]
