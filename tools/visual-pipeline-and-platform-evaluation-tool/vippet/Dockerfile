# Copyright (C) 2025 Intel Corporation

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

# http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions
# and limitations under the License.

# SPDX-License-Identifier: Apache-2.0

# syntax=docker/dockerfile:1.7

# Use DLStreamer as the base image
FROM intel/dlstreamer:2026.1.0-ubuntu24 AS prod

# Switch to root user to install dependencies
USER root

# Set environment variable to non-interactive mode (avoids some prompts)
ENV DEBIAN_FRONTEND=noninteractive

# Install necessary dependencies
# BuildKit cache mounts keep apt downloads/metadata between builds. The
# cache lives outside the image layer, so runtime image size is unchanged.
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    rm -f /etc/apt/apt.conf.d/docker-clean && \
    apt-get update && \
    apt-get install --yes --no-install-recommends yq v4l-utils

# Switch to dlstreamer user
USER dlstreamer

# Set GStreamer plugin path (original GST_PLUGIN_PATH ends with a colon, so there is no need to add one here)
ENV GST_PLUGIN_PATH=$GST_PLUGIN_PATH/usr/lib/x86_64-linux-gnu/gstreamer-1.0/

# Add DLSOptimizer scripts to PYTHONPATH
ENV PYTHONPATH=$PYTHONPATH:/opt/intel/dlstreamer/scripts/optimizer/

# Set the working directory inside the container
WORKDIR /home/dlstreamer/vippet

# Create and activate a virtual environment for Python dependencies
ENV VIRTUAL_ENV=/home/dlstreamer/.venv
RUN python3 -m venv --system-site-packages $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Secondary virtualenv dedicated to ``openvino-dev[onnx]==2024.6.0``
# (omz_downloader / omz_converter). It pulls its own matching
# ``openvino==2024.6.0`` so it never collides with the OpenVINO 2026.x
# runtime installed in $VIRTUAL_ENV. Built without --system-site-packages
# to fully isolate the two stacks.
ENV OMZ_VIRTUAL_ENV=/home/dlstreamer/.omz-venv

# Copy the requirements files into the container
COPY --chown=dlstreamer:dlstreamer vippet/requirements.txt /home/dlstreamer/vippet/requirements.txt
COPY --chown=dlstreamer:dlstreamer vippet/requirements-omz.txt /home/dlstreamer/vippet/requirements-omz.txt

# Install the production runtime dependencies into the main venv and the
# OMZ tooling into its own isolated venv.
#
# A BuildKit cache mount keeps pip's HTTP/wheel cache between builds. The
# cache lives outside the image layer, so runtime image size is unchanged.
# ``mode=0777`` lets the non-root ``dlstreamer`` user write to it without
# needing to know its uid/gid at build time.
RUN --mount=type=cache,target=/tmp/pip-cache,mode=0777,sharing=locked \
    PIP_CACHE_DIR=/tmp/pip-cache \
    pip3 install --disable-pip-version-check -r requirements.txt && \
    python3 -m venv $OMZ_VIRTUAL_ENV && \
    PIP_CACHE_DIR=/tmp/pip-cache \
    $OMZ_VIRTUAL_ENV/bin/pip install --disable-pip-version-check \
        -r requirements-omz.txt && \
    # Security override: bump ``onnx`` past the cap that ``openvino-dev``
    # 2024.6.0 (archived upstream) inherited. Fixes CVE-2026-27489 (HIGH),
    # CVE-2026-28500 and CVE-2026-34446. ``--upgrade`` + explicit version
    # is required because the resolver would otherwise honor the cap, and
    # we deliberately keep transitive deps intact (no --no-deps) so onnx's
    # own runtime requirements (protobuf, numpy) are satisfied.
    PIP_CACHE_DIR=/tmp/pip-cache \
    $OMZ_VIRTUAL_ENV/bin/pip install --disable-pip-version-check \
        --upgrade "onnx>=1.21.0"

# Copy the Python scripts and configuration files into the container
COPY --chown=dlstreamer:dlstreamer \
    vippet/*.py \
    vippet/entrypoint.sh \
    /home/dlstreamer/vippet/

COPY --chown=dlstreamer:dlstreamer vippet/pipelines/ /home/dlstreamer/vippet/pipelines
COPY --chown=dlstreamer:dlstreamer vippet/api/ /home/dlstreamer/vippet/api
COPY --chown=dlstreamer:dlstreamer vippet/managers/ /home/dlstreamer/vippet/managers

# Make scripts executable
RUN chmod +x ./entrypoint.sh

# Set the entrypoint for the container to run the main Python script
CMD ["./entrypoint.sh"]

# Image for testing with dev dependencies
FROM prod AS test

# Copy the dev requirements file into the container
COPY --chown=dlstreamer:dlstreamer vippet/requirements-dev.txt /home/dlstreamer/vippet/requirements-dev.txt

# Install only dev requirements on top of prod image
RUN --mount=type=cache,target=/tmp/pip-cache,mode=0777,sharing=locked \
    PIP_CACHE_DIR=/tmp/pip-cache \
    pip3 install --disable-pip-version-check -r requirements-dev.txt
