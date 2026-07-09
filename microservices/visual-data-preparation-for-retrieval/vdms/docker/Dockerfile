# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

ARG ARCH="cpu"
ARG INSTALL_DRIVER_VERSION="26.09.37435"
FROM python:3.12-slim AS python-base
ARG ARCH
# Setting env vars for python, pip and poetry
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=off \ 
    # off value above actually emplies, no cache will be used. Confusing.
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100 \
    POETRY_VERSION=2.3.1 \
    # Poetry installation location
    POETRY_HOME="/opt/poetry" \
    # Create the virtual environment dir .venv in the project's root
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    # Disable interactive prompts
    POETRY_NO_INTERACTION=1 \
    # Location where packages gets installed
    SETUP_PATH="/opt/projsetup" \
    # Location where virtual env is created
    VENV_PATH="/opt/projsetup/.venv"

# Add poetry and venv to path
ENV PATH="$PATH:$POETRY_HOME/bin:$VENV_PATH/bin"

# Create non-root user
RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid appuser --shell /bin/bash --create-home appuser

# upgrade pip to the latest version
RUN pip install --upgrade pip

# `builder-base` image used to install build dependecies and required packages 
FROM python-base AS builder-base
RUN apt-get update && apt-get install --no-install-recommends --fix-missing -y \
    curl \
    build-essential \
    git

# Install poetry. Installs in $POETRY_HOME with version $POETRY_VERSION
RUN curl -sSL https://install.python-poetry.org | python3 - 

WORKDIR $SETUP_PATH
COPY multimodal-embedding-serving /multimodal-embedding-serving
COPY visual-data-preparation-for-retrieval/vdms/poetry.lock visual-data-preparation-for-retrieval/vdms/pyproject.toml ./


# Install runtime deps. Uses $POETRY_VIRTUALENVS_IN_PROJECT to create venv.
# torch/torchvision/numpy are pinned to CPU wheels (OpenVINO handles CPU/Intel
# GPU/NPU acceleration, so a CUDA torch build is never needed).
RUN poetry install --no-root

# Install additional packages that have dependency conflicts with --no-deps
# These are required for the multimodal embedding service SDK
RUN poetry run pip install git+https://github.com/apple/ml-mobileclip.git salesforce-lavis==1.0.2 --no-deps

# Set ownership of poetry and setup directories to appuser
RUN chown -R appuser:appuser $POETRY_HOME $SETUP_PATH


# Runtime image
FROM python-base AS prod

ARG INSTALL_DRIVER_VERSION
# NPU user-space stack versions (declared once, interpolated into the download URLs below).
ARG NPU_DRIVER_VERSION="1.33.0"
ARG NPU_DRIVER_BUILD="v1.33.0.20260529-26625960453-ubuntu2404"
ARG LEVEL_ZERO_VERSION="1.27.0-1~24.04~ppa2"
ARG LEVEL_ZERO_PPA_SNAPSHOT="20260324T100000Z"

ENV FASTAPI_ENV=production \
    INSTALL_DRIVER_VERSION=${INSTALL_DRIVER_VERSION}

COPY --from=builder-base $SETUP_PATH $SETUP_PATH

