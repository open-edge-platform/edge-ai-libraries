#!/bin/bash

# This script automatically detects the available device (NPU, GPU, or CPU)
# and writes COMPOSE_PROFILES, RENDER_GROUP_ID, and DOCKER_TAG to the .env file.

VERSION=2025.2.0
COMPOSE_PROFILES=""
RENDER_GROUP_ID=""

# Check for NPU device
if compgen -G "/dev/accel*" > /dev/null; then
    # NPU device found, using NPU profile and render group
    COMPOSE_PROFILES="npu"
    RENDER_GROUP_ID=$(getent group render | awk -F: '{printf "%s\n", $3}')
elif compgen -G "/dev/dri/render*" > /dev/null; then
    # GPU device found, using GPU profile and render group
    COMPOSE_PROFILES="gpu"
    RENDER_GROUP_ID=$(getent group render | awk -F: '{printf "%s\n", $3}')
else
    # No NPU or GPU device found, falling back to CPU
    echo "No GPU or NPU device was found in the system, so only CPU will be used. This may be because the appropriate drivers have not been installed."
    COMPOSE_PROFILES="cpu"
    RENDER_GROUP_ID=""
fi

# Write variables to .env file
cat > .env <<EOF
COMPOSE_PROFILES=${COMPOSE_PROFILES}
RENDER_GROUP_ID=${RENDER_GROUP_ID}
DOCKER_TAG=${VERSION}
EOF
