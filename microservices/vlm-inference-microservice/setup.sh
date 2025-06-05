#!/bin/bash

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

export VLM_SERVICE_PORT=9764
export VLM_SEED=42

# Check if VLM_MODEL_NAME is not defined or empty
if [[ -z "$VLM_MODEL_NAME" ]]; then
    echo "Warning: VLM_MODEL_NAME is not defined."
    read -p "Please enter the VLM_MODEL_NAME: " user_model_name
    if [[ -n "$user_model_name" ]]; then
        echo "Using provided model name: $user_model_name"
        export VLM_MODEL_NAME="$user_model_name"
    else
        echo "Error: No model name provided. Exiting."
        exit 1
    fi
fi