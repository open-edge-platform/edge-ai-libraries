#!/bin/bash
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

BACKENDS=(vdms milvus pgvector faiss)

usage() {
    cat <<'EOF'
Build vector-retriever backend-flavored Docker images.

Usage:
    ./build.sh
    ./build.sh --backend <name> [--backend <name> ...]

Supported backends:
    vdms, milvus, pgvector, faiss

Environment variables:
    REGISTRY_URL Optional registry host/prefix
    PROJECT_NAME Optional project namespace appended to REGISTRY_URL
    TAG          Image tag (default: latest)

Examples:
    ./build.sh
    TAG=dev ./build.sh --backend pgvector
    REGISTRY_URL=my-registry.local PROJECT_NAME=my-team TAG=v1 ./build.sh --backend faiss --backend milvus
EOF
}

contains_backend() {
    local candidate="$1"
    local item
    for item in "${BACKENDS[@]}"; do
        if [[ "$item" == "$candidate" ]]; then
            return 0
        fi
    done
    return 1
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

selected_backends=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help)
            usage
            exit 0
            ;;
        --backend)
            if [[ $# -lt 2 ]]; then
                echo "Error: --backend requires a value." >&2
                usage
                exit 1
            fi
            selected_backends+=("$2")
            shift 2
            ;;
        *)
            if contains_backend "$1"; then
                echo "Error: backend '$1' must be passed with --backend." >&2
                echo "Example: ./build.sh --backend $1" >&2
            else
                echo "Error: unknown argument '$1'." >&2
            fi
            usage
            exit 1
            ;;
    esac
done

if [[ ${#selected_backends[@]} -eq 0 ]]; then
    selected_backends=("${BACKENDS[@]}")
fi

TAG="${TAG:-latest}"
REGISTRY_URL="${REGISTRY_URL:-}"
PROJECT_NAME="${PROJECT_NAME:-}"

if [[ -n "$REGISTRY_URL" ]]; then
    REGISTRY_URL="${REGISTRY_URL%/}/"
fi
if [[ -n "$PROJECT_NAME" ]]; then
    PROJECT_NAME="${PROJECT_NAME%/}/"
fi

REGISTRY_PREFIX="${REGISTRY_URL}${PROJECT_NAME}"

if [[ -n "$REGISTRY_PREFIX" && "${REGISTRY_PREFIX: -1}" != "/" ]]; then
    REGISTRY_PREFIX="${REGISTRY_PREFIX}/"
fi

validated_backends=()
for backend in "${selected_backends[@]}"; do
    if ! contains_backend "$backend"; then
        echo "Error: unsupported backend '$backend'. Supported: ${BACKENDS[*]}" >&2
        exit 1
    fi
    validated_backends+=("$backend")
done

echo "Building vector-retriever images with TAG=${TAG}"
if [[ -n "$REGISTRY_PREFIX" ]]; then
    echo "Using registry prefix from REGISTRY_URL/PROJECT_NAME: ${REGISTRY_PREFIX}"
else
    echo "Using local image names (no registry prefix)."
fi

for backend in "${validated_backends[@]}"; do
    image_name="${REGISTRY_PREFIX}vector-retriever-${backend}:${TAG}"
    echo ""
    echo "==> Building ${image_name}"
    docker build \
        -f docker/Dockerfile \
        --build-arg "RETRIEVER_BACKEND=${backend}" \
        -t "${image_name}" \
        .
done

echo ""
echo "Build complete for backends: ${validated_backends[*]}"