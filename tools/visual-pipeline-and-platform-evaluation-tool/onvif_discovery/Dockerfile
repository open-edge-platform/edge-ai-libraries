# Copyright (C) 2026 Intel Corporation

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

FROM python:3.14.2-slim

WORKDIR /app

# Copy the ONVIF discovery script
COPY onvif_discovery_agent.py /app/onvif_discovery_agent.py

# Set Python to run in unbuffered mode
ENV PYTHONUNBUFFERED=1

# Configurable output file and discovery interval
ENV OUTPUT_FILE=/out/onvif_cameras.json \
    DISCOVERY_INTERVAL=20 

# Run as non-root user (will be overridden by docker-compose user directive)
USER 1000:1000

CMD python /app/onvif_discovery_agent.py --out ${OUTPUT_FILE} --interval ${DISCOVERY_INTERVAL}
