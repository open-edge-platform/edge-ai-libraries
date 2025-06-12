# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

FROM python:3.11-slim

ENV HOME="/home/intelgai"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Create a non-root user
RUN groupadd -g 1001 intelgai && \
    useradd -m -s /bin/bash -u 1001 -g 1001 intelgai && \
    chown -R intelgai:intelgai $HOME && \
    apt-get update -y && \
    apt-get install -y --no-install-recommends --fix-missing \
    libgl1-mesa-glx \
    libjemalloc-dev && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* && \
    pip install --no-cache-dir --upgrade pip setuptools && \
    pip install --no-cache-dir poetry nltk && \
    poetry config virtualenvs.create false && \
    mkdir -p /home/intelgai/.cache/huggingface && \
    chown intelgai:intelgai /home/intelgai/.cache/huggingface

#COPY . my-app
#COPY pyproject.toml poetry.lock README.md app/ my-app/
WORKDIR /my-app
COPY pyproject.toml poetry.lock README.md ./
COPY app ./app

# Install dependencies and NLTK data as non-root user
RUN poetry install --only main && \
    rm -rf ~/.cache/pypoetry/* ~/.cache/pip/*

RUN python -m nltk.downloader punkt_tab averaged_perceptron_tagger_eng

USER intelgai

EXPOSE 8080


CMD uvicorn app.server:app --host 0.0.0.0 --port 8080
