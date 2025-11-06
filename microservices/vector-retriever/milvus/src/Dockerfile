# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

FROM python:3.12.10-slim

ENV LANG=C.UTF-8

RUN apt-get update -y && apt-get install -y --no-install-recommends --fix-missing curl

RUN useradd -m -s /bin/bash user && \
mkdir -p /home/user && \
chown -R user /home/user/

COPY vector-retriever/milvus /home/user/retriever
RUN chown -R user /home/user/retriever

RUN pip install --no-cache-dir --upgrade pip setuptools && \
    pip install --no-cache-dir -r /home/user/retriever/src/requirements.txt

USER user

EXPOSE 7770

WORKDIR /home/user/retriever/src

CMD ["uvicorn", "retriever_server:app", "--host", "0.0.0.0", "--port", "7770"]