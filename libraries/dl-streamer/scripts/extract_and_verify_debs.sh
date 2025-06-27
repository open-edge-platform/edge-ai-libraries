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

if ! docker exec "$CONTAINER_NAME" sh -c 'compgen -G "/debs/*.deb" > /dev/null'; then
    echo "❌ No .deb files found in /debs inside the container"
    docker rm -f "$CONTAINER_NAME"
    exit 1
fi

echo "Copying files from container to host..."
mkdir -p "$DEBS_DESTINATION_PATH"
docker cp "$CONTAINER_NAME:/debs/." "$DEBS_DESTINATION_PATH"
echo "Cleaning up container..."
docker rm "$CONTAINER_NAME"
echo "Finished."
echo "Packages available in $DEBS_DESTINATION_PATH:"
ls "$DEBS_DESTINATION_PATH"

# === VERIFY .deb PACKAGES ===
echo "Verifying if .deb packages were successfully extracted..."
if ! compgen -G "$DEBS_DESTINATION_PATH/*.deb" > /dev/null; then
    echo "❌ No .deb packages found in $DEBS_DESTINATION_PATH"
    exit 1
fi

echo "✅ Extracted .deb packages to $DEBS_DESTINATION_PATH:"
ls -lh "$DEBS_DESTINATION_PATH"
