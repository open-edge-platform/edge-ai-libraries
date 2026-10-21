# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
FROM node:24.21.0-bookworm
ARG HARNESS_AGENT
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       curl ca-certificates git iproute2 python3 python3-venv build-essential pkg-config \
    && rm -rf /var/lib/apt/lists/* \
    && install -d -o node -g node /sandbox /opt/harness
COPY scripts/lib/colors.sh scripts/lib/verify.sh scripts/lib/state.sh scripts/lib/sudo.sh scripts/lib/shim.sh scripts/lib/nodejs.sh scripts/lib/agents.sh /opt/harness/lib/
USER node
ENV NPM_CONFIG_PREFIX=/home/node/.local
ENV PATH=/home/node/.local/bin:/usr/local/bin:/usr/bin:/bin
RUN bash -euc 'for lib in colors verify state sudo shim nodejs agents; do source /opt/harness/lib/$lib.sh; done; \
    case "$1" in openclaw) install_openclaw ;; hermes) install_hermes ;; *) error "Unsupported sandbox agent" ;; esac' \
    _ "$HARNESS_AGENT"
USER root
COPY openshell/agent-start.sh /usr/local/bin/harness-agent-start
RUN chmod 755 /usr/local/bin/harness-agent-start
USER node
WORKDIR /sandbox
