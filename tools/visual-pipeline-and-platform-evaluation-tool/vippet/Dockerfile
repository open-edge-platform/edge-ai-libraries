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

# Use DLStreamer as the base image
FROM intel/dlstreamer:weekly-2026.0-20260127-ubuntu24 AS prod

# Switch to root user to install dependencies
USER root

# Set environment variable to non-interactive mode (avoids some prompts)
ENV DEBIAN_FRONTEND=noninteractive

# Install necessary dependencies
RUN apt-get update && \
    apt-get install --yes --no-install-recommends python3.12-dev gstreamer1.0-plugins-ugly yq v4l-utils && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

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

# Copy the requirements file into the container
COPY --chown=dlstreamer:dlstreamer vippet/requirements.txt /home/dlstreamer/vippet/requirements.txt

# Install necessary Python dependencies
RUN \
    pip3 install --upgrade pip && \
    pip3 install --disable-pip-version-check --no-cache-dir -r requirements.txt

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
RUN pip3 install --disable-pip-version-check --no-cache-dir -r requirements-dev.txt
