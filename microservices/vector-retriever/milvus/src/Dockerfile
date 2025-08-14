# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

FROM python:3.12.10-slim

ENV LANG=C.UTF-8

ARG ARCH="gpu"

RUN apt-get update -y && apt-get install -y --no-install-recommends --fix-missing libgl1-mesa-glx libglib2.0-0 build-essential gnupg ca-certificates wget curl git

RUN wget -qO - https://repositories.intel.com/gpu/intel-graphics.key | \
    gpg --yes --dearmor --output /usr/share/keyrings/intel-graphics.gpg && \
    echo "deb [arch=amd64,i386 signed-by=/usr/share/keyrings/intel-graphics.gpg] https://repositories.intel.com/gpu/ubuntu jammy unified" | \
    tee /etc/apt/sources.list.d/intel-gpu-jammy.list && \
    apt-get update && \
    apt-get install --no-install-recommends -y \
    libze-intel-gpu1 libze1 intel-opencl-icd clinfo && \
    apt-get clean && rm -rf /var/lib/apt/lists/*
RUN apt-get remove --no-install-recommends -y gnupg && \
    apt-get autoremove -y


RUN useradd -m -s /bin/bash user && \
mkdir -p /home/user && \
chown -R user /home/user/

COPY vector-retriever/milvus /home/user/retriever
RUN chown -R user /home/user/retriever

RUN pip install --no-cache-dir --upgrade pip setuptools && \
    pip install --no-cache-dir torch torchvision --extra-index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu -r /home/user/retriever/src/requirements.txt

ENV PYTHONPATH=$PYTHONPATH:/home/user

RUN mkdir -p /home/user/models && chown -R user /home/user/models

USER user

EXPOSE 7770

WORKDIR /home/user/retriever/src

CMD ["uvicorn", "retriever_server:app", "--host", "0.0.0.0", "--port", "7770"]