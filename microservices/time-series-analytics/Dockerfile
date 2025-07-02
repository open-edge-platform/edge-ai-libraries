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

# Optionally download copyleft sources if requested
ARG COPYLEFT_SOURCES=false
RUN if [ "$COPYLEFT_SOURCES" = "true" ]; then \
        apt-get update && \
        # Get list of installed deb packages with copyleft licenses \
        sed -Ei 's/# deb-src /deb-src /' /etc/apt/sources.list && \
        apt-get update && \
        mkdir -p /copyleft_sources/deb && cd /copyleft_sources/deb && \
        echo -n $null > copyleft_package_list.txt && \
        for package in $(dpkg -l | awk '/^ii/ {print $2}' | cut -d: -f1); do \
            grep -l 'Copyleft\|GPL\|LGPL\|EPL\|MPL\|CDDL' /usr/share/doc/${package}/copyright; \
            exit_status=$?; \
            if [ $exit_status -eq 0 ]; then \
                echo $package >> copyleft_package_list.txt; \
                apt-get source -q --download-only $package; \
            fi; \
        done; \
        # Get source code for installed Python packages with copyleft licenses \
        mkdir -p /copyleft_sources/python && \
        cd /copyleft_sources/python && \
        apt-get update && apt-get install -y gcc build-essential libffi-dev python3-dev && \
        # Download python package sources with relevant licenses \
        pip3 freeze | cut -d= -f1 | while read pkg; do \
            meta=$(pip3 show $pkg 2>/dev/null); \
            lic=$(echo "$meta" | grep -i '^License:' | grep -E 'MPL|GPL|General Public License|EPL|Eclipse Public License|CDDL|LGPL'); \
            if [ ! -z "$lic" ]; then \
                echo "Downloading source for $pkg with license: $lic"; \
                pip3 download --no-binary :all: $pkg || true; \
            fi; \
        done; \
        apt-get remove --purge -y gcc build-essential libffi-dev python3-dev; \
    fi

WORKDIR /app
# Remove git and clean up to reduce image size
RUN apt-get purge -y --auto-remove git && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/* /root/.cache/pip

# Switch to non-root user for security
USER $TIMESERIES_USER_NAME

# Simple healthcheck to verify container is running
HEALTHCHECK --interval=5m CMD exit 0

ENTRYPOINT ["python3", "./main.py"]
