# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

FROM python:3.11-slim AS build

RUN apt-get update && apt-get install -y python3-dev \
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
