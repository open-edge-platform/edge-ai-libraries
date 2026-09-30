#!/usr/bin/env bash
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

usage() {
  cat <<EOF
Build the Inference Router Docker image.

Usage:
  ./scripts/build_docker.sh [options]

The adaptive-token-compressor library is a baked-in dependency: the Dockerfile
fetches and installs it during the build, so `docker build .` works on its own.
This script is just a convenience wrapper around `docker build`.

Options:
  --image <name>       Image name (default: inference-router)
  --tag <tag>          Image tag (default: latest)
  --no-cache           Build without cache
  -h, --help           Show this help message

Environment variables (forwarded to the build as --build-arg if set):
  IMAGE_NAME, IMAGE_TAG                       image reference
  COMPRESSOR_REPO, COMPRESSOR_REF, COMPRESSOR_SUBDIR
                                              override the compressor source
  HTTP_PROXY/http_proxy, HTTPS_PROXY/https_proxy, NO_PROXY/no_proxy
                                              proxy settings
EOF
}

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

IMAGE_NAME="${IMAGE_NAME:-inference-router}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
NO_CACHE="false"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --image)
      IMAGE_NAME="$2"
      shift 2
      ;;
    --tag)
      IMAGE_TAG="$2"
      shift 2
      ;;
    --no-cache)
      NO_CACHE="true"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 1
      ;;
  esac
done

HTTP_PROXY_VAL="${HTTP_PROXY:-${http_proxy:-}}"
HTTPS_PROXY_VAL="${HTTPS_PROXY:-${https_proxy:-}}"
NO_PROXY_VAL="${NO_PROXY:-${no_proxy:-}}"

IMAGE_REF="${IMAGE_NAME}:${IMAGE_TAG}"

# The Dockerfile is self-contained: it fetches (vendors) the
# adaptive-token-compressor source itself. This script only wraps `docker build`
# with the usual conveniences (tagging, proxy/override forwarding).
BUILD_CMD=(
  docker build
  --file "${ROOT_DIR}/Dockerfile"
  --tag "${IMAGE_REF}"
)

if [[ "${NO_CACHE}" == "true" ]]; then
  BUILD_CMD+=(--no-cache)
fi

# Forward compressor source overrides to the Dockerfile's fetch stage if set.
if [[ -n "${COMPRESSOR_REPO:-}" ]]; then
  BUILD_CMD+=(--build-arg "COMPRESSOR_REPO=${COMPRESSOR_REPO}")
fi

if [[ -n "${COMPRESSOR_REF:-}" ]]; then
  BUILD_CMD+=(--build-arg "COMPRESSOR_REF=${COMPRESSOR_REF}")
fi

if [[ -n "${COMPRESSOR_SUBDIR:-}" ]]; then
  BUILD_CMD+=(--build-arg "COMPRESSOR_SUBDIR=${COMPRESSOR_SUBDIR}")
fi

if [[ -n "${HTTP_PROXY_VAL}" ]]; then
  BUILD_CMD+=(--build-arg "HTTP_PROXY=${HTTP_PROXY_VAL}" --build-arg "http_proxy=${HTTP_PROXY_VAL}")
fi

if [[ -n "${HTTPS_PROXY_VAL}" ]]; then
  BUILD_CMD+=(--build-arg "HTTPS_PROXY=${HTTPS_PROXY_VAL}" --build-arg "https_proxy=${HTTPS_PROXY_VAL}")
fi

if [[ -n "${NO_PROXY_VAL}" ]]; then
  BUILD_CMD+=(--build-arg "NO_PROXY=${NO_PROXY_VAL}" --build-arg "no_proxy=${NO_PROXY_VAL}")
fi

BUILD_CMD+=("${ROOT_DIR}")

echo "Building Docker image: ${IMAGE_REF}"
"${BUILD_CMD[@]}"

echo "Build complete: ${IMAGE_REF}"
