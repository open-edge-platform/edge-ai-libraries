# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
# On-device deployment environment: a single vLLM-IPEX serving instance (one
# multimodal model filling BOTH the VLM and LLM roles) plus the
# multilevel-video-understanding microservice, running locally on Intel PTL
# with shared system RAM.
#
# Usage:   source docker/set_env.sh      # before ./setup_docker.sh / docker compose up

# Auto-detect the host IP (used for no_proxy and the model-serving base URLs).
HOST_IP=$(ip route get 1 2>/dev/null | awk '{print $7; exit}')
export no_proxy=localhost,127.0.0.1,vllm-ipex-serving,multilevel-video-understanding,${HOST_IP}

# =========================================================================
# vLLM-IPEX model serving
# =========================================================================
export VIDEO_GROUP_ID=$(getent group video  | awk -F: '{print $3}')
export RENDER_GROUP_ID=$(getent group render | awk -F: '{print $3}')

# Host directory that caches downloaded Hugging Face weights.
HF_HOME=${HF_HOME:=~/models/huggingface}
export HF_HOME

# Model + context window. Qwen3.5-35B-A3B is a Mixture-of-Experts model
# (35B total / 3B active) that serves both the VLM (captioning) and LLM
# (aggregation) roles from a single endpoint.
export LLM_MODEL=Qwen/Qwen3.5-35B-A3B
export MAX_MODEL_LEN=61440            # 60k context; lower (e.g. 32768) to reduce RAM.

# Precision + share of system RAM the serving may reserve.
# fp8 is the default; awq / sym_int4 trade quality for lower memory.
if echo "${LLM_MODEL}" | grep -qi "awq"; then
  export LOAD_QUANTIZATION=awq
  export GPU_MEM_UTIL=0.5
else
  export LOAD_QUANTIZATION=fp8
  export GPU_MEM_UTIL=0.7
fi
export TENSOR_PARALLEL_SIZE=1        # single integrated GPU on PTL
export VLLM_SERVICE_PORT=41091

# =========================================================================
# multilevel-video-understanding microservice
# =========================================================================
export REGISTRY_URL=intel/
export REGISTRY=${REGISTRY_URL}
export TAG=latest
export SERVICE_PORT=8192

# Run multilevel-video-understanding as the host user
# To ensure bind-mount directories (e.g. ~/.cache/...) are available in container
export USER_GROUP_ID="$(id -g "$USER")"

# Both roles are served by the same on-device vLLM-IPEX endpoint. The two
# containers share `app-network`, so the microservice reaches it by service name.
export VLM_BASE_URL=http://vllm-ipex-serving:8000/v1
export LLM_BASE_URL=http://vllm-ipex-serving:8000/v1
export VLM_MODEL_NAME=${LLM_MODEL}
export LLM_MODEL_NAME=${LLM_MODEL}

export MAX_CONCURRENT_REQUESTS=4
export DEFAULT_MAX_TOKENS=512
export ENABLE_THINKING=false
export VIDEO_FRAME_HEIGHT=378
export VIDEO_FRAME_WIDTH=504
export DEFAULT_TEMPERATURE=0.0

# Runtime prompt-registry cache. Must exist as a user-owned dir BEFORE
# `docker compose up`, otherwise Docker creates it as root.
export VIDEO_SUMMARY_CACHE_HOST=${VIDEO_SUMMARY_CACHE_HOST:-${HOME}/.cache/.multilevel-video-understanding}
mkdir -p "${VIDEO_SUMMARY_CACHE_HOST}/tasks"
