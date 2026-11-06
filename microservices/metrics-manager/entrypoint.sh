#!/bin/bash
# Copyright (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Entrypoint script for Metrics Manager
# Initializes required directories and files, then starts supervisor

set -e

echo "[INFO] Starting Metrics Manager..."

export TELEGRAF_CONFIG_PATH="${TELEGRAF_CONFIG_PATH-/etc/telegraf/telegraf.conf}"
export HARDWARE_TELEMETRY_ENABLED="${HARDWARE_TELEMETRY_ENABLED-true}"
export TURBOSTAT_BIN="${TURBOSTAT_BIN-/usr/local/bin/turbostat}"
export TURBOSTAT_INTERVAL="${TURBOSTAT_INTERVAL-5}"
export METRICS_PORT="${METRICS_PORT-9090}"
export TELEGRAF_PORT="${TELEGRAF_PORT-9273}"
export TELEGRAF_HTTP_PORT="${TELEGRAF_HTTP_PORT-8186}"
export TELEGRAF_HTTP_ENDPOINT="${TELEGRAF_HTTP_ENDPOINT-http://localhost:${TELEGRAF_HTTP_PORT}/write}"
export PROMETHEUS_TELEGRAF_ENDPOINT="${PROMETHEUS_TELEGRAF_ENDPOINT-http://localhost:${TELEGRAF_PORT}}"
TELEGRAF_ACTIVE_CONFIG_DIR=$(/opt/venv/bin/python /app/docker_collectors.py)
export TELEGRAF_ACTIVE_CONFIG_DIR

# Ensure directories exist
mkdir -p /app/custom-metrics 2>/dev/null || true

# Ensure named pipe for qmassa exists
QMASSA_FIFO_PATH="${QMASSA_FIFO_PATH:-/app/qmassa.fifo}"
if [ ! -p "$QMASSA_FIFO_PATH" ]; then
    mkfifo "$QMASSA_FIFO_PATH" 2>/dev/null || true
fi
chmod 666 "$QMASSA_FIFO_PATH" 2>/dev/null || true

# Check if custom telegraf config is mounted
if [ -n "$TELEGRAF_CONFIG_PATH" ] && [ -f "$TELEGRAF_CONFIG_PATH" ]; then
    echo "[INFO] Using Telegraf config: $TELEGRAF_CONFIG_PATH"
else
    echo "[INFO] Using default Telegraf config"
fi

echo "[INFO] Initialization complete"
echo "       - Metrics API port: ${METRICS_PORT:-9090}"
echo "       - Telegraf Prometheus port: ${TELEGRAF_PORT:-9273}"
echo "       - Telegraf HTTP listener port: ${TELEGRAF_HTTP_PORT}"
echo "       - Custom metrics directory: ${CUSTOM_METRICS_DIR:-/app/custom-metrics}"

# Start supervisor to manage all processes
exec supervisord -c /etc/supervisor/supervisord.conf
