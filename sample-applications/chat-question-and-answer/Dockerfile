# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

FROM python:3.11-slim

ENV HOME="/home/intelgai"

# Create a non-root user
RUN groupadd -g 1001 intelgai && \
    useradd -m -s /bin/bash -u 1001 -g 1001 intelgai && \
    chown -R intelgai:intelgai $HOME 

RUN apt-get update -y && apt-get install -y --no-install-recommends --fix-missing \
    libgl1-mesa-glx \
    libjemalloc-dev

RUN pip install --no-cache-dir --upgrade pip setuptools && \
    pip install poetry vllm nltk

RUN poetry config virtualenvs.create false

COPY . my-app

RUN rm -rf /my-app/deploy

WORKDIR /my-app

RUN poetry install --only main

RUN python -m nltk.downloader punkt_tab averaged_perceptron_tagger_eng

USER intelgai

EXPOSE 8080


CMD opentelemetry-instrument uvicorn app.server:app --host 0.0.0.0 --port 8080
