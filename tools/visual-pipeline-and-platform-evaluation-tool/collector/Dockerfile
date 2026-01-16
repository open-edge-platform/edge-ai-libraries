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

# Base image for building qmassa
FROM docker.io/library/rust:1.88 AS qmassa

# Set environment variable to non-interactive mode (avoids some prompts)
ENV DEBIAN_FRONTEND=noninteractive

# Install necessary dependencies
RUN apt-get update && \
    apt-get install --yes --no-install-recommends libudev-dev && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install qmassa
RUN cargo install --locked qmassa@1.2.1

# Final image for the collector
FROM docker.io/library/telegraf:1.37.1 AS collector

# Copy qmassa binary from the build stage
COPY --from=qmassa /usr/local/cargo/bin/qmassa /usr/local/bin/qmassa

# Set environment variable to non-interactive mode (avoids some prompts)
ENV DEBIAN_FRONTEND=noninteractive

# Install necessary dependencies
RUN apt-get update && \
    apt-get install --yes --no-install-recommends python3 supervisor && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy configuration and scripts
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf
COPY telegraf.conf /etc/telegraf
COPY qmassa_reader.py qmassa_reader.py
COPY read_cpu_freq.sh read_cpu_freq.sh
COPY entrypoint.sh /entrypoint.sh

# Make scripts executable
RUN chmod +x read_cpu_freq.sh /entrypoint.sh

# Set the entrypoint to the custom script
CMD ["/entrypoint.sh"]
