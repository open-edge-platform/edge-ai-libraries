#!/usr/bin/env bash
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
BUILD_CONTEXT="$(cd "${REPO_ROOT}/.." && pwd)"
DOCKERFILE_PATH="${SCRIPT_DIR}/docker/Dockerfile"

IMAGE_NAME="${IMAGE_NAME:-kv-quant-offload-vllm-xpu:latest}"
CONTAINER_NAME="vllm-kvweave"
MODEL_PATH="${MODEL_PATH:-/models}"
MODEL="${MODEL:-Qwen3.5-9B}"
SERVE="${SERVE:-${MODEL}}"
TP="${TP:-1}"
GPU_MEM_UTIL="${GPU_MEM_UTIL:-0.86}"
MAX_MODEL_LEN="${MAX_MODEL_LEN:-8192}"
HOST_PORT="${HOST_PORT:-8000}"
LMCACHE_MP_PORT="${LMCACHE_MP_PORT:-6555}"
LMCACHE_MP_HTTP_PORT="${LMCACHE_MP_HTTP_PORT:-8090}"
LMCACHE_MP_L1_SIZE_GB="${LMCACHE_MP_L1_SIZE_GB:-5}"
FORCE_BUILD="${FORCE_BUILD:-0}"
DOCKER_BUILD_OPTS="${DOCKER_BUILD_OPTS:-}"
DOCKER_RUN_OPTS="${DOCKER_RUN_OPTS:-}"
BUILD_ARGS=()

usage() {
  cat <<'EOF'
Usage:
  bash integration/lmcache/vllm/vllm-start.sh

Optional environment variables:
  IMAGE_NAME            Built image tag. Default: kv-quant-offload-vllm-xpu:latest
  MODEL_PATH            Host model directory mounted at /models. Default: /models
  MODEL                 Model path/name under /models and vLLM model arg. Default: Qwen3.5-9B
  SERVE                 Served model name. Default: same as MODEL
  TP                    Tensor parallel size. Default: 1
  GPU_MEM_UTIL          vLLM gpu-memory-util. Default: 0.86
  MAX_MODEL_LEN         vLLM max model len. Default: 8192
  HOST_PORT             Host/container API port. Default: 8000
  LMCACHE_MP_PORT       LMCache MP port. Default: 6555
  LMCACHE_MP_HTTP_PORT  LMCache MP HTTP port. Default: 8090
  LMCACHE_MP_L1_SIZE_GB LMCache L1 size. Default: 5
  FORCE_BUILD           Rebuild even if IMAGE_NAME already exists. Default: 0
  DOCKER_BUILD_OPTS     Extra args appended to docker build
  DOCKER_RUN_OPTS       Extra args appended to docker run

Examples:
  MODEL_PATH=/data/models MODEL=Qwen3.5-9B bash integration/lmcache/vllm/vllm-start.sh
  IMAGE_NAME=kv-quant-offload-vllm:dev HOST_PORT=18000 bash integration/lmcache/vllm/vllm-start.sh
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ ! -f "${DOCKERFILE_PATH}" ]]; then
  echo "ERROR: Dockerfile not found at ${DOCKERFILE_PATH}" >&2
  exit 1
fi

if [[ ! -d "${MODEL_PATH}" ]]; then
  echo "ERROR: MODEL_PATH does not exist: ${MODEL_PATH}" >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker is not installed or not in PATH" >&2
  exit 1
fi

if ! docker image inspect "${IMAGE_NAME}" >/dev/null 2>&1 || [[ "${FORCE_BUILD}" == "1" ]]; then
  for proxy_var in http_proxy https_proxy HTTP_PROXY HTTPS_PROXY no_proxy NO_PROXY; do
    if [[ -n "${!proxy_var:-}" ]]; then
      BUILD_ARGS+=( --build-arg "${proxy_var}=${!proxy_var}" )
    fi
  done

  if [[ ${#BUILD_ARGS[@]} -eq 0 ]]; then
    echo "WARNING: no proxy environment variables detected for docker build; network-restricted hosts may fail to download dependencies" >&2
  fi

  echo "Building image ${IMAGE_NAME}"
  docker build \
    --no-cache \
    -f "${DOCKERFILE_PATH}" \
    -t "${IMAGE_NAME}" \
    "${BUILD_ARGS[@]}" \
    ${DOCKER_BUILD_OPTS} \
    "${BUILD_CONTEXT}"
else
  echo "Using existing image ${IMAGE_NAME}"
fi

echo "Removing any existing container named ${CONTAINER_NAME}"
docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true

echo "Starting container ${CONTAINER_NAME}"

# The image runs vLLM/LMCache as a non-root user, so it needs supplementary
# group membership matching the host's render/video group GIDs to access
# /dev/dri (GIDs vary per host, so they can't be baked into the image).
GROUP_ADD_OPTS=()
RENDER_GID="$(stat -c '%g' /dev/dri/renderD* 2>/dev/null | head -n1 || true)"
VIDEO_GID="$(stat -c '%g' /dev/dri/card* 2>/dev/null | head -n1 || true)"
[[ -n "${RENDER_GID}" ]] && GROUP_ADD_OPTS+=( --group-add "${RENDER_GID}" )
[[ -n "${VIDEO_GID}" ]] && GROUP_ADD_OPTS+=( --group-add "${VIDEO_GID}" )

docker run -d \
  --name "${CONTAINER_NAME}" \
  --ipc=host \
  --privileged \
  --device=/dev/dri \
  "${GROUP_ADD_OPTS[@]}" \
  --shm-size=16g \
  -v "${MODEL_PATH}:/models:ro" \
  -e LMCACHE_MP_HOST="tcp://127.0.0.1" \
  -e MODEL="/models/${MODEL}" \
  -e SERVE="${SERVE}" \
  -e TP="${TP}" \
  -e GPU_MEM_UTIL="${GPU_MEM_UTIL}" \
  -e MAX_MODEL_LEN="${MAX_MODEL_LEN}" \
  -e LMCACHE_MP_PORT="${LMCACHE_MP_PORT}" \
  -e LMCACHE_MP_HTTP_PORT="${LMCACHE_MP_HTTP_PORT}" \
  -e LMCACHE_MP_L1_SIZE_GB="${LMCACHE_MP_L1_SIZE_GB}" \
  -e http_proxy \
  -e https_proxy \
  -e HTTP_PROXY \
  -e HTTPS_PROXY \
  -e no_proxy="localhost,127.0.0.1" \
  -p "${HOST_PORT}:8000" \
  -p "${LMCACHE_MP_PORT}:${LMCACHE_MP_PORT}" \
  -p "${LMCACHE_MP_HTTP_PORT}:${LMCACHE_MP_HTTP_PORT}" \
  ${DOCKER_RUN_OPTS} \
  "${IMAGE_NAME}" \
  /usr/local/bin/start-lmcache-vllm.sh

echo "Container ${CONTAINER_NAME} started"
echo "vLLM API: http://127.0.0.1:${HOST_PORT}/v1"
echo "LMCache health: http://127.0.0.1:${LMCACHE_MP_HTTP_PORT}/healthcheck"
echo "Logs: docker logs -f ${CONTAINER_NAME}"