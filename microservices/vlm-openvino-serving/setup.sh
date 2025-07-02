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

# By default, HUGGINGFACE_TOKEN is unset
# To download Gated Models you need to pass your Huggingface Token as described here (https://huggingface.co/docs/hub/models-gated#access-gated-models-as-a-user)
# To set a specific value, uncomment and modify the following line:
# export HUGGINGFACE_TOKEN=<your_huggingface_token_here>
unset HUGGINGFACE_TOKEN

# Check if VLM_MODEL_NAME is not defined or empty
if [ -z "$VLM_MODEL_NAME" ]; then
    echo -e "ERROR: VLM_MODEL_NAME is not set in your shell environment."
    return
else
    export VLM_MODEL_NAME=$VLM_MODEL_NAME
    echo -n VLM_MODEL_NAME: ${VLM_MODEL_NAME}
fi
if [ -z "$HUGGINGFACE_TOKEN" ]; then
    echo -e "\nWARNING: HUGGINGFACE_TOKEN is not set."
else
    echo -e "\nHUGGINGFACE_TOKEN is set."
fi