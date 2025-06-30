# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

FROM python:3.11-slim AS build

RUN apt-get update && apt-get install -y \
    automake \
    gcc \
    g++ \
    subversion \
    python3-dev \
    libjpeg-dev \
    zlib1g-dev \
    && pip install Pillow==8.2.0 numpy \
    && pip install --pre torch torchvision --index-url https://download.pytorch.org/whl/nightly/cpu \
    && pip install poetry==2.1.3

WORKDIR /app
# Copy the application code
RUN poetry config virtualenvs.create false 

COPY . .

# Installing root dependencies
RUN poetry install --only main

# Expose the port the app runs on
EXPOSE 8000

# Command to run the application
CMD uvicorn app.server:app --host 0.0.0.0 --port 8000
