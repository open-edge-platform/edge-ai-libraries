#!/bin/bash

# Run video manager and exit if it fails
if ! ./video_manager.sh; then
    echo "[ERROR] video_manager.sh failed. Exiting."
    exit 1
fi

exec uvicorn api.main:app --host 0.0.0.0 --port 7860 --ws-ping-interval 10 --ws-ping-timeout 30
