#!/bin/bash
set -euo pipefail

# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

VLM_MODEL_NAME=$1
VLM_COMPRESSION_WEIGHT_FORMAT=$2
VLM_DEVICE=${3:-CPU}
HUGGINGFACE_TOKEN=${4:-}
VLM_NPU_EXPORT_PROFILE=${VLM_NPU_EXPORT_PROFILE:-safe}
VLM_NPU_VLM_NUM_SAMPLES=${VLM_NPU_VLM_NUM_SAMPLES:-16}
VLM_NPU_VLM_GROUP_SIZE=${VLM_NPU_VLM_GROUP_SIZE:--1}
VLM_NPU_VLM_RATIO=${VLM_NPU_VLM_RATIO:-0.8}
VLM_NPU_VLM_SENSITIVITY_METRIC=${VLM_NPU_VLM_SENSITIVITY_METRIC:-mean_activation_magnitude}

if [[ "${VLM_DEVICE^^}" == NPU* ]] && [[ "${VLM_COMPRESSION_WEIGHT_FORMAT,,}" != "int4" && "${VLM_COMPRESSION_WEIGHT_FORMAT,,}" != "nf4" ]]; then
    echo "NPU target requires int4/nf4 precision for VLM export. Overriding weight format '${VLM_COMPRESSION_WEIGHT_FORMAT}' -> 'int4'."
    VLM_COMPRESSION_WEIGHT_FORMAT="int4"
fi

MODEL_DIR=$(echo $VLM_MODEL_NAME | awk -F/ '{print $NF}')
DEVICE_DIR=$(echo "$VLM_DEVICE" | tr '[:upper:]' '[:lower:]')

# Scope exported/downloaded model artifacts by device to avoid cross-device reuse.
# OpenVINO namespace models are already converted; no weight subfolder needed.
if [[ "$VLM_MODEL_NAME" == OpenVINO/* ]]; then
    MODEL_DIR="ov-model/$MODEL_DIR/$DEVICE_DIR"
else
    MODEL_DIR="ov-model/$MODEL_DIR/$DEVICE_DIR/$VLM_COMPRESSION_WEIGHT_FORMAT"
fi

echo "Model Name: $VLM_MODEL_NAME"
echo "Compression Weight Format: $VLM_COMPRESSION_WEIGHT_FORMAT"
echo "Compilation Device: $VLM_DEVICE"
echo "Requested NPU Export Profile: $VLM_NPU_EXPORT_PROFILE"
echo "Model Directory: $MODEL_DIR"

# Login to Hugging Face if token is provided and not 'none'
if [ -n "$HUGGINGFACE_TOKEN" ] && [ "$HUGGINGFACE_TOKEN" != "none" ]; then
    echo "Logging in to Hugging Face to access gated models..."
    hf auth login --token "$HUGGINGFACE_TOKEN"
fi

if [ ! -d "$MODEL_DIR" ]; then
    echo "Model directory does not exist. Preparing model..."

    # Models under the OpenVINO HF namespace are already in IR format;
    # download them directly instead of running optimum-cli export.
    if [[ "$VLM_MODEL_NAME" == OpenVINO/* ]]; then
        echo "OpenVINO namespace model detected. Downloading pre-converted IR model..."
        DOWNLOAD_CMD=(
            hf download
            "$VLM_MODEL_NAME"
            --local-dir "$MODEL_DIR"
        )

        if ! "${DOWNLOAD_CMD[@]}"; then
            echo "Model download failed. Removing partial artifacts in $MODEL_DIR" >&2
            rm -rf "$MODEL_DIR"
            exit 1
        fi
        echo "Model downloaded successfully to $MODEL_DIR"
    else
        echo "Starting model compression..."
        EXPORT_CMD=(
            optimum-cli export openvino
            --trust-remote-code
            --model "$VLM_MODEL_NAME"
            "$MODEL_DIR"
            --weight-format "$VLM_COMPRESSION_WEIGHT_FORMAT"
        )

        task_forced=false

        # This service targets VLM models only. For NPU INT4/NF4 export, force
        # image-text-to-text task and select export profile:
        # - safe: OVMS-like defaults (--sym --ratio 1.0 --group-size -1)
        # - data_aware: contextual calibration settings
        if [[ "${VLM_DEVICE^^}" == NPU* ]] && [[ "${VLM_COMPRESSION_WEIGHT_FORMAT,,}" == "int4" || "${VLM_COMPRESSION_WEIGHT_FORMAT,,}" == "nf4" ]]; then
            profile=$(echo "${VLM_NPU_EXPORT_PROFILE}" | tr '[:upper:]' '[:lower:]')
            if [[ "${profile}" != "safe" && "${profile}" != "data_aware" ]]; then
                echo "Invalid VLM_NPU_EXPORT_PROFILE='${VLM_NPU_EXPORT_PROFILE}'. Supported values: safe, data_aware." >&2
                exit 1
            fi
            echo "Effective NPU Export Profile: ${profile}"
            EXPORT_CMD+=(--task image-text-to-text)
            if [[ "${profile}" == "safe" ]]; then
                echo "Applying NPU VLM safe export profile: --task image-text-to-text --sym --ratio 1.0 --group-size -1"
                EXPORT_CMD+=(--sym --ratio 1.0 --group-size -1)
            elif [[ "${profile}" == "data_aware" ]]; then
                echo "Applying NPU VLM data-aware export profile: --task image-text-to-text --group-size ${VLM_NPU_VLM_GROUP_SIZE} --ratio ${VLM_NPU_VLM_RATIO} --dataset contextual --sensitivity-metric ${VLM_NPU_VLM_SENSITIVITY_METRIC} --num-samples ${VLM_NPU_VLM_NUM_SAMPLES}"
                EXPORT_CMD+=(
                    --group-size "${VLM_NPU_VLM_GROUP_SIZE}"
                    --ratio "${VLM_NPU_VLM_RATIO}"
                    --dataset contextual
                    --sensitivity-metric "${VLM_NPU_VLM_SENSITIVITY_METRIC}"
                    --num-samples "${VLM_NPU_VLM_NUM_SAMPLES}"
                )
            fi
            task_forced=true
        fi

        if [[ "${VLM_DEVICE^^}" == NPU* ]]; then
            TRANSFORMERS_VERSION=$(python -c "import transformers; print(transformers.__version__)" 2>/dev/null || true)
            if [[ -n "${TRANSFORMERS_VERSION}" && "${TRANSFORMERS_VERSION}" != "4.51.3" ]]; then
                echo "WARNING: OpenVINO 2026.2 NPU export guidance recommends transformers==4.51.3 (current: ${TRANSFORMERS_VERSION})."
            fi
        fi

        if [[ "$VLM_MODEL_NAME" == openbmb/MiniCPM-o-2_6* ]] && [[ "${task_forced}" != "true" ]]; then
            echo "openbmb/MiniCPM-o-2_6 model detected. Forcing image-text-to-text export task."
            EXPORT_CMD+=(--task image-text-to-text)
        fi

        if ! "${EXPORT_CMD[@]}"; then
            echo "Model export failed. Removing partial artifacts in $MODEL_DIR" >&2
            rm -rf "$MODEL_DIR"
            exit 1
        fi
        echo "Model exported successfully to $MODEL_DIR"
    fi
else
    echo "Model directory already exists. Skipping export."
fi

echo "Model compression script completed."