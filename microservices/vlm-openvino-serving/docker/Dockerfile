# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

FROM python:3.12-slim AS build

RUN pip install --upgrade --no-cache-dir pip setuptools

RUN apt-get update -y && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir poetry

WORKDIR /app

COPY pyproject.toml poetry.lock /app/

RUN poetry config virtualenvs.create false && poetry install --no-root --only=main

FROM python:3.12-slim

ARG INSTALL_DRIVER_VERSION="26.09.37435"
ARG USER_ID=1000
ARG USER_GROUP_ID=1000
ARG NPU_DRIVER_VERSION="1.33.0"
ARG NPU_DRIVER_BUILD="v1.33.0.20260529-26625960453-ubuntu2404"
ARG LEVEL_ZERO_VERSION="1.27.0-1~24.04~ppa2"
ARG LEVEL_ZERO_PPA_SNAPSHOT="20260324T100000Z"

RUN groupadd -g ${USER_GROUP_ID} appuser && useradd -m -s /bin/bash -u ${USER_ID} -g ${USER_GROUP_ID} appuser

COPY --from=build /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=build /usr/local/bin /usr/local/bin
COPY --from=build /app/poetry.lock /app/poetry.lock

COPY ./scripts/install_ubuntu_gpu_drivers.sh /tmp/install_gpu_drivers.sh
# curl is needed only at build time for driver downloads; install then purge.
RUN apt-get update -y && apt-get install -y --no-install-recommends --fix-missing curl && \
    chmod +x /tmp/install_gpu_drivers.sh && \
    /tmp/install_gpu_drivers.sh && \
    apt-get purge -y curl && apt-get autoremove -y && \
    apt-get clean && rm -rf /tmp/install_gpu_drivers.sh && rm -rf /var/lib/apt/lists/* && rm -rf /tmp/* && rm -rf /root/.cachetmp/*

# Install the NPU user-space stack: the Intel NPU driver/compiler/firmware (from the
# linux-npu-driver release) and the oneAPI Level Zero loader (libze1). The loader is
# mandatory: without libze_loader.so.1 the OpenVINO NPU plugin cannot enumerate the
# device and compilation on NPU can fail.
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
COPY . .
RUN chmod +x /app/scripts/compress_model.sh

RUN mkdir -p /home/appuser/.cache/huggingface /app/ov-model && \
    chown -R appuser:appuser /home/appuser/.cache /app/ov-model /opt

USER appuser

EXPOSE 8000

CMD ["/bin/bash", "-c", "/app/scripts/compress_model.sh ${VLM_MODEL_NAME} ${VLM_COMPRESSION_WEIGHT_FORMAT} ${VLM_DEVICE} ${HUGGINGFACE_TOKEN} && gunicorn -b 0.0.0.0:8000 -k uvicorn.workers.UvicornWorker src.app:app --timeout 10000 -w ${WORKERS:-1} --log-level ${VLM_OPENVINO_LOG_LEVEL:-info} --access-logfile ${VLM_ACCESS_LOG_FILE:--} --error-logfile -"]
