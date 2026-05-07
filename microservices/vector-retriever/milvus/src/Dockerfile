# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Use latest Python 3.12 slim image with security patches
FROM python:3.12-slim

ENV LANG=C.UTF-8

# Update system packages and install curl with latest security patches
# Clean up apt cache to reduce image size
RUN apt-get update -y && \
    apt-get upgrade -y && \
    apt-get install -y --no-install-recommends --fix-missing \
        curl \
        ca-certificates && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

RUN useradd -m -s /bin/bash user && \
mkdir -p /home/user && \
chown -R user /home/user/

COPY vector-retriever/milvus /home/user/retriever
RUN chown -R user /home/user/retriever

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /home/user/retriever/src/requirements.txt

USER user

EXPOSE 7770

WORKDIR /home/user/retriever/src

CMD ["uvicorn", "retriever_server:app", "--host", "0.0.0.0", "--port", "7770"]