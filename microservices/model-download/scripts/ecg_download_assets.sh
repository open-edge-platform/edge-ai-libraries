#!/bin/sh
set -e

MODEL_DIR="${1:-/models/ai-ecg}"
BASE_URL="${HLS_ECG_BASE_URL}"

MODELS="
ecg_8960_ir10_fp16.xml
ecg_8960_ir10_fp16.bin
ecg_17920_ir10_fp16.xml
ecg_17920_ir10_fp16.bin
"

echo "[INFO] Creating ECG model directory: ${MODEL_DIR}"
mkdir -p "${MODEL_DIR}"

for model in $MODELS; do
  if [ ! -f "${MODEL_DIR}/${model}" ]; then
    echo "[INFO] Downloading ${model}"
    curl -s -o "${MODEL_DIR}/${model}" "${BASE_URL}/${model}"
  else
    echo "[INFO] ${model} already exists, skipping"
  fi
done

echo "[INFO] ECG models ready"
