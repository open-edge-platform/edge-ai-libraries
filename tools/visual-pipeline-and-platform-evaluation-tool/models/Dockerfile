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
FROM intel/dlstreamer:weekly-2026.0-20260127-ubuntu24

# Switch to root user to install dependencies
USER root

# Set environment variable to non-interactive mode (avoids some prompts)
ENV DEBIAN_FRONTEND=noninteractive

# Install necessary dependencies
RUN apt-get update && \
    apt-get install --yes --no-install-recommends dialog yq && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Switch to dlstreamer user
USER dlstreamer

# Set the working directory inside the container
WORKDIR /home/dlstreamer

# Copy the model manager script into the container and give execution permissions
COPY --chown=dlstreamer:dlstreamer models/model_manager.sh /home/dlstreamer/
RUN chmod +x ./model_manager.sh

# Set the entrypoint for the container to run the model manager script
CMD ["./model_manager.sh"]
