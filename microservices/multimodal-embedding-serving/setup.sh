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

export APP_NAME="multimodal-embedding-serving"
export APP_DISPLAY_NAME="Multimodal Embedding serving"
export APP_DESC="Generates embeddings for text, images, and videos using pretrained models"

# Video processing defaults
export DEFAULT_START_OFFSET_SEC=0
export DEFAULT_CLIP_DURATION=-1  # -1 means take the video till end
export DEFAULT_NUM_FRAMES=64

# OpenVINO configuration
export EMBEDDING_USE_OV=false
export EMBEDDING_DEVICE=CPU

export EMBEDDING_SERVER_PORT=9777

# Check if VCLIP_MODEL is not defined or empty
if [ -z "$VCLIP_MODEL" ]; then
    echo -e "ERROR: VCLIP_MODEL is not set in your shell environment."
    return
elif [ "$VCLIP_MODEL" != "openai/clip-vit-base-patch32" ]; then
    echo -e "ERROR: VCLIP_MODEL is set to an invalid value. Expected: 'openai/clip-vit-base-patch32'."
    return
fi

# Fetch group IDs
VIDEO_GROUP_ID=$(getent group video | awk -F: '{print $3}')
RENDER_GROUP_ID=$(getent group render | awk -F: '{print $3}')

docker volume create data-prep
docker volume create ov-models


export EMBEDDING_SERVER_PORT=$EMBEDDING_SERVER_PORT
export no_proxy_env=${no_proxy},$HOST_IP

export VIDEO_GROUP_ID=$VIDEO_GROUP_ID
export RENDER_GROUP_ID=$RENDER_GROUP_ID

echo "Environment variables set successfully."
echo "REGISTRY set to: ${REGISTRY}"
echo "VCLIP_MODEL set to: ${VCLIP_MODEL}"
echo "EMBEDDING_DEVICE set to: ${EMBEDDING_DEVICE}"