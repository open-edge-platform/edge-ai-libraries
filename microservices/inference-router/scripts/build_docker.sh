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
  --with-compressor    Include adaptive-token-compressor in image
  --without-compressor Build image without adaptive-token-compressor (default)
  -h, --help           Show this help message

Environment variable fallbacks:
  IMAGE_NAME, IMAGE_TAG, INSTALL_COMPRESSOR, COMPRESSOR_REPO, COMPRESSOR_REF
  HTTP_PROXY/http_proxy, HTTPS_PROXY/https_proxy, NO_PROXY/no_proxy
    are forwarded to the build as --build-arg if set.
EOF
}

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

IMAGE_NAME="${IMAGE_NAME:-inference-router}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
NO_CACHE="false"
INSTALL_COMPRESSOR="${INSTALL_COMPRESSOR:-false}"

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
    --with-compressor)
      INSTALL_COMPRESSOR="true"
      shift
      ;;
    --without-compressor)
      INSTALL_COMPRESSOR="false"
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

COMPRESSOR_REPO="${COMPRESSOR_REPO:-https://github.com/open-edge-platform/edge-ai-libraries.git}"
COMPRESSOR_REF="${COMPRESSOR_REF:-release/2026.2}"
COMPRESSOR_SUBDIR="${COMPRESSOR_SUBDIR:-libraries/adaptive-token-compressor}"
VENDOR_DIR="${ROOT_DIR}/vendor/adaptive-token-compressor"

if [[ "${INSTALL_COMPRESSOR}" == "true" ]]; then
  echo "Vendoring adaptive-token-compressor (${COMPRESSOR_REF}) into ${VENDOR_DIR}"
  rm -rf "${VENDOR_DIR}"
  if [[ -n "${COMPRESSOR_SUBDIR}" ]]; then
    # Library lives inside a larger monorepo; fetch only its subdirectory.
    TMP_CLONE="$(mktemp -d)"
    git clone --depth 1 --branch "${COMPRESSOR_REF}" --filter=blob:none --sparse \
      "${COMPRESSOR_REPO}" "${TMP_CLONE}"
    git -C "${TMP_CLONE}" sparse-checkout set --no-cone "${COMPRESSOR_SUBDIR}"
    if [[ ! -d "${TMP_CLONE}/${COMPRESSOR_SUBDIR}" ]]; then
      echo "Error: ${COMPRESSOR_SUBDIR} not found in ${COMPRESSOR_REPO}" >&2
      rm -rf "${TMP_CLONE}"
      exit 1
    fi
    mkdir -p "$(dirname "${VENDOR_DIR}")"
    mv "${TMP_CLONE}/${COMPRESSOR_SUBDIR}" "${VENDOR_DIR}"
    rm -rf "${TMP_CLONE}"
  else
    git clone --depth 1 --branch "${COMPRESSOR_REF}" "${COMPRESSOR_REPO}" "${VENDOR_DIR}"
    rm -rf "${VENDOR_DIR}/.git"
  fi
else
  rm -rf "${VENDOR_DIR}"
  mkdir -p "${VENDOR_DIR}"
  echo "Skipping adaptive-token-compressor vendoring (INSTALL_COMPRESSOR=${INSTALL_COMPRESSOR})"
fi

IMAGE_REF="${IMAGE_NAME}:${IMAGE_TAG}"

BUILD_CMD=(
  docker build
  --file "${ROOT_DIR}/Dockerfile"
  --tag "${IMAGE_REF}"
  --build-arg "INSTALL_COMPRESSOR=${INSTALL_COMPRESSOR}"
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

echo "Building Docker image: ${IMAGE_REF} (INSTALL_COMPRESSOR=${INSTALL_COMPRESSOR})"
"${BUILD_CMD[@]}"

echo "Build complete: ${IMAGE_REF}"
