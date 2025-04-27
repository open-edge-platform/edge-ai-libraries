#!/bin/bash

# This script sets up the environment for the Chat Question and Answer Core application.
# It accepts two optional parameters:
# -p or --path: Specify the model cache path (default is /tmp/model_cache/)
# -d or --device: Specify the device (default is cpu)
# Usage:
# ./setup_env.sh
# OR
# ./setup_env.sh -p /path/to/model_cache -d gpu

# Default values
MODEL_CACHE_PATH="/tmp/model_cache/"
DEVICE="cpu"
PROFILES="DEFAULT"

# Parse named arguments using getopts
# -p for MODEL_CACHE_PATH
# -d for DEVICE
while [[ "$#" -gt 0 ]]; do
    case $1 in
        -p|--path) MODEL_CACHE_PATH="$2"; shift ;;
        -d|--device) DEVICE="$2"; shift ;;
        *)
            echo "Unknown parameter passed: $1"
            echo "Accepted parameters are:"
            echo "  -p  --path : Specify the model cache path"
            echo "  -d  --device : Specify the device"
            return 1
            ;;
    esac
    shift
done

# Check if DEVICE value is valid
if [[ "$DEVICE" != "cpu" && "$DEVICE" != "gpu" ]]; then
    echo "Error: Invalid device value '$DEVICE'. Valid values are 'cpu' or 'gpu'."
    return 1
fi

# Check if MODEL_CACHE_PATH is an absolute path
if [[ "$MODEL_CACHE_PATH" != /* ]]; then
    MODEL_CACHE_PATH="$PWD/$MODEL_CACHE_PATH"
    echo "Relative path provided. Using absolute path: $MODEL_CACHE_PATH"
fi

# Check if MODEL_CACHE_PATH exists
if [ -e "$MODEL_CACHE_PATH" ]; then
    # If it exists, check the owner
    if [ "$(stat -c '%U:%G' "$MODEL_CACHE_PATH")" != "root:root" ]; then
        echo "$MODEL_CACHE_PATH exists in host..."
    else
        # If owned by root:root, delete and recreate it
        echo "$MODEL_CACHE_PATH exists and is owned by root:root. Deleting it and recreate..."
        sudo rm -rf "$MODEL_CACHE_PATH"
        mkdir "$MODEL_CACHE_PATH"
    fi
else
    # If it doesn't exist, create it
    echo "$MODEL_CACHE_PATH does not exist. Creating it..."
    mkdir "$MODEL_CACHE_PATH"
fi

# Set COMPOSE_PROFILES based on device argument
# If device is GPU, check if render device exists
# If it exists, set to GPU-DEVICE
# If it doesn't exist, set to DEFAULT
# Else, set to DEFAULT
# If device is not mentioned, set to DEFAULT
if [ "$DEVICE" == "gpu" ]; then
    # Check if render device exists
    if compgen -G "/dev/dri/render*" > /dev/null; then
        echo "GPU rendering device found. Getting the GID..."
        export RENDER_DEVICE_GID=$(stat -c "%g" /dev/dri/render* | head -n 1)
        PROFILES="GPU-DEVICE"
    else
        echo -e "No GPU rendering device found. \nSwitching to CPU processing..."
    fi
fi

# Export other environment variables
export HOST_IP=$(hostname -I | awk '{print $1}')
export GID=$(id -g ${USER})
export HF_ACCESS_TOKEN="${HUGGINGFACEHUB_API_TOKEN}"
export EMBEDDING_MODEL_ID="BAAI/bge-small-en-v1.5"
export LLM_MODEL_ID="Intel/neural-chat-7b-v3-3"
export RERANKER_MODEL_ID="BAAI/bge-reranker-base"
export MODEL_CACHE_PATH="$MODEL_CACHE_PATH"
export APP_BACKEND_URL="http://$HOST_IP:8888"
export COMPOSE_PROFILES=$PROFILES