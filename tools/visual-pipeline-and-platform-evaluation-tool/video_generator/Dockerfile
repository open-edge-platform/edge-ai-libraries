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
FROM docker.io/intel/dlstreamer:2025.0.1.3-ubuntu24

# Set environment variable to non-interactive mode (avoids some prompts)
ENV DEBIAN_FRONTEND=noninteractive

USER root

# Install necessary dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gstreamer1.0-plugins-bad    \
    gstreamer1.0-plugins-ugly && \
    rm -rf /var/lib/apt/lists/*


ENV GST_PLUGIN_PATH=$GST_PLUGIN_PATH/usr/lib/x86_64-linux-gnu/gstreamer-1.0/

# Set the working directory inside the container
WORKDIR /usr/src/app/

# Copy the requirements file into the container
COPY requirements.txt /usr/src/app

# Install necessary Python dependencies
RUN pip3 install -r requirements.txt

# Copy the Python scripts and configuration files into the container
COPY background.gif config.json imagetovideo.py composite_generator.py /usr/src/app/

# Copy the images folder into the container
COPY images/ /usr/src/app/images

ARG UID=1000
USER ${UID}

# Set the entrypoint for the container to run the main Python script
CMD ["python3", "imagetovideo.py"]
