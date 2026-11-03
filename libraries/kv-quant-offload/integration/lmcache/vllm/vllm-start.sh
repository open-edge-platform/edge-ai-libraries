#!/usr/bin/env bash
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
BUILD_CONTEXT="${REPO_ROOT}"
DOCKERFILE_PATH="${SCRIPT_DIR}/docker/Dockerfile"

IMAGE_NAME="${IMAGE_NAME:-kv-quant-offload-vllm-xpu:latest}"
CONTAINER_NAME="vllm-kvweave"
MODEL_PATH="${MODEL_PATH:-/models}"
MODEL="${MODEL:-Qwen3.5-9B}"
SERVE="${SERVE:-${MODEL}}"
TP="${TP:-1}"
GPU_MEM_UTIL="${GPU_MEM_UTIL:-0.8}"
MAX_MODEL_LEN="${MAX_MODEL_LEN:-8192}"
DTYPE="${DTYPE:-float16}"
QUANTIZATION="${QUANTIZATION:-fp8}"
DEBUG="${DEBUG:-False}"
HOST_BIND_ADDRESS="${HOST_BIND_ADDRESS:-127.0.0.1}"
HOST_PORT="${HOST_PORT:-8000}"
LMCACHE_MP_HOST="${LMCACHE_MP_HOST:-tcp://localhost}"
LMCACHE_MP_PORT="${LMCACHE_MP_PORT:-6555}"
LMCACHE_MP_HTTP_PORT="${LMCACHE_MP_HTTP_PORT:-8090}"
LMCACHE_MP_MQ_TIMEOUT="${LMCACHE_MP_MQ_TIMEOUT:-600}"
LMCACHE_MP_HEARTBEAT_INTERVAL="${LMCACHE_MP_HEARTBEAT_INTERVAL:-15}"
LMCACHE_MP_L1_SIZE_GB="${LMCACHE_MP_L1_SIZE_GB:-5}"
LMCACHE_MP_L2_ENABLE="${LMCACHE_MP_L2_ENABLE:-true}"
LMCACHE_MP_EVICTION_POLICY="${LMCACHE_MP_EVICTION_POLICY:-LRU}"
LMCACHE_MP_SUPPORTED_TRANSFER_MODE="${LMCACHE_MP_SUPPORTED_TRANSFER_MODE:-auto}"
LMCACHE_MP_SHM_NAME="${LMCACHE_MP_SHM_NAME:-lmcache_l1_pool_server}"
LMCACHE_MP_EVICTION_TRIGGER_WATERMARK="${LMCACHE_MP_EVICTION_TRIGGER_WATERMARK:-0.7}"
LMCACHE_MP_EVICTION_RATIO="${LMCACHE_MP_EVICTION_RATIO:-0.3}"
LMCACHE_MP_TRANSFER_MODE="${LMCACHE_MP_TRANSFER_MODE:-engine_driven}"
LMCACHE_MP_L1_KVWEAVE_QUANT="${LMCACHE_MP_L1_KVWEAVE_QUANT:-1}"
LMCACHE_MP_KVWEAVE_QUANT_DEVICE="${LMCACHE_MP_KVWEAVE_QUANT_DEVICE:-xpu}"
LMCACHE_MP_KVWEAVE_QBIT="${LMCACHE_MP_KVWEAVE_QBIT:-4}"
LMCACHE_MP_KVWEAVE_SCALING_METHOD="${LMCACHE_MP_KVWEAVE_SCALING_METHOD:-per_channel}"
LMCACHE_MP_KVWEAVE_RH="${LMCACHE_MP_KVWEAVE_RH:-1}"
LMCACHE_MP_KVWEAVE_ASYM="${LMCACHE_MP_KVWEAVE_ASYM:-1}"
LMCACHE_MP_KVWEAVE_PRECOND="${LMCACHE_MP_KVWEAVE_PRECOND:-1}"
LMCACHE_MP_KVWEAVE_LINEAR_QUANT_ENABLED="${LMCACHE_MP_KVWEAVE_LINEAR_QUANT_ENABLED:-1}"
LMCACHE_MP_KVWEAVE_LINEAR_MAX_SIZE_RATIO="${LMCACHE_MP_KVWEAVE_LINEAR_MAX_SIZE_RATIO:-1.20}"
LMCACHE_MP_KVWEAVE_LINEAR_RH="${LMCACHE_MP_KVWEAVE_LINEAR_RH:-1}"
LMCACHE_MP_KVWEAVE_LINEAR_ASYM="${LMCACHE_MP_KVWEAVE_LINEAR_ASYM:-0}"
LMCACHE_MP_KVWEAVE_CONV_QUANT_ENABLED="${LMCACHE_MP_KVWEAVE_CONV_QUANT_ENABLED:-1}"
LMCACHE_MP_KVWEAVE_CONV_SCALING_METHOD="${LMCACHE_MP_KVWEAVE_CONV_SCALING_METHOD:-per_token}"
LMCACHE_MP_KVWEAVE_CONV_RH="${LMCACHE_MP_KVWEAVE_CONV_RH:-0}"
LMCACHE_MP_KVWEAVE_CONV_QBIT="${LMCACHE_MP_KVWEAVE_CONV_QBIT:-4}"
LMCACHE_MP_KVWEAVE_SSM_QUANT_ENABLED="${LMCACHE_MP_KVWEAVE_SSM_QUANT_ENABLED:-1}"
LMCACHE_MP_KVWEAVE_SSM_SCALING_METHOD="${LMCACHE_MP_KVWEAVE_SSM_SCALING_METHOD:-per_token}"
LMCACHE_MP_KVWEAVE_SSM_RH="${LMCACHE_MP_KVWEAVE_SSM_RH:-0}"
LMCACHE_MP_KVWEAVE_SSM_QBIT="${LMCACHE_MP_KVWEAVE_SSM_QBIT:-4}"
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
  GPU_MEM_UTIL          vLLM gpu-memory-util. Default: 0.7
  MAX_MODEL_LEN         vLLM max model len. Default: 12000
  DTYPE                vLLM data type. Default: float16
  QUANTIZATION         vLLM quantization method. Default: fp8
  KV_CACHE_MEMORY_BYTES vLLM kv-cache-memory-bytes. Default: 2G
  VLLM_INITIAL_BLOCK_SIZE Initial block size passed to calc_vllm_block_size.py. Default: 64
  DEBUG                Enable VLLM_SERVER_DEV_MODE. Default: False
  VLLM_BLOCK_SIZE_OVERRIDE Force LMCache --chunk-size, vLLM --block-size and max_num_batched_tokens (e.g. 256 for dense models). Default: calculated
  MAX_NUM_BATCHED_TOKENS vLLM max_num_batched_tokens. Default: block size
  HOST_BIND_ADDRESS    Host address for published container ports. Default: 127.0.0.1
  HOST_PORT             Host/container API port. Default: 8000
  LMCACHE_MP_HOST       LMCache MP host URI inside the container. Default: tcp://localhost
  LMCACHE_MP_PORT       LMCache MP port. Default: 6555
  LMCACHE_MP_HTTP_PORT  LMCache MP HTTP port. Default: 8090
  LMCACHE_MP_MQ_TIMEOUT LMCache MP message timeout in seconds. Default: 600
  LMCACHE_MP_HEARTBEAT_INTERVAL LMCache MP heartbeat interval in seconds. Default: 15
  LMCACHE_MP_L1_SIZE_GB LMCache L1 size. Default: 15
  LMCACHE_MP_L2_ENABLE  Enable LMCache L2 filesystem adapter. Default: false
  LMCACHE_MP_EVICTION_POLICY  L1 eviction policy. Default: LRU
  LMCACHE_MP_SUPPORTED_TRANSFER_MODE  LMCache server transfer mode. Default: auto
  LMCACHE_MP_SHM_NAME   LMCache server shared-memory pool name. Default: lmcache_l1_pool_server
  LMCACHE_MP_EVICTION_TRIGGER_WATERMARK  L1 eviction trigger watermark. Default: 0.7
  LMCACHE_MP_EVICTION_RATIO              L1 eviction ratio. Default: 0.3
  LMCACHE_MP_KVWEAVE_QBIT Attention quantization bit width. Default: 4
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

