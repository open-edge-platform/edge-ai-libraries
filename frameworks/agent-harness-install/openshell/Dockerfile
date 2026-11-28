# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
FROM node:24.21.0-bookworm
ARG HARNESS_AGENT
# Hermes pin override (both or neither); empty keeps the pin built into agents.sh.
ARG HERMES_PINNED_COMMIT=
ARG HERMES_PINNED_SHA256=
# Hermes telemetry plugin source (HARNESS_HERMES_OTEL_PLUGIN / HARNESS_HERMES_OTEL_REF in scripts/lib/metrics.sh).
ARG HERMES_OTEL_PLUGIN=hermes_otel
ARG HERMES_OTEL_REF=
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       curl ca-certificates git iproute2 python3 python3-venv build-essential pkg-config \
    && rm -rf /var/lib/apt/lists/* \
    && install -d -o node -g node /sandbox /opt/harness
COPY scripts/lib/colors.sh scripts/lib/verify.sh scripts/lib/state.sh scripts/lib/sudo.sh scripts/lib/shim.sh scripts/lib/nodejs.sh scripts/lib/agents.sh /opt/harness/lib/
USER node
ENV NPM_CONFIG_PREFIX=/home/node/.local
ENV PATH=/home/node/.local/bin:/usr/local/bin:/usr/bin:/bin
# Reuse host-mode version pins and installer verification instead of maintaining separate pins.
RUN bash -euc 'for lib in colors verify state sudo shim nodejs agents; do source /opt/harness/lib/$lib.sh; done; \
    case "$1" in openclaw) install_openclaw ;; deepagents-code) install_dcode ;; hermes) install_hermes ;; *) error "Unsupported sandbox agent" ;; esac' \
    _ "$HARNESS_AGENT"
# The default sandbox policy denies registry egress, so OpenClaw's exporter plugin is fetched at build time; agent-start.sh links it into the sandbox home.
RUN if [ "$HARNESS_AGENT" = openclaw ]; then bash -euc 'for lib in colors verify state sudo shim nodejs agents; do source /opt/harness/lib/$lib.sh; done; \
    openclaw plugins install "npm:@openclaw/diagnostics-otel@$(installed_npm_global_version openclaw)" --accept-capabilities </dev/null; \
    rm -rf "$HOME/.openclaw/openclaw.json" "$HOME/.openclaw/state" "$HOME/.openclaw/config-journal-fingerprint.key"'; fi
# Hermes's plugin enable resolves Python dependencies over the network, which the default sandbox policy denies. So the
# hermes-otel plugin is installed and enabled here, and kept silent by a hermes_otel.yaml with enabled: false
# (written below); 'observability enable' only rewrites that file.
RUN if [ "$HARNESS_AGENT" = hermes ]; then bash -euc 'export HERMES_HOME=/home/node/.hermes; \
    hermes plugins install "$1" ${2:+--ref "$2"} </dev/null; \
    hermes plugins enable hermes_otel </dev/null; \
    rm -f "$HERMES_HOME"/hermes_otel_live.db*; find "$HERMES_HOME/logs" -type f -delete 2>/dev/null || true' \
    _ "$HERMES_OTEL_PLUGIN" "$HERMES_OTEL_REF"; fi
USER root
# Keep startup-only changes from invalidating the expensive agent installation layer.
COPY openshell/agent-start.sh /usr/local/bin/harness-agent-start
COPY openshell/model-config.mjs /opt/harness/model-config.mjs
COPY openshell/observability-config.mjs /opt/harness/observability-config.mjs
COPY scripts/lib/hermes-api-config.mjs /opt/harness/hermes-api-config.mjs
RUN chmod 755 /usr/local/bin/harness-agent-start
USER node
RUN if [ "$HARNESS_AGENT" = hermes ]; then HERMES_HOME=/home/node/.hermes node /opt/harness/observability-config.mjs hermes-disable no-restart; fi
WORKDIR /sandbox
