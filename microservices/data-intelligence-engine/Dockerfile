# syntax=docker/dockerfile:1
# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
# Engine service image. Build context is the data-intelligence-engine/ directory.
#   docker build -t data-intelligence-engine -f Dockerfile .
FROM python:3.11-slim

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# curl: container healthcheck, and the manual API scripts in scripts/.
# jq: those scripts express their checks as jq filters (installed again below as
# part of the driver step; kept here so this layer stands on its own).
# build-essential: fallback for any sdist without a wheel (e.g. PyStemmer on some
# platforms).
# tesseract-ocr(-chi-sim): OCR for scanned PDFs. ffmpeg: decodes audio for
# speech recognition (core/multimodal/asr.py).
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl jq build-essential tesseract-ocr tesseract-ocr-chi-sim ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Intel GPU user-space runtime (OpenCL ICD + Level Zero) so OpenVINO can enumerate
# and run embedding/rerank on the Intel GPU. Without these, OpenVINO only sees CPU
# even when /dev/dri is passed through. Mirrors EdgeCraftRAG's Dockerfile.server.
RUN apt-get update \
    && (apt-get remove -y libze-intel-gpu1 libigc1 libigdfcl1 libze-dev || true) \
    && apt-get install -y gnupg2 wget curl jq \
    && curl -sL 'https://keyserver.ubuntu.com/pks/lookup?fingerprint=on&op=get&search=0x0C0E6AF955CE463C03FC51574D098D70AFBE5E1F' \
        | tee /etc/apt/trusted.gpg.d/driver.asc \
    && echo -e "Types: deb\nURIs: https://ppa.launchpadcontent.net/kobuk-team/intel-graphics/ubuntu/\nSuites: noble\nComponents: main\nSigned-By: /etc/apt/trusted.gpg.d/driver.asc" \
        > /etc/apt/sources.list.d/driver.sources \
    && apt-get update \
    && apt-get install -y \
        libze-intel-gpu1 libze1 intel-metrics-discovery intel-opencl-icd clinfo intel-gsc \
        libze-dev intel-ocloc libze-intel-gpu-raytracing libglib2.0-0 libgl1 \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -s /bin/bash user
WORKDIR /app

# Install runtime and build dependencies from metadata alone. Source edits must
# not invalidate this layer. Keep pip downloads in BuildKit's persistent cache,
# outside the image, so changed dependencies can also reuse existing wheels.
# The PyTorch CPU index supplies the +cpu wheels pinned in pyproject.toml.
COPY pyproject.toml /app/engine/pyproject.toml
RUN --mount=type=cache,id=engine-pip,target=/root/.cache/pip,sharing=locked <<'INSTALL'
set -eu
python3 - <<'PY'
from pathlib import Path
import tomllib

project = tomllib.loads(Path("/app/engine/pyproject.toml").read_text(encoding="utf-8"))
Path("/tmp/engine-requirements.txt").write_text(
    "\n".join(project["build-system"]["requires"] + project["project"]["dependencies"]) + "\n",
    encoding="utf-8",
)
PY
pip3 install --extra-index-url https://download.pytorch.org/whl/cpu \
    wheel -r /tmp/engine-requirements.txt
rm /tmp/engine-requirements.txt
INSTALL

# Copy and install only the project; dependencies and the build backend are
# already installed, so packaging updated source needs no network access.
# The workspace is a mount point, not image content:
# create it owned by `user` so a fresh bind mount is writable.
#
# `uploads` and `content` are created here rather than left to the first request.
# A bind mount arrives owned by the host user, and the engine runs as `user`: if
# the first thing to create `content/` is the object adapter at ingest time, it
# fails on a read-only or root-owned mount *after* the upload has been accepted,
# which reads as a broken ingest rather than a misconfigured volume. Registering
# a filesystem object database now checks the root is writable up front, but the
# directory still has to belong to the user that will write to it.
COPY . /app/engine/
RUN --mount=type=cache,id=engine-pip,target=/root/.cache/pip,sharing=locked \
    pip3 install --no-deps --no-build-isolation --no-index /app/engine \
    && rm -rf /app/engine/workspace \
    && mkdir -p /workspace/uploads /workspace/configs /workspace/models /workspace/content \
    && chown -R user /app /workspace

USER user

# ENGINE_WORKSPACE holds all runtime state: the Milvus volumes, the models, the
# uploaded files, the asset content, the persisted asset libraries, and the
# database connections. Mount it from the host — see docker-compose.yml.
#
# There is deliberately no database configuration here. MILVUS_URI and the
# object-store settings used to live in this block, and the engine registered
# connections from them at import time; they are registered over HTTP now
# (POST /v1/databases) and persisted in the workspace. A container
# started against an empty workspace is connected to nothing until something
# registers a database — see the compose file, which does it for you.
ENV ENGINE_HOST=0.0.0.0 \
    ENGINE_PORT=16022 \
    ENGINE_WORKSPACE=/workspace \
    PYTHONUNBUFFERED=1

EXPOSE 16022

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD curl -fsS "http://localhost:${ENGINE_PORT:-16022}/health" || exit 1

ENTRYPOINT ["data-intelligence-engine"]