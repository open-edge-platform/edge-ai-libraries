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

COPY kv-quant-offload /src/kvweave

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

# --- uv for fast, deterministic installs (matches legacy build) ---
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

# --- torch MUST match the runtime base (2.11.0+xpu) so SyclExtension .so files link
#     against the same libtorch ABI the runtime ships (rpath $ORIGIN/../../torch/lib) ---
RUN --mount=type=cache,target=/root/.cache/uv \
    pip install --upgrade pip wheel setuptools && \
    uv pip install torch==2.11.0+xpu torchaudio torchvision \
        --index-url https://download.pytorch.org/whl/xpu

RUN mkdir -p ${WHEELS}

RUN --mount=type=cache,target=/root/.cache/uv \
    set -eo pipefail && \
    source /opt/intel/oneapi/setvars.sh --force && \
    git clone --depth 1 -b v0.23.0 https://github.com/vllm-project/vllm.git /src/vllm && \
    cd /src/vllm && \
    uv pip install -r requirements/xpu.txt && \
    uv pip install grpcio-tools protobuf nanobind && \
    export CMAKE_PREFIX_PATH="$(python3 -c 'import site; print(site.getsitepackages()[0])'):${CMAKE_PREFIX_PATH:-}" && \
    VLLM_TARGET_DEVICE=xpu pip wheel --no-build-isolation --no-deps . -w ${WHEELS} && \
    rm -rf build


RUN --mount=type=cache,target=/root/.cache/uv \
    set -eo pipefail && \
    source /opt/intel/oneapi/setvars.sh --force && \
    cp -r /src/kvweave /tmp/kvweave_quant_build && \
    cd /tmp/kvweave_quant_build && \
    KVWEAVE_COMPILER=icpx pip wheel --no-build-isolation --no-deps . -w ${WHEELS} && \
    rm -rf build

RUN --mount=type=cache,target=/root/.cache/uv \
    set -eo pipefail && \
    source /opt/intel/oneapi/setvars.sh --force && \
    git clone --branch v0.4.7 https://github.com/LMCache/LMCache.git  /src/LMCache && \
    cd /src/LMCache && \
    uv  pip install -r requirements/common.txt && \
    git apply /src/kvweave/integration/lmcache/patches/lmcache-mp-hybrid.patch && \
    git apply /src/kvweave/integration/lmcache/patches/lmcache-v0.4.7-mp-hybrid-to-kvweave.patch && \
    BUILD_WITH_SYCL=1 pip wheel --no-build-isolation --no-deps . -w ${WHEELS} && \
    rm -rf build

RUN ls -la ${WHEELS}/

FROM intel/pytorch:xpu-2.11.0-ubuntu24.04

ARG http_proxy
ARG https_proxy
ARG no_proxy
ARG ONECCL_INSTALLER="intel-oneccl-2021.15.9.14_offline.sh"
ARG ONECCL_INSTALLER_SHA256="f7ab81b6ed1b10dd35fadec366a78046d8af214888dfd625047ce8953d5aa4ef"

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
    LMCACHE_MP_HOST=tcp://localhost \
    LMCACHE_MP_PORT=6555 \
    LMCACHE_MP_HTTP_PORT=8090 \
    LMCACHE_MP_L1_SIZE_GB=5 \
    LMCACHE_MP_EVICTION_POLICY=LRU \
    LMCACHE_MP_EVICTION_TRIGGER_WATERMARK=0.7 \
    LMCACHE_MP_EVICTION_RATIO=0.3 \
    LMCACHE_MP_L1_KVWEAVE_QUANT=1 \
    LMCACHE_MP_KVWEAVE_NUM_KV_HEADS=4 \
    LMCACHE_MP_KVWEAVE_HEAD_DIM=256 \
    LMCACHE_MP_KVWEAVE_NUM_THREADS=8 \
    LMCACHE_MP_KVWEAVE_PRECOND=1 \
    LMCACHE_MP_KVWEAVE_SCALING_METHOD=per_channel \
    LMCACHE_MP_KVWEAVE_LINEAR_QUANT_ENABLED=1 \
    LMCACHE_MP_KVWEAVE_CONV_SCALING_METHOD=per_token \
    LMCACHE_MP_KVWEAVE_CONV_RH=0 \
    LMCACHE_MP_KVWEAVE_SSM_SCALING_METHOD=per_channel \
    LMCACHE_MP_KVWEAVE_SSM_RH=1 \
    LMCACHE_MP_KVWEAVE_LINEAR_ASYM=0

