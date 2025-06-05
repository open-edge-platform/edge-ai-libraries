# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

FROM python:3.12.10-slim AS build

ARG ARCH="cpu"

RUN apt-get update -y && apt-get install -y --no-install-recommends --fix-missing \
    libgl1-mesa-glx \
    curl

RUN pip install --upgrade --no-cache pip setuptools && \
    if [ ${ARCH} = "cpu" ]; then \
        pip install --no-cache torch torchvision --index-url https://download.pytorch.org/whl/cpu; \
    else \
        pip install --no-cache torch torchvision; \
    fi

RUN pip install poetry

WORKDIR /app

COPY pyproject.toml poetry.lock /app/

RUN poetry config virtualenvs.create false && poetry install --no-root

FROM python:3.12.10-slim

RUN apt-get update -y && apt-get install -y --no-install-recommends --fix-missing \
    libgl1-mesa-glx \
    curl

RUN apt-get clean && rm -rf /var/lib/apt/lists/* /tmp/*

COPY --from=build /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=build /usr/local/bin /usr/local/bin
COPY --from=build /app/poetry.lock /app/poetry.lock

WORKDIR /app
COPY . .
RUN chmod +x /app/scripts/compress_model.sh

EXPOSE 8000

CMD ["/bin/bash", "-c", "/app/scripts/compress_model.sh ${VLM_MODEL_NAME} ${VLM_COMPRESSION_WEIGHT_FORMAT} && gunicorn -b 0.0.0.0:8000 -k uvicorn.workers.UvicornWorker src.app:app --timeout 10000 -w ${WORKERS:-1} --log-level info --access-logfile - --error-logfile - --log-config /app/logging.conf"]