# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Use latest Python 3.12 slim image with security patches
FROM python:3.12-slim

ENV LANG=C.UTF-8

# Update system packages and install dependencies with latest security patches
RUN apt-get update -y && \
    apt-get upgrade -y && \
    apt-get install -y --no-install-recommends --fix-missing \
        gnupg \
        curl \
        unzip \
        ca-certificates

RUN curl https://repositories.intel.com/gpu/intel-graphics.key | \
    gpg --dearmor --output /usr/share/keyrings/intel-graphics.gpg && \
    echo "deb [arch=amd64,i386 signed-by=/usr/share/keyrings/intel-graphics.gpg] https://repositories.intel.com/gpu/ubuntu jammy client" | \
    tee /etc/apt/sources.list.d/intel-gpu-jammy.list && \
    apt-get update && \
    apt-get install --no-install-recommends -y \
    libze1 intel-level-zero-gpu intel-opencl-icd && \
    apt-get remove --no-install-recommends -y gnupg && \
    apt-get autoremove -y && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

RUN useradd -m -s /bin/bash user && \
mkdir -p /home/user && \
chown -R user /home/user/

COPY visual-data-preparation-for-retrieval/milvus /home/user/dataprep
RUN chown -R user /home/user/dataprep

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /home/user/dataprep/src/requirements.txt

RUN mkdir -p /home/user/data && chown -R user /home/user/data

USER user

EXPOSE 9990

WORKDIR /home/user/dataprep/src

CMD ["uvicorn", "dataprep_visual:app", "--host", "0.0.0.0", "--port", "9990"]