# Ensure the L2 disk cache dir exists and is writable by the container's
# non-root user (UID 1000); otherwise a root-owned auto-created bind mount
# causes PermissionError inside the container.
mkdir -p "${MODEL_PATH}/lmcache_disk"
chmod 1777 "${MODEL_PATH}/lmcache_disk"

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
  -v "${MODEL_PATH}/lmcache_disk:/lmcache_disk" \
  -e LMCACHE_MP_HOST="tcp://127.0.0.1" \
  -e MODEL="/models/${MODEL}" \
  -e SERVE="${SERVE}" \
  -e TP="${TP}" \
  -e GPU_MEM_UTIL="${GPU_MEM_UTIL}" \
  -e MAX_MODEL_LEN="${MAX_MODEL_LEN}" \
  -e DTYPE="${DTYPE}" \
  -e QUANTIZATION="${QUANTIZATION}" \
  -e DEBUG="${DEBUG}" \
  -e VLLM_BLOCK_SIZE_OVERRIDE \
  -e MAX_NUM_BATCHED_TOKENS \
  -e LMCACHE_MP_HOST="${LMCACHE_MP_HOST}" \
  -e LMCACHE_MP_PORT="${LMCACHE_MP_PORT}" \
  -e LMCACHE_MP_HTTP_PORT="${LMCACHE_MP_HTTP_PORT}" \
  -e LMCACHE_MP_MQ_TIMEOUT="${LMCACHE_MP_MQ_TIMEOUT}" \
  -e LMCACHE_MP_HEARTBEAT_INTERVAL="${LMCACHE_MP_HEARTBEAT_INTERVAL}" \
  -e LMCACHE_MP_L1_SIZE_GB="${LMCACHE_MP_L1_SIZE_GB}" \
  -e LMCACHE_MP_L2_ENABLE="${LMCACHE_MP_L2_ENABLE}" \
  -e LMCACHE_MP_EVICTION_POLICY="${LMCACHE_MP_EVICTION_POLICY}" \
  -e LMCACHE_MP_SUPPORTED_TRANSFER_MODE="${LMCACHE_MP_SUPPORTED_TRANSFER_MODE}" \
  -e LMCACHE_MP_SHM_NAME="${LMCACHE_MP_SHM_NAME}" \
  -e LMCACHE_MP_EVICTION_TRIGGER_WATERMARK="${LMCACHE_MP_EVICTION_TRIGGER_WATERMARK}" \
  -e LMCACHE_MP_EVICTION_RATIO="${LMCACHE_MP_EVICTION_RATIO}" \
  -e LMCACHE_MP_TRANSFER_MODE="${LMCACHE_MP_TRANSFER_MODE}" \
  -e LMCACHE_MP_L1_KVWEAVE_QUANT="${LMCACHE_MP_L1_KVWEAVE_QUANT}" \
  -e LMCACHE_MP_KVWEAVE_QUANT_DEVICE="${LMCACHE_MP_KVWEAVE_QUANT_DEVICE}" \
  -e LMCACHE_MP_KVWEAVE_QBIT="${LMCACHE_MP_KVWEAVE_QBIT}" \
  -e LMCACHE_MP_KVWEAVE_SCALING_METHOD="${LMCACHE_MP_KVWEAVE_SCALING_METHOD}" \
  -e LMCACHE_MP_KVWEAVE_RH="${LMCACHE_MP_KVWEAVE_RH}" \
  -e LMCACHE_MP_KVWEAVE_ASYM="${LMCACHE_MP_KVWEAVE_ASYM}" \
  -e LMCACHE_MP_KVWEAVE_PRECOND="${LMCACHE_MP_KVWEAVE_PRECOND}" \
  -e LMCACHE_MP_KVWEAVE_LINEAR_QUANT_ENABLED="${LMCACHE_MP_KVWEAVE_LINEAR_QUANT_ENABLED}" \
  -e LMCACHE_MP_KVWEAVE_LINEAR_MAX_SIZE_RATIO="${LMCACHE_MP_KVWEAVE_LINEAR_MAX_SIZE_RATIO}" \
  -e LMCACHE_MP_KVWEAVE_LINEAR_RH="${LMCACHE_MP_KVWEAVE_LINEAR_RH}" \
  -e LMCACHE_MP_KVWEAVE_LINEAR_ASYM="${LMCACHE_MP_KVWEAVE_LINEAR_ASYM}" \
  -e LMCACHE_MP_KVWEAVE_CONV_QUANT_ENABLED="${LMCACHE_MP_KVWEAVE_CONV_QUANT_ENABLED}" \
  -e LMCACHE_MP_KVWEAVE_CONV_SCALING_METHOD="${LMCACHE_MP_KVWEAVE_CONV_SCALING_METHOD}" \
  -e LMCACHE_MP_KVWEAVE_CONV_RH="${LMCACHE_MP_KVWEAVE_CONV_RH}" \
  -e LMCACHE_MP_KVWEAVE_CONV_QBIT="${LMCACHE_MP_KVWEAVE_CONV_QBIT}" \
  -e LMCACHE_MP_KVWEAVE_SSM_QUANT_ENABLED="${LMCACHE_MP_KVWEAVE_SSM_QUANT_ENABLED}" \
  -e LMCACHE_MP_KVWEAVE_SSM_SCALING_METHOD="${LMCACHE_MP_KVWEAVE_SSM_SCALING_METHOD}" \
  -e LMCACHE_MP_KVWEAVE_SSM_RH="${LMCACHE_MP_KVWEAVE_SSM_RH}" \
  -e LMCACHE_MP_KVWEAVE_SSM_QBIT="${LMCACHE_MP_KVWEAVE_SSM_QBIT}" \
  -e http_proxy \
  -e https_proxy \
  -e HTTP_PROXY \
  -e HTTPS_PROXY \
  -e no_proxy="localhost,127.0.0.1" \
  -p "${HOST_BIND_ADDRESS}:${HOST_PORT}:8000" \
  -p "${HOST_BIND_ADDRESS}:${LMCACHE_MP_PORT}:${LMCACHE_MP_PORT}" \
  -p "${HOST_BIND_ADDRESS}:${LMCACHE_MP_HTTP_PORT}:${LMCACHE_MP_HTTP_PORT}" \
  ${DOCKER_RUN_OPTS} \
  "${IMAGE_NAME}" \
  /usr/local/bin/start-lmcache-vllm.sh

echo "Container ${CONTAINER_NAME} started"
echo "vLLM API: http://127.0.0.1:${HOST_PORT}/v1"
echo "LMCache health: http://127.0.0.1:${LMCACHE_MP_HTTP_PORT}/healthcheck"
echo "Logs: docker logs -f ${CONTAINER_NAME}"