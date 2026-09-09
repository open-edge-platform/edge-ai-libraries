# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

ARG BASE_IMAGE=intel/dlstreamer:2026.1.0-ubuntu24
FROM ${BASE_IMAGE}

USER root

ENV DEBIAN_FRONTEND=noninteractive
ENV DLSTREAMER_DIR=/opt/intel/dlstreamer

ARG WORKDIR=/home/pipeline-server
WORKDIR ${WORKDIR}

# Install runtime OS dependencies
RUN apt-get update --allow-releaseinfo-change && \
    apt-get install -y --no-install-recommends \
        python3-venv \
        python3-dev \
        libglib2.0-0 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Create and activate a Python virtual environment
RUN python3 -m venv --system-site-packages /python3venv && \
    /python3venv/bin/pip3 install --no-cache-dir --upgrade pip

ENV VIRTUAL_ENV=/python3venv
ENV PATH=$VIRTUAL_ENV/bin:$PATH
ENV PYTHONPATH=${DLSTREAMER_DIR}/gstreamer/lib/python3/dist-packages:${DLSTREAMER_DIR}/python

# Create a non-root user
ARG USER=pipeline-server
ARG UID=1999
RUN useradd -ms /bin/bash -G video,audio,users ${USER} -o -u ${UID} && \
    chown -R ${USER}:${USER} ${WORKDIR}

# Copy application source and startup script
COPY --chown=${USER}:${USER} ./src/ ${WORKDIR}/src/
COPY --chown=${USER}:${USER} ./docker/run.sh ${WORKDIR}/run.sh
RUN chmod +x ${WORKDIR}/run.sh

USER root

# Install Python dependencies
RUN pip3 install --no-cache-dir -r ${WORKDIR}/src/requirements.txt

USER ${USER}

# Create models and resources directories
RUN mkdir -p \
    ${WORKDIR}/models \
    ${WORKDIR}/resources/videos \
    ${WORKDIR}/resources/models \
    ${WORKDIR}/resources/images

ENV REST_SERVER_PORT=8080
ENV APP_LOG_LEVEL=INFO
ENV WEB_SERVER_LOG_LEVEL=WARNING
ENV GST_DEBUG=1

EXPOSE ${REST_SERVER_PORT}

ENTRYPOINT ["./run.sh"]