WORKDIR /opt/kvweave
COPY --from=builder /src/vllm ./vllm
COPY --from=builder /src/kvweave ./kvweave
COPY --from=builder /src/LMCache ./LMCache

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,from=builder,source=/wheels,target=/wheels \
    apt-get update -y && \
    apt-get install -y --no-install-recommends --fix-missing \
        ffmpeg libsndfile1 libsm6 libxext6 libgl1 numactl curl && \
    rm -rf /var/lib/apt/lists/* && \
    curl -fL --retry 3 -o "${ONECCL_INSTALLER}" "https://github.com/uxlfoundation/oneCCL/releases/download/2021.15.9/${ONECCL_INSTALLER}" && \
    printf "%s  %s\n" "${ONECCL_INSTALLER_SHA256}" "${ONECCL_INSTALLER}" > /tmp/oneccl.sha256 && \
    sha256sum -c /tmp/oneccl.sha256 && \
    rm -f /tmp/oneccl.sha256 && \
    bash "${ONECCL_INSTALLER}" -s -x -f /tmp && \
    ONECCL_CUP="/tmp/${ONECCL_INSTALLER%.sh}/packages/intel.oneapi.lin.ccl.runtime,v=2021.15.9+13/cupPayload.cup" && \
    ONECCL_DST="/tmp/oneccl-runtime" && \
    python3 -m zipfile -e "${ONECCL_CUP}" "${ONECCL_DST}" && \
    ONECCL_LIB="${ONECCL_DST}/_installdir/ccl/2021.15/lib" && \
    rm -f "${ONECCL_LIB}/libccl.so" "${ONECCL_LIB}/libccl.so.1" "${ONECCL_LIB}/libccl_openmp.so" "${ONECCL_LIB}/libccl_openmp.so.0" && \
    ln -sf libccl.so.1 "${ONECCL_LIB}/libccl.so" && \
    ln -sf libccl.so.1.0 "${ONECCL_LIB}/libccl.so.1" && \
    ln -sf libccl_openmp.so.0 "${ONECCL_LIB}/libccl_openmp.so" && \
    ln -sf libccl_openmp.so.0.1 "${ONECCL_LIB}/libccl_openmp.so.0" && \
    ONECCL_CPU_LIB="${ONECCL_DST}/_installdir/ccl/2021.15/lib/ccl/cpu/lib" && \
    rm -f "${ONECCL_CPU_LIB}/libccl.so" "${ONECCL_CPU_LIB}/libccl.so.1" "${ONECCL_CPU_LIB}/libccl_openmp.so" "${ONECCL_CPU_LIB}/libccl_openmp.so.0" && \
    ln -sf libccl.so.1 "${ONECCL_CPU_LIB}/libccl.so" && \
    ln -sf libccl.so.1.0 "${ONECCL_CPU_LIB}/libccl.so.1" && \
    ln -sf libccl_openmp.so.0 "${ONECCL_CPU_LIB}/libccl_openmp.so" && \
    ln -sf libccl_openmp.so.0.1 "${ONECCL_CPU_LIB}/libccl_openmp.so.0" && \
    mkdir -p /opt/intel/oneapi/ccl && \
    rm -rf /opt/intel/oneapi/ccl/2021.15 && \
    cp -a /tmp/oneccl-runtime/_installdir/ccl/2021.15 /opt/intel/oneapi/ccl/ && \
    rm "${ONECCL_INSTALLER}" && \
    echo "export LD_LIBRARY_PATH=/opt/venv/lib\${LD_LIBRARY_PATH:+:\$LD_LIBRARY_PATH}" >> /root/.bashrc && \
    echo "if [ -f /opt/intel/oneapi/setvars.sh ]; then source /opt/intel/oneapi/setvars.sh --force; fi" >> /root/.bashrc && \
    echo "if [ -f /opt/intel/oneapi/ccl/2021.15/env/vars.sh ]; then source /opt/intel/oneapi/ccl/2021.15/env/vars.sh --force; fi" >> /root/.bashrc && \
    rm -f /opt/intel/oneapi/ccl/latest && \
    ln -s /opt/intel/oneapi/ccl/2021.15 /opt/intel/oneapi/ccl/latest && \
    find /opt/intel/oneapi/ccl -mindepth 1 -maxdepth 1 -type d -not -name 2021.15 -exec rm -rf {} + && \
    rm -rf "/tmp/${ONECCL_INSTALLER%.sh}" /tmp/oneccl-runtime && \
    pip install --no-deps /wheels/kvweave*.whl && \
    pip install --no-deps /wheels/lmcache*.whl && \
    pip install -r /opt/kvweave/LMCache/requirements/common.txt && \
    pip install /wheels/vllm-*.whl --extra-index-url https://download.pytorch.org/whl/xpu && \
    pip install transformers==5.8.0 accelerate hf_transfer 'modelscope!=1.15.0' && \
    pip install librosa soundfile decord ijson && \
    pip uninstall -y triton triton-xpu || true && \
    pip install --no-deps triton-xpu==3.7.0 \
        --extra-index-url https://download.pytorch.org/whl/xpu && \
    pip uninstall -y oneccl oneccl-devel || true && \
    rm -f /opt/venv/lib/libccl.so /opt/venv/lib/libccl.so.1 /opt/venv/lib/libccl.so.1.0 \
        /opt/venv/lib/libccl_openmp.so /opt/venv/lib/libccl_openmp.so.0 /opt/venv/lib/libccl_openmp.so.0.1 && \
    ln -sf /opt/intel/oneapi/ccl/2021.15/lib/libccl.so.1.0 /opt/venv/lib/libccl.so.1 && \
    ln -sf /opt/venv/lib/libccl.so.1 /opt/venv/lib/libccl.so && \
    ln -sf /opt/intel/oneapi/ccl/2021.15/lib/libccl_openmp.so.0.1 /opt/venv/lib/libccl_openmp.so.0 && \
    ln -sf /opt/venv/lib/libccl_openmp.so.0 /opt/venv/lib/libccl_openmp.so && \
    TRITON=/opt/venv/lib/python3.12/site-packages/triton && \
    strip --strip-debug ${TRITON}/_C/libtriton.so && \
    rm -f ${TRITON}/plugins/libMLIRDialectPlugin.so.22.0git && \
    ln -s libMLIRDialectPlugin.so ${TRITON}/plugins/libMLIRDialectPlugin.so.22.0git

RUN cat <<'EOF' > /usr/local/bin/start-lmcache-vllm.sh
#!/usr/bin/env bash
set -euo pipefail

cleanup() {
    if [[ -n "${lmcache_pid:-}" ]]; then
        kill "${lmcache_pid}" 2>/dev/null || true
    fi
}
trap cleanup EXIT INT TERM

LMCACHE_LOG_LEVEL="${LMCACHE_LOG_LEVEL:-INFO}" \
lmcache server \
    --port "${LMCACHE_MP_PORT:-6555}" \
    --http-port "${LMCACHE_MP_HTTP_PORT:-8090}" \
    --l1-size-gb "${LMCACHE_MP_L1_SIZE_GB:-1}" \
    --eviction-policy "${LMCACHE_MP_EVICTION_POLICY:-LRU}" \
    --eviction-trigger-watermark "${LMCACHE_MP_EVICTION_TRIGGER_WATERMARK:-0.7}" \
    --eviction-ratio "${LMCACHE_MP_EVICTION_RATIO:-0.3}" \
    --chunk-size 1024 &
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
    VLLM_OFFLOAD_WEIGHTS_BEFORE_QUANT="${VLLM_OFFLOAD_WEIGHTS_BEFORE_QUANT:-1}" \
    TORCH_LLM_ALLREDUCE="${TORCH_LLM_ALLREDUCE:-1}" \
    VLLM_USE_V1="${VLLM_USE_V1:-1}" \
    W_LONG_MAX_MODEL_LEN="${W_LONG_MAX_MODEL_LEN:-1}" \
    VLLM_WORKER_MULTIPROC_METHOD="${VLLM_WORKER_MULTIPROC_METHOD:-spawn}" \
    LMCACHE_LOG_LEVEL="${LMCACHE_LOG_LEVEL:-INFO}" \
    python3 -m vllm.entrypoints.openai.api_server \
        --model "${MODEL:-Qwen3.5-9B}" \
        --dtype=float16 \
        --enforce-eager \
        --port 8000 \
        --block-size 1024 \
        --gpu-memory-util "${GPU_MEM_UTIL:-0.5}" \
        --trust-remote-code \
        --enable-prefix-caching \
        --mamba-cache-mode align \
        --max_num_batched_tokens=1024 \
        --max_model_len "${MAX_MODEL_LEN:-8192}" \
        -tp="${TP:-1}" \
        --served-model-name "${SERVE:-Qwen3.5-9B}" \
        --kv-transfer-config "{\"kv_connector\":\"LMCacheMPConnector\",\"kv_role\":\"kv_both\",\"kv_connector_extra_config\":{\"lmcache.mp.host\":\"${LMCACHE_MP_HOST:-tcp://localhost}\",\"lmcache.mp.port\":${LMCACHE_MP_PORT:-6555}}}"
EOF

RUN chmod +x /usr/local/bin/start-lmcache-vllm.sh

ENTRYPOINT ["/usr/local/bin/start-lmcache-vllm.sh"]
