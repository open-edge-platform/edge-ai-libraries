#!/bin/bash
# Copyright (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Entrypoint script for Metrics Manager
# Initializes required directories and files, then starts supervisor

set -e

echo "[INFO] Starting Metrics Manager..."

# Ensure directories exist
mkdir -p /app/custom-metrics

# Ensure named pipe for qmassa exists
if [ ! -p /app/qmassa.fifo ]; then
    mkfifo /app/qmassa.fifo 2>/dev/null || true
fi
chmod 666 /app/qmassa.fifo 2>/dev/null || true

# Check if custom telegraf config is mounted
if [ -n "$TELEGRAF_CONFIG_PATH" ] && [ -f "$TELEGRAF_CONFIG_PATH" ]; then
    echo "[INFO] Using Telegraf config: $TELEGRAF_CONFIG_PATH"
else
    echo "[INFO] Using default Telegraf config"
fi

echo "[INFO] Initialization complete"
echo "       - Metrics API port: ${METRICS_PORT:-9090}"
echo "       - Telegraf Prometheus port: ${TELEGRAF_PORT:-9273}"
echo "       - Custom metrics directory: ${CUSTOM_METRICS_DIR:-/app/custom-metrics}"

# Start supervisor to manage all processes
exec /usr/bin/supervisord -c /etc/supervisor/supervisord.conf
