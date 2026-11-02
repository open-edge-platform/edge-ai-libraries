# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

FROM intel/omix:0.1.0-devel-ubuntu24.04 AS builder

ARG http_proxy
ARG https_proxy
ARG no_proxy

ENV VIRTUAL_ENV=/opt/buildenv \
    PATH="/root/.local/bin:/opt/buildenv/bin:${PATH}" \
    UV_HTTP_TIMEOUT=500 \
    PIP_EXTRA_INDEX_URL="https://download.pytorch.org/whl/xpu" \
    UV_EXTRA_INDEX_URL="https://download.pytorch.org/whl/xpu" \
    UV_INDEX_STRATEGY="unsafe-best-match" \
    UV_LINK_MODE="copy" \
    VLLM_TARGET_DEVICE=xpu \
    WHEELS=/wheels

SHELL ["bash", "-c"]


# --- build tooling (the oneAPI DPC++ compiler is already in the OMIX devel base) ---
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    apt-get update -y && \
    apt-get install -y --no-install-recommends --fix-missing \
        git curl ca-certificates \
        python3-dev python3-venv python3-pip \
        ninja-build cmake pkg-config numactl

# --- isolated build venv (avoid OMIX system-python PEP 668 block; clean resolution) ---
RUN python3 -m venv ${VIRTUAL_ENV}

# --- uv for fast, deterministic installs ---
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

# --- torch MUST match the runtime base (2.11.0+xpu) so SyclExtension .so files link
#     against the same libtorch ABI the runtime ships (rpath $ORIGIN/../../torch/lib) ---
RUN --mount=type=cache,target=/root/.cache/uv \
    pip install --upgrade pip wheel setuptools && \
    uv pip install torch==2.12.0+xpu torchaudio torchvision \
        --index-url https://download.pytorch.org/whl/xpu

COPY . /src/kvweave

RUN mkdir -p ${WHEELS}

# 1a Build KVWeave wheel
RUN --mount=type=cache,target=/root/.cache/uv \
    set -eo pipefail && \
    source /opt/intel/oneapi/setvars.sh --force && \
    cp -r /src/kvweave /tmp/kvweave_quant_build && \
    cd /tmp/kvweave_quant_build && \
    KVWEAVE_XPU=1 KVWEAVE_COMPILER=icpx pip wheel --no-build-isolation --no-deps . -w ${WHEELS} && \
    rm -rf build

# 1b Build LMCache wheel
RUN --mount=type=cache,target=/root/.cache/uv \
    set -eo pipefail && \
    source /opt/intel/oneapi/setvars.sh --force && \
    git clone --branch v0.5.5 https://github.com/LMCache/LMCache.git  /src/LMCache && \
    cd /src/LMCache && \
    uv  pip install -r requirements/common.txt && \
    uv  pip install grpcio-tools && \
    git apply /src/kvweave/integration/lmcache/patches/lmcache-mp-hybrid.patch && \
    git apply /src/kvweave/integration/lmcache/patches/lmcache-v0.5.5-mp-hybrid-to-kvweave.patch && \
    BUILD_WITH_SYCL=1 pip wheel --no-build-isolation --no-deps . -w ${WHEELS} && \
    rm -rf build

RUN ls -la ${WHEELS}/

FROM vllm/vllm-openai-xpu:v0.26.0

ARG http_proxy
ARG https_proxy
ARG no_proxy

