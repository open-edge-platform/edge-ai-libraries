#!/bin/bash
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

set -e

# ---------------------------------------------------------------------------
# GPU / VA-API prerequisites (mirrors original DLSPS)
# ---------------------------------------------------------------------------
gpu_execution_prerequisites() {
    export LIBVA_DRIVER_NAME=iHD
    export LIBVA_DRIVERS_PATH=/usr/lib/x86_64-linux-gnu/dri
    export GST_VAAPI_ALL_DRIVERS=1

    mkdir -p /var/tmp/.cl-cache
    export cl_cache_dir=/var/tmp/.cl-cache
}

gpu_execution_prerequisites

# ---------------------------------------------------------------------------
# Start the FastAPI server
# ---------------------------------------------------------------------------
PORT=${REST_SERVER_PORT:-8080}
LOG_LEVEL=${WEB_SERVER_LOG_LEVEL:-warning}

cd "$(dirname "$0")"

exec uvicorn api.main:app \
    --app-dir src \
    --host 0.0.0.0 \
    --port "${PORT}" \
    --log-level "${LOG_LEVEL,,}"
