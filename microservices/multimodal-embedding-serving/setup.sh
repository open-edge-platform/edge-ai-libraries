#!/bin/bash

# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

export HOST_IP=$(hostname -I | awk '{print $1}')

# Registry handling - ensure consistent formatting with trailing slashes
# If REGISTRY_URL is set, ensure it ends with a trailing slash
[[ -n "$REGISTRY_URL" ]] && REGISTRY_URL="${REGISTRY_URL%/}/"

# If PROJECT_NAME is set, ensure it ends with a trailing slash
[[ -n "$PROJECT_NAME" ]] && PROJECT_NAME="${PROJECT_NAME%/}/"

export REGISTRY="${REGISTRY_URL}${PROJECT_NAME}"

# Set default tag if not already set
export TAG=${TAG:-latest}

# Video processing defaults
export DEFAULT_START_OFFSET_SEC=0
export DEFAULT_CLIP_DURATION=-1  # -1 means take the video till end
export DEFAULT_NUM_FRAMES=64

# OpenVINO configuration
export EMBEDDING_USE_OV=false
export EMBEDDING_DEVICE=${EMBEDDING_DEVICE:-CPU}

# If EMBEDDING_DEVICE is GPU, set EMBEDDING_USE_OV to true
if [ "$EMBEDDING_DEVICE" = "GPU" ]; then
    export EMBEDDING_USE_OV=true
fi

export EMBEDDING_SERVER_PORT=9777
export USE_ONLY_TEXT_EMBEDDINGS=${USE_ONLY_TEXT_EMBEDDINGS}  # Setup multimodal embedding models, not just text models.

# Check if VCLIP_MODEL is not defined or empty
if [ -z "$VCLIP_MODEL" ] || [ "$VCLIP_MODEL" != "openai/clip-vit-base-patch32" ]; then
    echo -e "ERROR: VCLIP_MODEL is either not set or is set to an invalid value in your shell environment."
    return
fi

if [ -z "$QWEN_MODEL" ] || [ "$QWEN_MODEL" != "Qwen/Qwen3-Embedding-0.6B" ]; then
    echo -e "ERROR: QWEN_MODEL is either not set or is set to an invalid value in your shell environment."
    return
fi

# Fetch group IDs
VIDEO_GROUP_ID=$(getent group video | awk -F: '{print $3}')
RENDER_GROUP_ID=$(getent group render | awk -F: '{print $3}')
export USER_ID=$(id -u)
export USER_GROUP_ID=$(id -g)

docker volume create data-prep
docker volume create ov-models


export EMBEDDING_SERVER_PORT=$EMBEDDING_SERVER_PORT
export no_proxy_env=${no_proxy},$HOST_IP

export VIDEO_GROUP_ID=$VIDEO_GROUP_ID
export RENDER_GROUP_ID=$RENDER_GROUP_ID

echo "Environment variables set successfully."
echo "REGISTRY set to: ${REGISTRY}"
echo "VCLIP_MODEL set to: ${VCLIP_MODEL}"
echo "QWEN_MODEL set to: ${QWEN_MODEL}"
echo "EMBEDDING_DEVICE set to: ${EMBEDDING_DEVICE}"
echo "Using only text embedding model: ${USE_ONLY_TEXT_EMBEDDINGS:-False}"