# The base already exports PATH=/opt/venv/bin:... and DEVICE=xpu.
ENV PIP_EXTRA_INDEX_URL="https://download.pytorch.org/whl/xpu" \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    LD_LIBRARY_PATH="/opt/venv/lib:${LD_LIBRARY_PATH}" \
    VLLM_OFFLOAD_WEIGHTS_BEFORE_QUANT=1 \
    TORCH_LLM_ALLREDUCE=1 \
    VLLM_USE_V1=1 \
    W_LONG_MAX_MODEL_LEN=1 \
    VLLM_ALLOW_LONG_MAX_MODEL_LEN=1 \
    VLLM_WORKER_MULTIPROC_METHOD=spawn \
    LMCACHE_LOG_LEVEL=INFO \
    MODEL=Qwen3.5-9B \
    SERVE=Qwen3.5-9B \
    TP=1 \
    GPU_MEM_UTIL=0.5 \
    MAX_MODEL_LEN=8192 \
    DTYPE=float16 \
    QUANTIZATION=fp8 \
    DEBUG=False \
    LMCACHE_MP_HOST=tcp://localhost \
    LMCACHE_MP_PORT=6555 \
    LMCACHE_MP_HTTP_PORT=8090 \
    LMCACHE_MP_MQ_TIMEOUT=600 \
    LMCACHE_MP_HEARTBEAT_INTERVAL=15 \
    LMCACHE_MP_L2_ENABLE=true \
    LMCACHE_MP_L1_SIZE_GB=5 \
    LMCACHE_MP_EVICTION_POLICY=LRU \
    LMCACHE_MP_EVICTION_TRIGGER_WATERMARK=0.7 \
    LMCACHE_MP_EVICTION_RATIO=0.3 \
    LMCACHE_MP_SUPPORTED_TRANSFER_MODE=auto \
    LMCACHE_MP_SHM_NAME=lmcache_l1_pool_server \
    LMCACHE_MP_TRANSFER_MODE=engine_driven \
    LMCACHE_MP_L1_KVWEAVE_QUANT=1 \
    LMCACHE_MP_KVWEAVE_QUANT_DEVICE=xpu \
    LMCACHE_MP_KVWEAVE_QBIT=4 \
    LMCACHE_MP_KVWEAVE_SCALING_METHOD=per_channel \
    LMCACHE_MP_KVWEAVE_RH=1 \
    LMCACHE_MP_KVWEAVE_ASYM=1 \
    LMCACHE_MP_KVWEAVE_PRECOND=1 \
    LMCACHE_MP_KVWEAVE_LINEAR_QUANT_ENABLED=1 \
    LMCACHE_MP_KVWEAVE_LINEAR_MAX_SIZE_RATIO=1.20 \
    LMCACHE_MP_KVWEAVE_LINEAR_RH=1 \
    LMCACHE_MP_KVWEAVE_LINEAR_ASYM=1 \
    LMCACHE_MP_KVWEAVE_CONV_QUANT_ENABLED=1 \
    LMCACHE_MP_KVWEAVE_CONV_SCALING_METHOD=per_token \
    LMCACHE_MP_KVWEAVE_CONV_RH=1 \
    LMCACHE_MP_KVWEAVE_CONV_QBIT=4 \
    LMCACHE_MP_KVWEAVE_SSM_QUANT_ENABLED=1 \
    LMCACHE_MP_KVWEAVE_SSM_SCALING_METHOD=per_token \
    LMCACHE_MP_KVWEAVE_SSM_RH=1 \
    LMCACHE_MP_KVWEAVE_SSM_QBIT=4

WORKDIR /opt/kvweave
COPY --from=builder /src/kvweave ./kvweave
COPY --from=builder /src/LMCache ./LMCache

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,from=builder,source=/wheels,target=/wheels \
    pip install --no-deps /wheels/kvweave*.whl && \
    pip install --no-deps /wheels/lmcache*.whl && \
    pip install -r /opt/kvweave/LMCache/requirements/common.txt && \
    pip install grpcio-tools 

RUN cat <<'EOF' > /usr/local/bin/start-lmcache-vllm.sh
#!/usr/bin/env bash
set -euo pipefail

cleanup() {
    if [[ -n "${lmcache_pid:-}" ]]; then
        kill "${lmcache_pid}" 2>/dev/null || true
    fi
}
trap cleanup EXIT INT TERM

if block_size_output="$(python3 /opt/kvweave/kvweave/tests/calc_vllm_block_size.py \
    "${MODEL:-Qwen3.5-9B}" \
    --dtype "${DTYPE:-float16}" \
    --tp-size "${TP:-1}" \
    --block-size "${VLLM_INITIAL_BLOCK_SIZE:-64}" \
    --ma-mode align \
    --enable-prefix-caching)"; then
    block_size="$(printf '%s\n' "${block_size_output}" \
        | awk -F': ' '/^vLLM block size[[:space:]]*:/ {print $2}' \
        | awk '{print $1}')"
else
    block_size=""
fi
if [[ ! "${block_size}" =~ ^[0-9]+$ ]] || (( block_size <= 0 )); then
    echo "WARNING: failed to obtain vLLM block size; using default 1024" >&2
    printf '%s\n' "${block_size_output:-}" >&2
    block_size=1024
fi
echo "Using calculated vLLM block size: ${block_size} tokens"
if [[ -n "${VLLM_BLOCK_SIZE_OVERRIDE:-}" ]]; then
    block_size="${VLLM_BLOCK_SIZE_OVERRIDE}"
    echo "Overriding block size via VLLM_BLOCK_SIZE_OVERRIDE: ${block_size} tokens (lmcache chunk size / vllm block size / max_num_batched_tokens)"
fi

