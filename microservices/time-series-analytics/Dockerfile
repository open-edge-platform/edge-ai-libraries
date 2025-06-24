#
# Apache v2 license
# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

# Use the Kapacitor image as the base image
ARG KAPACITOR_VERSION
FROM kapacitor:$KAPACITOR_VERSION

# Install Python and necessary packages in a single layer, minimize image size
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        python3 python3-pip git ca-certificates && \
    python3 -m pip install --no-cache-dir --upgrade pip && \
    apt-get purge -y --auto-remove && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Clone only the required files to reduce image size
RUN git clone --depth 1 --filter=blob:none --sparse --branch v${KAPACITOR_VERSION} \
    https://github.com/influxdata/kapacitor.git /tmp/kapacitor && \
    cd /tmp/kapacitor && \
    git sparse-checkout set udf/agent/py && \
    mv /tmp/kapacitor/udf/agent/py /app/kapacitor_python && \
    rm -rf /tmp/kapacitor

ARG TIMESERIES_UID
ARG TIMESERIES_USER_NAME
ARG PYTHON_VERSION

# Create non-root user and group in a single layer for smaller image and better caching
RUN groupadd --gid $TIMESERIES_UID $TIMESERIES_USER_NAME && \
    useradd --no-log-init --system --uid $TIMESERIES_UID --gid $TIMESERIES_UID --create-home $TIMESERIES_USER_NAME

COPY ./requirements.txt .

# Install Python dependencies efficiently and clean up cache to reduce image size
RUN pip3 install --no-cache-dir -r requirements.txt

# Set environment variables in a single ENV instruction for better layer caching
ENV PYTHONPATH="$PYTHONPATH:/tmp/py_package:/app/kapacitor_python/" \
    LD_LIBRARY_PATH="$LD_LIBRARY_PATH:/app/idp/lib"

# Adding classifier program
# Copy Python source files in a single layer for better caching
COPY ./src/classifier_startup.py ./src/opcua_alerts.py ./src/mr_interface.py ./src/main.py /app/

# Copy configuration files and directories efficiently
COPY ./config.json /app/
COPY ./config/kapacitor*.conf /app/config/
COPY ./tick_scripts /app/temperature_classifier/tick_scripts/
COPY ./udfs /app/temperature_classifier/udfs/

# Remove git and clean up to reduce image size
RUN apt-get purge -y --auto-remove git && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/* /root/.cache/pip

# Switch to non-root user for security
USER $TIMESERIES_USER_NAME

# Simple healthcheck to verify container is running
HEALTHCHECK --interval=5m CMD exit 0

ENTRYPOINT ["python3", "./main.py"]
