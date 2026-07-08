#!/bin/bash
#
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

MODEL_PATH="${MODEL_PATH:-Qwen/Qwen3.5-9B}"
SERVED_MODEL_NAME="${SERVED_MODEL_NAME:-${MODEL_PATH}}"
MAX_MODEL_LEN="${MAX_MODEL_LEN:-32768}"
LOAD_QUANTIZATION="${LOAD_QUANTIZATION:-fp8}"
TENSOR_PARALLEL_SIZE="${TENSOR_PARALLEL_SIZE:-1}"
GPU_MEM_UTIL="${GPU_MEM_UTIL:-0.5}"

echo "HF_HUB_OFFLINE: $HF_HUB_OFFLINE"
echo "LOAD_QUANTIZATION is $LOAD_QUANTIZATION"
echo "TENSOR_PARALLEL_SIZE is $TENSOR_PARALLEL_SIZE"
echo "MODEL_PATH is $MODEL_PATH"
echo "SERVED_MODEL_NAME is $SERVED_MODEL_NAME"
echo "GPU_MEM_UTIL is $GPU_MEM_UTIL"
echo "MAX_MODEL_LEN is $MAX_MODEL_LEN"


python3 "$(dirname "$0")/patch_vllm_video.py"

VLLM_ALLOW_RUNTIME_LORA_UPDATING=True \
TORCH_LLM_ALLREDUCE=1 \
VLLM_USE_V1=1 \
VLLM_ALLOW_LONG_MAX_MODEL_LEN=1 \
VLLM_WORKER_MULTIPROC_METHOD=spawn \
python3 -m vllm.entrypoints.openai.api_server \
    --model ${MODEL_PATH} \
    --dtype=float16 \
    --served-model-name ${SERVED_MODEL_NAME} \
    --enforce-eager \
    --port 8000 \
    --host 0.0.0.0 \
    --trust-remote-code \
    --gpu-memory-util=${GPU_MEM_UTIL} \
    --disable-log-requests \
    --max-model-len=${MAX_MODEL_LEN} \
    --block-size 64 \
    --max_num_batched_tokens=8192 \
    --quantization ${LOAD_QUANTIZATION} \
    -tp=${TENSOR_PARALLEL_SIZE} \
    --enable-prefix-caching  \
    --enable-auto-tool-choice \
    --tool-call-parser qwen3_coder \
    --reasoning-parser qwen3 \
    --default-chat-template-kwargs '{"enable_thinking": false}'
