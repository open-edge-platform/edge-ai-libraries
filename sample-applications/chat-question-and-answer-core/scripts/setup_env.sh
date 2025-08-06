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
PROFILES="OPENVINO"
BACKEND="OPENVINO"
BACKEND_HOST="chatqna-core-ov-cpu"

print_help() {
    echo "Usage: source setup.sh [options]"
    echo "Options:"
    echo "  -p, --path <path>       Specify the model cache path"
    echo "  -d, --device <device>   Specify the device"
    echo "  -b, --backend <backend> Specify the backend (openvino or ollama)"
    echo "  -h, --help              Display this help message"
}

# Parse named arguments using getopts
# -p for MODEL_CACHE_PATH
# -d for DEVICE
# -b for BACKEND
while [[ "$#" -gt 0 ]]; do
    case $1 in
        -p|--path) MODEL_CACHE_PATH="$2"; shift ;;
        -d|--device) DEVICE="$2"; shift ;;
        -b|--backend) BACKEND="$2"; shift ;;
        -h|--help)
            print_help
            return 0
            ;;
        *)
            echo "Unknown parameter passed: $1"
            print_help
            return 1
            ;;
    esac
    shift
done


# Convert BACKEND to uppercase to handle both uppercase and lowercase inputs
BACKEND=$(echo "$BACKEND" | tr '[:lower:]' '[:upper:]')
# Check if BACKEND value is valid
if [[ "$BACKEND" != "OPENVINO" && "$BACKEND" != "OLLAMA" ]]; then
    echo "Error: Unsupported backend: '$BACKEND'. Supported backends are 'openvino' or 'ollama'."
    return 1
fi


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


# Set environment variables based on the backend and device
if [ "$BACKEND" == "OPENVINO" ]; then
    if [ "$DEVICE" == "GPU" ]; then
        # Check if render device exists
        if compgen -G "/dev/dri/render*" > /dev/null; then
            echo "GPU rendering device found. Getting the GID..."
            export RENDER_DEVICE_GID=$(stat -c "%g" /dev/dri/render* | head -n 1)
            PROFILES="OPENVINO-GPU"
            BACKEND_HOST="chatqna-core-ov-gpu"
        else
            echo -e "No GPU rendering device found. \nUse CPU processing instead..."
        fi
    fi
elif [ "$BACKEND" == "OLLAMA" ]; then
    PROFILES="OLLAMA"
    BACKEND_HOST="chatqna-core-ollama"
    if [ "$DEVICE" == "GPU" ]; then
        echo -e "Current ollama backend doesn't support GPU. Only CPU is supported."
        echo -e "Use CPU processing..."
    fi
fi

export USER_GROUP_ID=$(id -g ${USER})
export HF_ACCESS_TOKEN="${HUGGINGFACEHUB_API_TOKEN}"
export MODEL_CACHE_PATH="$MODEL_CACHE_PATH"
export APP_BACKEND_URL="/v1/chatqna"
export COMPOSE_PROFILES=$PROFILES
export UI_HOST="chatqna-core-ui"
export BACKEND_HOST=$BACKEND_HOST

# Generate nginx.conf file for docker compose
source ./nginx_config/generate_nginx_conf.sh