lmcache_chunk_size="${block_size}"
if [[ "${MODEL,,}" == *gemma* ]]; then
    lmcache_chunk_size=$(( block_size * 2 ))
    echo "Detected gemma model (${MODEL}); using lmcache chunk size: ${lmcache_chunk_size} tokens"
fi

lmcache_args=(
    --port "${LMCACHE_MP_PORT:-6555}"
    --http-port "${LMCACHE_MP_HTTP_PORT:-8090}"
    --l1-size-gb "${LMCACHE_MP_L1_SIZE_GB:-1}"
    --eviction-policy "${LMCACHE_MP_EVICTION_POLICY:-LRU}"
    --eviction-trigger-watermark "${LMCACHE_MP_EVICTION_TRIGGER_WATERMARK:-0.7}"
    --eviction-ratio "${LMCACHE_MP_EVICTION_RATIO:-0.3}"
    --chunk-size "${lmcache_chunk_size}"
    --supported-transfer-mode "${LMCACHE_MP_SUPPORTED_TRANSFER_MODE:-auto}"
    --shm-name "${LMCACHE_MP_SHM_NAME:-lmcache_l1_pool_server}"
)
l2_enable="${LMCACHE_MP_L2_ENABLE:-true}"
if [[ "${l2_enable,,}" == "true" ]]; then
    lmcache_args+=(--l2-adapter '{"type": "fs", "base_path": "/lmcache_disk"}')
fi

vllm_env=()
debug_enabled="${DEBUG:-False}"
if [[ "${debug_enabled,,}" == "true" ]]; then
    vllm_env+=(VLLM_SERVER_DEV_MODE=1)
fi

LMCACHE_LOG_LEVEL="${LMCACHE_LOG_LEVEL:-INFO}" \
lmcache server "${lmcache_args[@]}" &
lmcache_pid=$!

ready=0
for _ in $(seq 1 60); do
    if python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:${LMCACHE_MP_HTTP_PORT:-8090}/healthcheck', timeout=1).read()" >/dev/null 2>&1; then
        ready=1
        break
    fi
    sleep 1
done

if [[ "${ready}" != "1" ]]; then
    echo "ERROR: LMCache MP server did not become healthy" >&2
    exit 1
fi

exec env \
    "${vllm_env[@]}" \
    VLLM_OFFLOAD_WEIGHTS_BEFORE_QUANT="${VLLM_OFFLOAD_WEIGHTS_BEFORE_QUANT:-1}" \
    TORCH_LLM_ALLREDUCE="${TORCH_LLM_ALLREDUCE:-1}" \
    VLLM_USE_V1="${VLLM_USE_V1:-1}" \
    W_LONG_MAX_MODEL_LEN="${W_LONG_MAX_MODEL_LEN:-1}" \
    VLLM_WORKER_MULTIPROC_METHOD="${VLLM_WORKER_MULTIPROC_METHOD:-spawn}" \
    LMCACHE_LOG_LEVEL="${LMCACHE_LOG_LEVEL:-INFO}" \
    python3 -m vllm.entrypoints.openai.api_server \
        --model "${MODEL:-Qwen3.5-9B}" \
        --dtype "${DTYPE:-float16}" \
        --enforce-eager \
        --port 8000 \
        --block-size "${block_size}" \
        --gpu-memory-util "${GPU_MEM_UTIL:-0.5}" \
        --trust-remote-code \
        --enable-prefix-caching \
        --enable-prompt-tokens-details \
        --mamba-cache-mode align \
        --max_num_batched_tokens="${MAX_NUM_BATCHED_TOKENS:-${block_size}}" \
        --max_model_len "${MAX_MODEL_LEN:-8192}" \
        -tp="${TP:-1}" \
        --quantization "${QUANTIZATION:-fp8}" \
        --served-model-name "${SERVE:-Qwen3.5-9B}" \
        --kv-transfer-config "{\"kv_connector\":\"LMCacheMPConnector\",\"kv_role\":\"kv_both\",\"kv_connector_extra_config\":{\"lmcache.mp.host\":\"${LMCACHE_MP_HOST:-tcp://localhost}\",\"lmcache.mp.port\":${LMCACHE_MP_PORT:-6555}}}"
EOF

RUN chmod +x /usr/local/bin/start-lmcache-vllm.sh

# UID/GID 1000 already exists in the base image (Ubuntu 24.04's default
# non-root user); reuse it by numeric ID instead of creating a new one.
RUN chown -R 1000:1000 /opt/kvweave

USER 1000

ENTRYPOINT ["/usr/local/bin/start-lmcache-vllm.sh"]
