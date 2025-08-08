#!/bin/bash

set -euo pipefail

models=(
    'YOLO v5m 640x640 (INT8)'
    'YOLO v10s 640x640 (FP16)'
    'YOLO v10m 640x640 (FP16)'
    'MobileNet V2 PyTorch (FP16)'
)

if [[ "${DOWNLOAD_PUBLIC_MODELS:-false}" == "true" ]]; then
    echo "DOWNLOAD_PUBLIC_MODELS is true, no need for cleanup. Exiting."
    exit 0
fi

for model in "${models[@]}"; do
    sed -i "/${model}/d" pipelines/*/config.yaml
done
