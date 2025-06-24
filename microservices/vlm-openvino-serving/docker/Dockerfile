# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

FROM python:3.12.10-slim AS build

RUN pip install --upgrade --no-cache pip setuptools && \
    pip install --no-cache torch~=2.7.0 torchvision~=0.22.0 --index-url https://download.pytorch.org/whl/cpu;

RUN pip install poetry

WORKDIR /app

COPY pyproject.toml poetry.lock /app/

RUN poetry config virtualenvs.create false && poetry install --no-root

FROM python:3.12.10-slim

ARG INSTALL_DRIVER_VERSION="24.39.31294"
ARG USER_ID=1000
ARG USER_GROUP_ID=1000

RUN groupadd -g ${USER_GROUP_ID} appuser && useradd -m -s /bin/bash -u ${USER_ID} -g ${USER_GROUP_ID} appuser

RUN apt-get update -y && apt-get install -y --no-install-recommends --fix-missing \
    curl 

COPY --from=build /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=build /usr/local/bin /usr/local/bin
COPY --from=build /app/poetry.lock /app/poetry.lock

COPY ./scripts/install_ubuntu_gpu_drivers.sh /tmp/install_gpu_drivers.sh
RUN chmod +x /tmp/install_gpu_drivers.sh
RUN /tmp/install_gpu_drivers.sh

RUN apt-get clean && rm -rf /tmp/install_gpu_drivers.sh && rm -rf /var/lib/apt/lists/* && rm -rf /tmp/*

WORKDIR /app
COPY . .
RUN chmod +x /app/scripts/compress_model.sh

RUN mkdir -p /home/appuser/.cache/huggingface /app/ov-model && \
    chown -R appuser:appuser /home/appuser/.cache /app/ov-model

USER appuser

EXPOSE 8000

CMD ["/bin/bash", "-c", "/app/scripts/compress_model.sh ${VLM_MODEL_NAME} ${VLM_COMPRESSION_WEIGHT_FORMAT} && gunicorn -b 0.0.0.0:8000 -k uvicorn.workers.UvicornWorker src.app:app --timeout 10000 -w ${WORKERS:-1} --log-level info --access-logfile - --error-logfile - --log-config /app/logging.conf"]