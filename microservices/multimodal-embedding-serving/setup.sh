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
export EMBEDDING_USE_OV=true
export EMBEDDING_DEVICE=${EMBEDDING_DEVICE:-CPU}
export OV_PERFORMANCE_MODE=${OV_PERFORMANCE_MODE:-LATENCY}

# If EMBEDDING_DEVICE is GPU, set EMBEDDING_USE_OV to true
if [ "$EMBEDDING_DEVICE" = "GPU" ]; then
    export EMBEDDING_USE_OV=true
fi

export EMBEDDING_SERVER_PORT=9777

# Model configuration - REQUIRED: User must set EMBEDDING_MODEL_NAME
if [ -z "$EMBEDDING_MODEL_NAME" ]; then
    echo "ERROR: EMBEDDING_MODEL_NAME environment variable is required."
    echo ""
    echo "Please set a model name before sourcing setup.sh:"
    echo "  export EMBEDDING_MODEL_NAME=\"your-chosen-model\""
    echo "  source setup.sh"
    echo ""
    echo "See docs/user-guide/supported-models.md for complete model specifications."
    return 1
fi

# Model path configuration
export EMBEDDING_OV_MODELS_DIR=${EMBEDDING_OV_MODELS_DIR:-"/app/ov_models"}

# Check if EMBEDDING_MODEL_NAME is supported
case "$EMBEDDING_MODEL_NAME" in
    "CLIP/clip-vit-b-16"|"CLIP/clip-vit-l-14"|"CLIP/clip-vit-b-32"|"CLIP/clip-vit-h-14")
        echo "Using CLIP model: $EMBEDDING_MODEL_NAME"
        ;;
    "CN-CLIP/cn-clip-vit-b-16"|"CN-CLIP/cn-clip-vit-l-14"|"CN-CLIP/cn-clip-vit-h-14")
        echo "Using CN-CLIP model: $EMBEDDING_MODEL_NAME (Chinese + English support)"
        ;;
    "SigLIP/siglip2-vit-b-16"|"SigLIP/siglip2-vit-l-16"|"SigLIP/siglip2-so400m-patch16-384")
        echo "Using SigLIP model: $EMBEDDING_MODEL_NAME"
        ;;
    "MobileCLIP/mobileclip_s0"|"MobileCLIP/mobileclip_s1"|"MobileCLIP/mobileclip_s2"|"MobileCLIP/mobileclip_b"|"MobileCLIP/mobileclip_blt")
        echo "Using MobileCLIP model: $EMBEDDING_MODEL_NAME"
        ;;
    "Blip2/blip2_transformers")
        echo "Using BLIP2 model: $EMBEDDING_MODEL_NAME"
        ;;
    *)
        echo -e "WARNING: Model '$EMBEDDING_MODEL_NAME' may not be supported."
        echo -e "See docs/user-guide/supported-models.md for the complete list of supported models."
        ;;
esac

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
echo "EMBEDDING_MODEL_NAME set to: ${EMBEDDING_MODEL_NAME}"
echo "EMBEDDING_DEVICE set to: ${EMBEDDING_DEVICE}"
echo "EMBEDDING_USE_OV set to: ${EMBEDDING_USE_OV}"
echo "OV_PERFORMANCE_MODE set to: ${OV_PERFORMANCE_MODE}"