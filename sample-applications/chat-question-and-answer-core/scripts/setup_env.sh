#!/bin/bash

# This script sets up the environment for the Chat Question and Answer Core application.
# It accepts two optional parameters:
# -p or --path: Specify the model cache path (default is /tmp/model_cache/)
# -d or --device: Specify the device (default is cpu)
# Usage:
# ./setup_env.sh
# OR
# ./setup_env.sh -p /path/to/model_cache -d gpu

# GPUs currently tested:
# - Arc A770 dGPU
# - Battlemage G21 dGPU
# - Arrowlake iGPU

# Default values
MODEL_CACHE_PATH="/home/${USER}/model_cache/"
DEVICE="CPU"
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

# Convert DEVICE to uppercase to handle both uppercase and lowercase inputs
DEVICE=$(echo "$DEVICE" | tr '[:lower:]' '[:upper:]')
# Check if DEVICE value is valid
if [[ "$DEVICE" != "CPU" && "$DEVICE" != "GPU" ]]; then
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
        mkdir -p "$MODEL_CACHE_PATH"
    fi
else
    # If it doesn't exist, create it
    echo "$MODEL_CACHE_PATH does not exist. Creating it..."
    mkdir -p "$MODEL_CACHE_PATH"
fi


# Export environment variables
# Set COMPOSE_PROFILES based on device argument
# If device is GPU, check if render device exists
# If it exists, set to GPU-DEVICE
# If it doesn't exist, set to DEFAULT
# Else, set to DEFAULT
# If device is not mentioned, set to DEFAULT
if [ "$DEVICE" == "GPU" ]; then
    # Check if render device exists
    if compgen -G "/dev/dri/render*" > /dev/null; then
        echo "GPU rendering device found. Getting the GID..."
        export RENDER_DEVICE_GID=$(stat -c "%g" /dev/dri/render* | head -n 1)
        PROFILES="GPU-DEVICE"
    else
        echo -e "No GPU rendering device found. \nSwitching to CPU processing..."
    fi
fi

export USER_GROUP_ID=$(id -g ${USER})
export HF_ACCESS_TOKEN="${HUGGINGFACEHUB_API_TOKEN}"
export MODEL_CACHE_PATH="$MODEL_CACHE_PATH"

export APP_BACKEND_URL="/v1/chatqna"
export COMPOSE_PROFILES=$PROFILES
