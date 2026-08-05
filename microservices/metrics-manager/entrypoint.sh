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

# Optional runtime OpenVINO install to keep default image size small.
# - ENABLE_OV_RUNTIME_INSTALL=true enables installation on container startup.
# - OV_PIP_SPEC controls the version/specifier (default: openvino==2026.1.0).
# - OV_INSTALL_STRICT=true fails startup if install fails.
ENABLE_OV_RUNTIME_INSTALL="${ENABLE_OV_RUNTIME_INSTALL:-false}"
OV_PIP_SPEC="${OV_PIP_SPEC:-openvino==2026.1.0}"
OV_INSTALL_STRICT="${OV_INSTALL_STRICT:-false}"

if [ "$ENABLE_OV_RUNTIME_INSTALL" = "true" ]; then
    if python -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('openvino') else 1)"; then
        echo "[INFO] OpenVINO already available; skipping runtime install"
    else
        echo "[INFO] Runtime OpenVINO install enabled; installing: $OV_PIP_SPEC"
        if pip install --no-cache-dir "$OV_PIP_SPEC"; then
            echo "[INFO] OpenVINO runtime install completed"
        else
            echo "[WARN] OpenVINO runtime install failed"
            if [ "$OV_INSTALL_STRICT" = "true" ]; then
                echo "[ERROR] OV_INSTALL_STRICT=true; exiting"
                exit 1
            fi
            echo "[WARN] Continuing without OpenVINO"
        fi
    fi
else
    echo "[INFO] Runtime OpenVINO install disabled (ENABLE_OV_RUNTIME_INSTALL=false)"
fi

echo "[INFO] Initialization complete"
echo "       - Metrics API port: ${METRICS_PORT:-9090}"
echo "       - Telegraf Prometheus port: ${TELEGRAF_PORT:-9273}"
echo "       - Custom metrics directory: ${CUSTOM_METRICS_DIR:-/app/custom-metrics}"

# Start supervisor to manage all processes
exec supervisord -c /etc/supervisor/supervisord.conf
