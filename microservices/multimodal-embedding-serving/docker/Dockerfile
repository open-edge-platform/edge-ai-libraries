# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Builder stage
FROM python:3.12-slim AS builder

ARG USER_ID=1000
ARG USER_GROUP_ID=1000
ARG POETRY_VERSION="2.4.0"
ARG MOBILECLIP_COMMIT="c16bfe5a4feb424762d6bdf5245539120a4ce9ef"
ARG SALESFORCE_LAVIS_VERSION="1.0.2"

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    patch \
    build-essential \
    gcc \
    git && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY poetry.lock pyproject.toml /app/
RUN pip install --no-cache-dir poetry==${POETRY_VERSION} && \
    poetry config virtualenvs.create false && \
    poetry install --no-root && \
    poetry run pip install --no-cache-dir \
        "git+https://github.com/apple/ml-mobileclip.git@${MOBILECLIP_COMMIT}#egg=mobileclip" \
        "salesforce-lavis==${SALESFORCE_LAVIS_VERSION}" \
        --no-deps

# Final stage
FROM python:3.12-slim

ARG USER_ID=1000
ARG USER_GROUP_ID=1000
# Intel GPU and NPU user-space stack versions (declared once, interpolated into the
# download URLs below). To upgrade, check these release pages for the latest versions:
#   GPU driver (Level Zero GPU + OpenCL ICD, ocloc, gmmlib): https://github.com/intel/compute-runtime/releases
#   GPU graphics compiler (IGC):                             https://github.com/intel/intel-graphics-compiler/releases
#   NPU driver/compiler/firmware:                            https://github.com/intel/linux-npu-driver/releases
#   Level Zero loader (libze1):                              https://github.com/oneapi-src/level-zero/releases
# Bump the GPU versions together: each compute-runtime release names the IGC and gmmlib
# versions it was validated with, and its .deb file names give the IGC build number.
# Keep LEVEL_ZERO_VERSION at the loader version the compute-runtime and linux-npu-driver
# releases list as validated (the libze1 .deb comes from the kobuk-team/intel-graphics
# PPA snapshot, so LEVEL_ZERO_PPA_SNAPSHOT must be a snapshot that still carries it).
ARG GPU_COMPUTE_RUNTIME_VERSION="26.35.39758.10"
ARG GPU_IGC_VERSION="2.41.5"
ARG GPU_IGC_BUILD="22716"
ARG GPU_GMMLIB_VERSION="22.10.0"
ARG NPU_DRIVER_VERSION="1.38.0"
ARG NPU_DRIVER_BUILD="v1.38.0.20260910-34487311128-ubuntu2404"
ARG LEVEL_ZERO_VERSION="1.32.0-1~24.04~ppa1"
ARG LEVEL_ZERO_PPA_SNAPSHOT="20260830T100000Z"
ARG COPYLEFT_SOURCES=false

