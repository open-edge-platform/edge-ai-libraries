#
# Apache v2 license
# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

FROM python:3.13-slim

# Set working directory
WORKDIR /app

# Copy requirements file
COPY requirements.txt .

RUN pip install --upgrade pip

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY ingestion-data.csv .
COPY ingestion.py .

# Set environment variables
ENV PYTHONUNBUFFERED=1

ARG COPYLEFT_SOURCES=false

# Download sources for Debian and Python packages with specific licenses if requested
RUN  if [ "$COPYLEFT_SOURCES" = "true" ]; then \
      mkdir -p /python-licenses && \
      cd /python-licenses && \
      # Download python package sources with relevant licenses
      pip3 freeze | cut -d= -f1 | while read pkg; do \
        meta=$(pip3 show $pkg 2>/dev/null); \
        lic=$(echo "$meta" | grep -i '^License:' | grep -Ei 'MPL|GPL|General Public License|EPL|Eclipse Public License|CDDL|LGPL'); \
        if [ ! -z "$lic" ]; then \
          pip3 download --no-binary :all: $pkg || true; \
        fi; \
      done; \
    fi

# Expose any necessary ports (if needed for debugging/monitoring)
EXPOSE 8080

ARG TIMESERIES_UID
ARG TIMESERIES_USER_NAME

RUN groupadd $TIMESERIES_USER_NAME -g $TIMESERIES_UID && \
    useradd -r -u $TIMESERIES_UID -g $TIMESERIES_USER_NAME $TIMESERIES_USER_NAME

USER $TIMESERIES_USER_NAME

# Run the ingestion service
CMD ["python", "ingestion.py"]
