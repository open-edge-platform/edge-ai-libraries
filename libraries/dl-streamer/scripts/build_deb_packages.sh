#!/bin/bash
# ==============================================================================
# Copyright (C) 2025 Intel Corporation
#
# SPDX-License-Identifier: MIT
# ==============================================================================

set -e

# === CONFIG ===
IMAGE_NAME="$1"
CONTAINER_NAME="temp_extract_container"
DEBS_DESTINATION_PATH="./deb_packages"

# === USAGE ===
if [[ -z "$IMAGE_NAME" ]]; then
    echo "Usage: $0 <docker_image_with_debs>"
    exit 1
fi

# === RUN CONTAINER AND COPY FILES ===
echo "Creating container from image: $IMAGE_NAME"
docker create --name "$CONTAINER_NAME" "$IMAGE_NAME" bash

echo "Copying .deb packages from container to host..."
mkdir -p "$DEBS_DESTINATION_PATH"
docker cp "$CONTAINER_NAME:/intel-dlstreamer*.deb" "$DEBS_DESTINATION_PATH" 2>/dev/null || {
    echo "No matching .deb files found. Exiting."
    docker rm "$CONTAINER_NAME" >/dev/null
    exit 1
}

echo "Cleaning up..."
docker rm "$CONTAINER_NAME" >/dev/null

# === VERIFY .deb PACKAGES ===
echo "Verifying if .deb packages were successfully extracted..."
if ! compgen -G "$DEBS_DESTINATION_PATH/*.deb" > /dev/null; then
    echo "❌ No .deb packages found in $DEBS_DESTINATION_PATH"
    exit 1
fi

echo "✅ Extracted .deb packages to $DEBS_DESTINATION_PATH:"
ls -lh "$DEBS_DESTINATION_PATH"

