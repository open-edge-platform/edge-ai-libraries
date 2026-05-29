# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# ---------- Stage 1: builder ----------
# Compile/install all Python dependencies into a virtualenv that the final
# stage will copy. Build-only apt packages (gcc, headers, git) never make it
# into the runtime image.
FROM python:3.12-slim AS builder

ENV LANG=C.UTF-8 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    VENV_PATH=/opt/venv

# Minimal build deps:
#   build-essential : required to compile lmdb==1.3.0 from source (hard-pinned
#                     by cn-clip, no cp312 wheel exists). The lmdb sdist
#                     applies patches that need a full toolchain (make + gcc).
#   git             : required to pip-install mobileclip from GitHub.
#   ca-certificates : required for HTTPS pip/git operations.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential git ca-certificates && \
    rm -rf /var/lib/apt/lists/*

RUN python -m venv "$VENV_PATH"
ENV PATH="$VENV_PATH/bin:$PATH"

# Stage 1a: copy only dependency manifests (requirements.txt + bundled wheels)
# so the pip install layer is cached across source changes.
COPY visual-data-preparation-for-retrieval/milvus/src/requirements.txt /home/user/dataprep/src/requirements.txt
COPY visual-data-preparation-for-retrieval/milvus/src/wheels /home/user/dataprep/src/wheels

RUN pip install --upgrade pip && \
    pip install -r /home/user/dataprep/src/requirements.txt && \
    pip install --no-deps \
        "git+https://github.com/apple/ml-mobileclip.git@c16bfe5a4feb424762d6bdf5245539120a4ce9ef#egg=mobileclip" \
        "salesforce-lavis==1.0.2"

# Strip caches that pip leaves behind to keep the venv lean. We intentionally
# do NOT delete 'tests/' directories — some packages (numpy._core.tests)
# expose modules that other libs import at runtime.
RUN find "$VENV_PATH" -type d -name '__pycache__' -prune -exec rm -rf {} + && \
    find "$VENV_PATH" -type f -name '*.pyc' -delete


# ---------- Stage 2: runtime ----------
FROM python:3.12-slim

# Pinned Intel GPU compute-runtime release (matches MME/VDMS reference images
# so the same kernels run on this host). Override at build time if needed.
ARG INSTALL_DRIVER_VERSION="25.31.34666"

ENV LANG=C.UTF-8 \
    VENV_PATH=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    INSTALL_DRIVER_VERSION=${INSTALL_DRIVER_VERSION}

# Runtime apt deps:
#   curl            : needed by install_ubuntu_gpu_drivers.sh and compose healthcheck.
#   ca-certificates : HTTPS for curl + HF model downloads at runtime.
# torch bundles its own OpenMP runtime, so libgomp1 is not required.
# No opencv-python in requirements, so libgl1/libglib2.0-0 are not required.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Install the Intel GPU userspace stack (Level Zero + OpenCL ICD + GMM) using
# the canonical pinned-version script from MME. This is needed because in
# SDK-embedding mode dataprep runs the OpenVINO inference in-process on GPU.
COPY visual-data-preparation-for-retrieval/milvus/scripts/install_ubuntu_gpu_drivers.sh /install_ubuntu_gpu_drivers.sh
RUN chmod +x /install_ubuntu_gpu_drivers.sh && \
    /install_ubuntu_gpu_drivers.sh && \
    rm /install_ubuntu_gpu_drivers.sh && \
    rm -rf /var/lib/apt/lists/*

RUN useradd -m -s /bin/bash user && \
    mkdir -p /home/user && \
    chown -R user /home/user/

COPY --from=builder $VENV_PATH $VENV_PATH

# Stage 2: copy the rest of the source tree.
COPY visual-data-preparation-for-retrieval/milvus /home/user/dataprep
RUN chown -R user /home/user/dataprep

RUN mkdir -p /home/user/data && chown -R user /home/user/data

USER user

EXPOSE 9990

WORKDIR /home/user/dataprep/src

CMD ["uvicorn", "dataprep_visual:app", "--host", "0.0.0.0", "--port", "9990"]
