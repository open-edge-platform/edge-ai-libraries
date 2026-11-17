#!/usr/bin/env bash
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# Start the official vLLM-XPU image with prefix caching enabled.

set -euo pipefail

MODEL_PATH="${MODEL_PATH:-Qwen/Qwen3.6-35B-A3B}"
MAX_MODEL_LEN="${MAX_MODEL_LEN:-61440}"
LOAD_QUANTIZATION="${LOAD_QUANTIZATION:-fp8}"
TENSOR_PARALLEL_SIZE="${TENSOR_PARALLEL_SIZE:-1}"
GPU_MEM_UTIL="${GPU_MEM_UTIL:-0.8}"

printf 'MODEL_PATH is %s\nMAX_MODEL_LEN is %s\nLOAD_QUANTIZATION is %s\nTENSOR_PARALLEL_SIZE is %s\nGPU_MEM_UTIL is %s\n' \
    "${MODEL_PATH}" "${MAX_MODEL_LEN}" \
    "${LOAD_QUANTIZATION}" "${TENSOR_PARALLEL_SIZE}" "${GPU_MEM_UTIL}"

lora_args=()
if [[ "${DYNAMIC_LORA:-0}" == "1" || "${DYNAMIC_LORA:-0}" == "true" ]]; then
    lora_args=(--enable-lora --max-loras 4 --max-lora-rank 64 --max-cpu-loras 8)
    export VLLM_ALLOW_RUNTIME_LORA_UPDATING=1
fi

VLLM_ALLOW_LONG_MAX_MODEL_LEN=1 \
VLLM_WORKER_MULTIPROC_METHOD=spawn \
exec vllm serve \
    --model "${MODEL_PATH}" \
    --dtype=half \
    --served-model-name "${MODEL_PATH}" \
    --enforce-eager \
    --port 8000 \
    --host 0.0.0.0 \
    --gpu-memory-utilization "${GPU_MEM_UTIL}" \
    --trust-remote-code \
    --no-enable-log-requests \
    --enable-prefix-caching \
    --media-io-kwargs '{"video": {"num_frames": -1}}' \
    --max-model-len "${MAX_MODEL_LEN}" \
    --block-size 64 \
    --max-num-batched-tokens 8192 \
    --quantization "${LOAD_QUANTIZATION}" \
    --allow-deprecated-quantization \
    --tensor-parallel-size "${TENSOR_PARALLEL_SIZE}" \
    "${lora_args[@]}" \
    --enable-auto-tool-choice \
    --tool-call-parser qwen3_coder \
    --reasoning-parser qwen3 \
    --default-chat-template-kwargs '{"enable_thinking": false}'