RUN apt-get update && apt-get install -y --no-install-recommends \
    patch && \
    rm -rf /var/lib/apt/lists/* && \
    groupadd -g ${USER_GROUP_ID} appuser && useradd -m --no-log-init -s /bin/bash -u ${USER_ID} -g ${USER_GROUP_ID} appuser

WORKDIR /app


# Copy installed site-packages and bin from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin/gunicorn /usr/local/bin/gunicorn
COPY --from=builder /app /app

# Refresh security patches after bringing in build artifacts
RUN apt-get update && apt-get upgrade -y --no-install-recommends && rm -rf /var/lib/apt/lists/*

# Copy rest of the source code

# Install the Intel GPU user-space stack: the compute-runtime Level Zero GPU driver and
# OpenCL ICD, the graphics compiler (IGC) and gmmlib, from their GitHub releases. This
# follows the NPU step below: curl -f turns HTTP errors into failures and --retry rides
# out transient download errors, every step is chained with && so any failure aborts the
# build instead of silently shipping an image without GPU support, and the final
# assertions fail the build if the Level Zero GPU driver or the OpenCL ICD is missing.
# curl is installed here for the downloads and purged at the end so it stays out of the
# final image (reduces the runtime CVE/dependency surface).
RUN mkdir -p /tmp/gpu_deps && cd /tmp/gpu_deps && \
    apt-get update && apt-get install -y --no-install-recommends libnuma1 ocl-icd-libopencl1 curl && \
    curl -fL --retry 5 --retry-delay 5 --retry-all-errors -O https://github.com/intel/intel-graphics-compiler/releases/download/v${GPU_IGC_VERSION}/intel-igc-core-2_${GPU_IGC_VERSION}+${GPU_IGC_BUILD}_amd64.deb && \
    curl -fL --retry 5 --retry-delay 5 --retry-all-errors -O https://github.com/intel/intel-graphics-compiler/releases/download/v${GPU_IGC_VERSION}/intel-igc-opencl-2_${GPU_IGC_VERSION}+${GPU_IGC_BUILD}_amd64.deb && \
    curl -fL --retry 5 --retry-delay 5 --retry-all-errors -O https://github.com/intel/compute-runtime/releases/download/${GPU_COMPUTE_RUNTIME_VERSION}/intel-ocloc_${GPU_COMPUTE_RUNTIME_VERSION}-0_amd64.deb && \
    curl -fL --retry 5 --retry-delay 5 --retry-all-errors -O https://github.com/intel/compute-runtime/releases/download/${GPU_COMPUTE_RUNTIME_VERSION}/intel-opencl-icd_${GPU_COMPUTE_RUNTIME_VERSION}-0_amd64.deb && \
    curl -fL --retry 5 --retry-delay 5 --retry-all-errors -O https://github.com/intel/compute-runtime/releases/download/${GPU_COMPUTE_RUNTIME_VERSION}/libigdgmm12_${GPU_GMMLIB_VERSION}_amd64.deb && \
    curl -fL --retry 5 --retry-delay 5 --retry-all-errors -O https://github.com/intel/compute-runtime/releases/download/${GPU_COMPUTE_RUNTIME_VERSION}/libze-intel-gpu1_${GPU_COMPUTE_RUNTIME_VERSION}-0_amd64.deb && \
    dpkg -i ./*.deb && cd / && rm -Rf /tmp/gpu_deps && \
    ldconfig && \
    test -e /usr/lib/x86_64-linux-gnu/libze_intel_gpu.so.1 && \
    test -e /etc/OpenCL/vendors/intel.icd && \
    apt-get purge -y curl && apt-get autoremove -y && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install the NPU user-space stack: the Intel NPU driver/compiler/firmware (from the
# linux-npu-driver release) AND the oneAPI Level Zero loader (libze1). The loader is
# mandatory: without libze_loader.so.1 the OpenVINO NPU plugin cannot enumerate the
# device and falls back to a VCL compiler that is not shipped, so NPU compilation fails.
# Downloads use curl -f (HTTP errors fail) and --retry (the PPA snapshot host intermittently returns 5xx),
# every step is chained with && so a failed download aborts the build instead of silently
# shipping a broken image, and the final assertion fails the build if the loader is missing.
# curl is installed here for the downloads and purged at the end so it stays out of the
# final image (reduces the runtime CVE/dependency surface).
RUN mkdir -p /tmp/npu_deps && cd /tmp/npu_deps && \
    apt-get update && apt-get install -y --no-install-recommends libtbb12 curl && \
    curl -fL --retry 5 --retry-delay 5 --retry-all-errors -O https://github.com/intel/linux-npu-driver/releases/download/v${NPU_DRIVER_VERSION}/linux-npu-driver-${NPU_DRIVER_BUILD}.tar.gz && \
    tar -xf linux-npu-driver-${NPU_DRIVER_BUILD}.tar.gz && \
    curl -fL --retry 5 --retry-delay 5 --retry-all-errors -O https://snapshot.ppa.launchpadcontent.net/kobuk-team/intel-graphics/ubuntu/${LEVEL_ZERO_PPA_SNAPSHOT}/pool/main/l/level-zero-loader/libze1_${LEVEL_ZERO_VERSION}_amd64.deb && \
    dpkg -i ./*.deb && rm -Rf /tmp/npu_deps && \
    ldconfig && \
    test -e /usr/lib/x86_64-linux-gnu/libze_loader.so.1 && \
    apt-get purge -y curl && apt-get autoremove -y && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Optionally download copyleft sources if requested
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

COPY . .

RUN mkdir -p /tmp/dataprep/video /home/appuser/.cache/huggingface /app/ov_models && \
    chown -R appuser:appuser /home/appuser/.cache /app/ov_models /tmp/dataprep

USER appuser
EXPOSE 8000

CMD ["gunicorn", "-b", "0.0.0.0:8000", "-k", "uvicorn.workers.UvicornWorker", "src.app:app", "--timeout", "300", "--log-level", "debug"]