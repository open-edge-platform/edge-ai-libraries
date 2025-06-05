#
# Apache v2 license
# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

# Use the Kapacitor 1.7.6 image as the base image
ARG KAPACITOR_VERSION
FROM kapacitor:$KAPACITOR_VERSION

# Install Python and other necessary packages
RUN apt-get update && \
    apt-get install -y --no-install-recommends python3 python3-dev python3-pip python3-venv git && \
    pip install -U pip && \
    pip uninstall -y setuptools && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN mkdir -p /app/kapacitor-${KAPACITOR_VERSION} && \
    git clone --single-branch -b v${KAPACITOR_VERSION} \
    https://github.com/influxdata/kapacitor.git /app/kapacitor-${KAPACITOR_VERSION} && \
    mv /app/kapacitor-${KAPACITOR_VERSION}/udf/agent/py /app/kapacitor_python && \
    rm -r kapacitor-${KAPACITOR_VERSION}

ARG TIMESERIES_UID
ARG TIMESERIES_USER_NAME
ARG PYTHON_VERSION
RUN groupadd $TIMESERIES_USER_NAME -g $TIMESERIES_UID && \
    useradd -r -u $TIMESERIES_UID -g $TIMESERIES_USER_NAME $TIMESERIES_USER_NAME

COPY ./requirements.txt .

RUN pip3 install -r requirements.txt

ENV PYTHONPATH $PYTHONPATH:/tmp/py_package:/app/kapacitor_python/
ENV LD_LIBRARY_PATH $LD_LIBRARY_PATH:/app/idp/lib

# Adding classifier program
COPY ./src/classifier_startup.py /app
COPY ./src/opcua_alerts.py /app
COPY ./src/mr_interface.py /app
COPY ./config.json /app
# Add configs
COPY ./config/kapacitor*.conf /app/config/
COPY ./tick_scripts /app/temperature_classifier/tick_scripts
COPY ./udfs /app/temperature_classifier/udfs

RUN apt-get remove --purge -y git

USER $TIMESERIES_USER_NAME

HEALTHCHECK --interval=5m CMD exit 0

ENTRYPOINT ["python3", "./classifier_startup.py"]
