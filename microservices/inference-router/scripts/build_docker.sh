#!/usr/bin/env bash
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

usage() {
  cat <<EOF
Build the Inference Router Docker image.

Usage:
  ./scripts/build_docker.sh [options]

Options:
  --image <name>       Image name (default: inference-router)
  --tag <tag>          Image tag (default: latest)
  --no-cache           Build without cache
  -h, --help           Show this help message

Environment variable fallbacks:
  IMAGE_NAME, IMAGE_TAG
  HTTP_PROXY/http_proxy, HTTPS_PROXY/https_proxy, NO_PROXY/no_proxy
    are forwarded to the build as --build-arg if set.
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

BUILD_CMD=(
  docker build
  --file "${ROOT_DIR}/Dockerfile"
  --tag "${IMAGE_REF}"
)

if [[ "${NO_CACHE}" == "true" ]]; then
  BUILD_CMD+=(--no-cache)
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
