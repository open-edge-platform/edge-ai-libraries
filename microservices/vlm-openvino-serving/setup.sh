#!/bin/bash

# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

export HOST_IP=$(hostname -I | awk '{print $1}')
export no_proxy_env=${no_proxy}

export VLM_DEVICE=CPU

export TAG=${TAG:-latest}

# If REGISTRY_URL is set, ensure it ends with a trailing slash
# Using parameter expansion to conditionally append '/' if not already present
[[ -n "$REGISTRY_URL" ]] && REGISTRY_URL="${REGISTRY_URL%/}/"

# If PROJECT_NAME is set, ensure it ends with a trailing slash
[[ -n "$PROJECT_NAME" ]] && PROJECT_NAME="${PROJECT_NAME%/}/"

export REGISTRY="${REGISTRY_URL}${PROJECT_NAME}"

# Ensure both .cache and .cache/huggingface directories exist and have correct permissions
CACHE_DIR="/home/$USER/.cache"
HF_CACHE_DIR="$CACHE_DIR/huggingface"

# Create directories if they don't exist
if [ ! -d "$CACHE_DIR" ]; then
    mkdir -p "$CACHE_DIR"
    echo "Created cache directory: $CACHE_DIR"
fi

if [ ! -d "$HF_CACHE_DIR" ]; then
    mkdir -p "$HF_CACHE_DIR"
    echo "Created huggingface cache directory: $HF_CACHE_DIR"
fi

# Check permissions of .cache directory first
if [ ! -w "$CACHE_DIR" ] || [ "$(stat -c '%U:%G' "$CACHE_DIR")" != "$USER:$(id -gn)" ]; then
    echo "Warning: $CACHE_DIR is not owned by $USER:$(id -gn)"
    echo "Attempting to fix permissions for cache directory (may require sudo)..."
    sudo chown $USER:$(id -gn) "$CACHE_DIR"
    if [ $? -ne 0 ]; then
        echo "ERROR: Failed to update permissions for $CACHE_DIR"
    else
        echo "Successfully updated ownership of $CACHE_DIR"
    fi
fi

# Check ownership of huggingface directory and files within
if find "$HF_CACHE_DIR" -not -user $USER -o -not -group $(id -gn) | grep -q .; then
    echo "Warning: Some files in $HF_CACHE_DIR are not owned by $USER:$(id -gn)"
    echo "Attempting to fix permissions recursively (may require sudo)..."
    sudo chown -R $USER:$(id -gn) "$HF_CACHE_DIR"
    if [ $? -eq 0 ]; then
        echo "Successfully updated permissions for all files in $HF_CACHE_DIR"
    else
        echo "ERROR: Failed to update permissions. Container may fail to write to cache."
        echo "Please run: sudo chown -R $USER:$(id -gn) $HF_CACHE_DIR"
    fi
else
    echo "HuggingFace cache directory permissions are correct."
fi

docker volume create ov-models
echo "Created docker volume for the models."

export VLM_COMPRESSION_WEIGHT_FORMAT=int8
# Number of uvicorn workers
export WORKERS=6

if [[ "$VLM_DEVICE" == "GPU" ]]; then
    export VLM_COMPRESSION_WEIGHT_FORMAT=int4
    export WORKERS=1
fi

# Export current user and group IDs for container user
export USER_ID=$(id -u)
export USER_GROUP_ID=$(id -g)
export VIDEO_GROUP_ID=$(getent group video | awk -F: '{printf "%s\n", $3}')
export RENDER_GROUP_ID=$(getent group render | awk -F: '{printf "%s\n", $3}')

export VLM_SERVICE_PORT=9764
export VLM_SEED=42

# By default, VLM_MAX_COMPLETION_TOKENS is unset (which results in None in Python)
# To set a specific value, uncomment and modify the following line:
# export VLM_MAX_COMPLETION_TOKENS=1000
unset VLM_MAX_COMPLETION_TOKENS

# Check if VLM_MODEL_NAME is not defined or empty
if [ -z "$VLM_MODEL_NAME" ]; then
    echo -e "ERROR: VLM_MODEL_NAME is not set in your shell environment."
    return
else
    export VLM_MODEL_NAME=$VLM_MODEL_NAME
    echo -n VLM_MODEL_NAME: ${VLM_MODEL_NAME}
fi