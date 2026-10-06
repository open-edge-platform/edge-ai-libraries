#!/usr/bin/env bash

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Build CDI GPU generator binary using Docker (no Go required on host)

set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
OUTPUT_BINARY="$SCRIPT_DIR/intel-cdi-specs-generator-gpu"
TAG="${TAG:-gpu-v0.10.1}"

echo "Building CDI GPU generator using Docker..."
echo "Tag: $TAG"
echo "Output: $OUTPUT_BINARY"

# Build image and extract binary
docker build \
    --build-arg TAG="$TAG" \
    --build-arg http_proxy="${http_proxy:-}" \
    --build-arg https_proxy="${https_proxy:-}" \
    --build-arg no_proxy="${no_proxy:-}" \
    -t cdi-generator-builder:local \
    -f "$SCRIPT_DIR/Dockerfile" \
    "$SCRIPT_DIR"

# Extract binary from image
CONTAINER_ID=$(docker create cdi-generator-builder:local)
docker cp "$CONTAINER_ID:/intel-cdi-specs-generator-gpu" "$OUTPUT_BINARY"
docker rm "$CONTAINER_ID" >/dev/null

# Set permissions
chmod +x "$OUTPUT_BINARY"

echo "Build complete: $OUTPUT_BINARY"
echo "Size: $(du -h "$OUTPUT_BINARY" | cut -f1)"