COPY visual-data-preparation-for-retrieval/vdms/scripts/ /
# curl is needed only at build time (the driver script downloads .deb packages),
# so it is installed here and purged at the end to keep it out of the final image.
RUN apt-get update && apt-get install --no-install-recommends -y curl && \
chmod +x /entrypoint.sh /install_ubuntu_gpu_drivers.sh && \
/install_ubuntu_gpu_drivers.sh && \
apt-get purge -y curl && apt-get autoremove -y && \
apt-get clean && rm -rf /var/lib/apt/lists/*

# Install the NPU user-space stack: the Intel NPU driver/compiler/firmware (from the
# linux-npu-driver release) AND the oneAPI Level Zero loader (libze1). The loader is
# mandatory: without libze_loader.so.1 the OpenVINO NPU plugin cannot enumerate the
# device and falls back to a VCL compiler that is not shipped, so NPU compilation fails.
# Downloads use curl --retry because the PPA snapshot host intermittently returns 5xx,
# every step is chained with && so a failed download aborts the build instead of silently
# shipping a broken image, and the final assertion fails the build if the loader is missing.
# curl is installed here for the downloads and purged at the end so it stays out of the
# final image (reduces the runtime CVE/dependency surface).
RUN mkdir -p /tmp/npu_deps && cd /tmp/npu_deps && \
    apt-get update && apt-get install -y --no-install-recommends libtbb12 curl && \
    curl -L --retry 5 --retry-delay 5 --retry-all-errors -O https://github.com/intel/linux-npu-driver/releases/download/v${NPU_DRIVER_VERSION}/linux-npu-driver-${NPU_DRIVER_BUILD}.tar.gz && \
    tar -xf linux-npu-driver-${NPU_DRIVER_BUILD}.tar.gz && \
    curl -L --retry 5 --retry-delay 5 --retry-all-errors -O https://snapshot.ppa.launchpadcontent.net/kobuk-team/intel-graphics/ubuntu/${LEVEL_ZERO_PPA_SNAPSHOT}/pool/main/l/level-zero-loader/libze1_${LEVEL_ZERO_VERSION}_amd64.deb && \
    dpkg -i ./*.deb && rm -Rf /tmp/npu_deps && \
    ldconfig && \
    test -e /usr/lib/x86_64-linux-gnu/libze_loader.so.1 && \
    apt-get purge -y curl && apt-get autoremove -y && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

COPY visual-data-preparation-for-retrieval/vdms/ /app/

# Optionally download copyleft sources if requested
ARG COPYLEFT_SOURCES=false
RUN if [ "$COPYLEFT_SOURCES" = "true" ]; then \
        apt-get update && \
        # Get list of installed deb packages with copyleft licenses \
        sed -Ei 's/# deb-src /deb-src /' /etc/apt/sources.list && \
        apt-get update && \
        mkdir -p /copyleft_sources/deb && cd /copyleft_sources/deb && \
        echo -n $null > copyleft_package_list.txt && \
        for package in $(dpkg -l | awk '/^ii/ {print $2}' | cut -d: -f1); do \
            grep -l 'Copyleft\|GPL\|LGPL\|EPL\|MPL\|CDDL' /usr/share/doc/${package}/copyright; \
            exit_status=$?; \
            if [ $exit_status -eq 0 ]; then \
                echo $package >> copyleft_package_list.txt; \
                apt-get source -q --download-only $package; \
            fi; \
        done; \
        # Get source code for installed Python packages with copyleft licenses \
        mkdir -p /copyleft_sources/python && \
        cd /copyleft_sources/python && \
        apt-get update && apt-get install --no-install-recommends -y gcc build-essential libffi-dev python3-dev && \
        # Download python package sources with relevant licenses \
        pip3 freeze | cut -d= -f1 | while read pkg; do \
            meta=$(pip3 show $pkg 2>/dev/null); \
            lic=$(echo "$meta" | grep -i '^License:' | grep -E 'MPL|GPL|General Public License|EPL|Eclipse Public License|CDDL|LGPL'); \
            if [ ! -z "$lic" ]; then \
                echo "Downloading source for $pkg with license: $lic"; \
                pip3 download --no-binary :all: $pkg || true; \
            fi; \
        done; \
        apt-get remove --purge -y gcc build-essential libffi-dev python3-dev; \
    fi

WORKDIR /app

# Create temporary directory to store app artifacts. Ownership is changed to appuser later.
# Create model directory for persistent storage mount
RUN mkdir -p /tmp/dataprep /app/models/yolox /app/ov_models /home/appuser/.cache/huggingface


# Set ownership of all necessary directories to appuser
RUN chown -R appuser:appuser /app  /tmp/dataprep /entrypoint.sh /home/appuser/.cache/huggingface

# Switch to non-root user
USER appuser

EXPOSE 8000

ENTRYPOINT [ "/entrypoint.sh" ]
CMD ["gunicorn", "-b", "0.0.0.0:8000", "-k", "uvicorn.workers.UvicornWorker", "src.main:app", "--timeout", "1200", "--log-level", "debug"]
