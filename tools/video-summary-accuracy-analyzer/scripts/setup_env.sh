#!/bin/bash
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Default values
MODEL_CACHE_PATH="/home/${USER}/model_cache/sbert"

# Check if MODEL_CACHE_PATH exists
if [ -e "$MODEL_CACHE_PATH" ]; then
    # If it exists, check the owner
    if [ "$(stat -c '%U:%G' "$MODEL_CACHE_PATH")" != "root:root" ]; then
        echo "$MODEL_CACHE_PATH exists in host..."
    else
        # If owned by root:root, delete and recreate it
        echo "$MODEL_CACHE_PATH exists and is owned by root:root. Deleting it and recreate..."
        sudo rm -rf "$MODEL_CACHE_PATH"
        mkdir -p "$MODEL_CACHE_PATH"
    fi
else
    # If it doesn't exist, create it
    echo "$MODEL_CACHE_PATH does not exist. Creating it..."
    mkdir -p "$MODEL_CACHE_PATH"
fi


USER_GROUP_ID="$(id -g "${USER}")"
export USER_GROUP_ID
export SBERT_MODEL_ID="all-mpnet-base-v2"
export MODEL_CACHE_PATH="$MODEL_CACHE_PATH"
export APP_BACKEND_URL="http://video-accuracy-eval:9000/v1/eval"

# Container image coordinates. Override REGISTRY/TAG to pull different images.
export REGISTRY="${REGISTRY:-intel/}"
export TAG="${TAG:-latest}"
