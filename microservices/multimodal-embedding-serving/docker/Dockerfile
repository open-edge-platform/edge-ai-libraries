# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

FROM python:3.12.10-slim AS build

ARG USER_ID=1000
ARG USER_GROUP_ID=1000

RUN apt-get update -y && apt-get install -y --no-install-recommends --fix-missing \
    curl

RUN pip install --upgrade --no-cache pip setuptools && \
    pip install --no-cache torch~=2.7.1 torchvision~=0.22.1 --index-url https://download.pytorch.org/whl/cpu;

RUN pip install poetry

RUN poetry config virtualenvs.create false

WORKDIR /app

COPY poetry.lock pyproject.toml /app/
RUN poetry install --no-root

RUN apt-get install -y --no-install-recommends curl ca-certificates libxml2 gnupg

RUN curl https://repositories.intel.com/gpu/intel-graphics.key | \
    gpg --dearmor --output /usr/share/keyrings/intel-graphics.gpg && \
    echo "deb [arch=amd64,i386 signed-by=/usr/share/keyrings/intel-graphics.gpg] https://repositories.intel.com/gpu/ubuntu jammy client" | \
    tee /etc/apt/sources.list.d/intel-gpu-jammy.list && \
    apt-get update && \
    apt-get install --no-install-recommends -y \
    libze1 intel-level-zero-gpu intel-opencl-icd && \
    apt-get clean && rm -rf /var/lib/apt/lists/*
RUN apt-get remove --no-install-recommends -y gnupg && \
    apt-get autoremove -y

# old script
ARG INSTALL_DRIVER_VERSION="24.39.31294"
COPY scripts/install_ubuntu_gpu_drivers.sh /tmp/install_gpu_drivers.sh
RUN chmod +x /tmp/install_gpu_drivers.sh
RUN /tmp/install_gpu_drivers.sh
RUN apt-get clean && rm -rf /tmp/install_gpu_drivers.sh && rm -rf /var/lib/apt/lists/* && rm -rf /tmp/*

RUN groupadd -g ${USER_GROUP_ID} appuser && useradd -m -s /bin/bash -u ${USER_ID} -g ${USER_GROUP_ID} appuser

COPY . .
RUN mkdir -p /tmp/dataprep/videos
RUN mkdir -p /home/appuser/.cache/huggingface /app/ov-models && \
    chown -R appuser:appuser /home/appuser/.cache /app/ov-models

USER appuser

EXPOSE 8000

CMD ["gunicorn", "-b", "0.0.0.0:8000", "-k", "uvicorn.workers.UvicornWorker", "app:app", "--timeout", "300", "--log-level", "info", "--access-logfile", "-", "--error-logfile", "-", "--log-config", "/app/logging.conf"]