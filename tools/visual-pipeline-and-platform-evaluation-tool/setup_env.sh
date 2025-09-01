#!/bin/bash

# This script sets up the environment for the Visual Pipeline and Platform Evaluation Tool.
# It accepts one optional parameter:
# -d or --device: Specify the device (default is cpu)
# Usage:
# ./setup_env.sh
# OR
# ./setup_env.sh -d gpu

# Default values
DEVICE="CPU"
PROFILE="CPU"

# Parse named arguments using getopts
# -d for DEVICE
while [[ "$#" -gt 0 ]]; do
    case $1 in
        -d|--device) DEVICE="$2"; shift ;;
        *)
            echo "Unknown parameter passed: $1"
            echo "Accepted parameters are:"
            echo "  -d  --device : Specify the device"
            return 1
            ;;
    esac
    shift
done

# Convert DEVICE to uppercase to handle both uppercase and lowercase inputs
DEVICE=$(echo "$DEVICE" | tr '[:lower:]' '[:upper:]')
# Check if DEVICE value is valid
if [[ "$DEVICE" != "CPU" && "$DEVICE" != "GPU" && "$DEVICE" != "NPU" ]]; then
    echo "Error: Invalid device value '$DEVICE'. Valid values are 'cpu' or 'gpu' or 'npu'."
    return 1
fi

# Export environment variables based on the specified device
case "$DEVICE" in
  GPU)
    # Check if GPU rendering device exists
    if compgen -G "/dev/dri/render*" > /dev/null; then
        echo "GPU rendering device found. Getting the GID..."
        export RENDER_GROUP_ID=$(getent group render | awk -F: '{printf "%s\n", $3}')
        PROFILE="gpu"
    else
        echo -e "No GPU rendering device found. \nSwitching to CPU processing..."
        PROFILE="cpu"
    fi
    ;;
  NPU)
    # Check if NPU rendering device exists
    if compgen -G "/dev/accel*" > /dev/null; then
        echo "NPU rendering device found. Getting the GID..."
        export RENDER_GROUP_ID=$(getent group render | awk -F: '{printf "%s\n", $3}')
        PROFILE="npu"
    else
        echo -e "No NPU rendering device found. \nSwitching to CPU processing..."
        PROFILE="cpu"
    fi
    ;;
  CPU)
    echo "CPU processing configured."
    PROFILE="cpu"
    ;;
esac

export COMPOSE_PROFILES=$PROFILE
export DEVICE_TYPE=$DEVICE
