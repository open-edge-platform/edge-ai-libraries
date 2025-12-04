# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Builder stage
FROM python:3.12.12-slim AS builder

ARG USER_ID=1000
ARG USER_GROUP_ID=1000
ARG POETRY_VERSION="1.8.3"
ARG MOBILECLIP_COMMIT="c16bfe5a4feb424762d6bdf5245539120a4ce9ef"
ARG SALESFORCE_LAVIS_VERSION="1.0.2"

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    patch \
    build-essential \
    gcc \
    git && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY poetry.lock pyproject.toml /app/
RUN pip install --no-cache-dir poetry==${POETRY_VERSION} && \
    poetry config virtualenvs.create false && \
    poetry install --no-root && \
    poetry run pip install --no-cache-dir \
        "git+https://github.com/apple/ml-mobileclip.git@${MOBILECLIP_COMMIT}#egg=mobileclip" \
        "salesforce-lavis==${SALESFORCE_LAVIS_VERSION}" \
        --no-deps

# Final stage
FROM python:3.12.12-slim

ARG USER_ID=1000
ARG USER_GROUP_ID=1000
ARG INSTALL_DRIVER_VERSION="24.39.31294"
ENV INSTALL_DRIVER_VERSION=${INSTALL_DRIVER_VERSION}
ARG COPYLEFT_SOURCES=false

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    patch && \
    rm -rf /var/lib/apt/lists/* && \
    groupadd -g ${USER_GROUP_ID} appuser && useradd -m --no-log-init -s /bin/bash -u ${USER_ID} -g ${USER_GROUP_ID} appuser

WORKDIR /app


# Copy installed site-packages and bin from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin/gunicorn /usr/local/bin/gunicorn
COPY --from=builder /app /app

# Refresh security patches after bringing in build artifacts
RUN apt-get update && apt-get upgrade -y --no-install-recommends && rm -rf /var/lib/apt/lists/*

# Copy rest of the source code

# Install GPU drivers in final image
COPY scripts/install_ubuntu_gpu_drivers.sh /tmp/install_gpu_drivers.sh
RUN chmod +x /tmp/install_gpu_drivers.sh && \
/tmp/install_gpu_drivers.sh && \
apt-get clean && rm -rf /tmp/install_gpu_drivers.sh && rm -rf /var/lib/apt/lists/* && rm -rf /tmp/*

# Optionally download copyleft sources if requested
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

COPY . .

RUN mkdir -p /tmp/dataprep/video /home/appuser/.cache/huggingface /app/ov_models && \
    chown -R appuser:appuser /home/appuser/.cache /app/ov_models /tmp/dataprep

USER appuser

EXPOSE 8000

CMD ["gunicorn", "-b", "0.0.0.0:8000", "-k", "uvicorn.workers.UvicornWorker", "src.app:app", "--timeout", "300", "--log-level", "debug"]