#!/bin/bash
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Run inside the vllm-kvweave container (see integration/vllm/vllm-start.sh DEBUG=1).
#
# Sends NUM_REQUESTS DIFFERENT concurrent requests ("wave 1": each request
# gets a distinct, deterministically shuffled prompt built from two seed
# texts, so no two requests in the same wave share content and none can hit
# another's prefix/KV cache), waits for all of them to finish, then sends
# the EXACT SAME NUM_REQUESTS requests again ("wave 2"), and reports
# per-request TTFT/TPOT for every request in both waves so you can compare
# wave1 (cold) vs wave2 (e.g. KV-cache-warmed) latency.
#
# Also reports each request's cached_tokens (vLLM local prefix cache +
# LMCache external cache hits, combined). This requires the vLLM server to
# be started with --enable-prompt-tokens-details (off by default); without
# it, cached_tokens will show up as null for every request.
#
# Requires: python3 with transformers installed (for exact-token-length
# truncation via the model's own tokenizer).
#

# ---------------------------------------------------------------------------
# Simple Usage
#
  # start lmcache: 
  #     export LMCACHE_LOG_LEVEL=INFO
  #     export LMCACHE_MP_L1_KVWEAVE_QUANT=1
  #     export LMCACHE_MP_KVWEAVE_NUM_KV_HEADS=4
  #     export LMCACHE_MP_KVWEAVE_HEAD_DIM=256
  #     export LMCACHE_MP_KVWEAVE_NUM_THREADS=8
  #     export LMCACHE_MP_KVWEAVE_PRECOND=1
  #     export LMCACHE_MP_KVWEAVE_SCALING_METHOD=per_channel

  #     # Mamba conv/ssm 独立量化配置（按需覆盖，未设置则回退到 LINEAR_* 默认值）
  #     export LMCACHE_MP_KVWEAVE_LINEAR_QUANT_ENABLED=1
  #     export LMCACHE_MP_KVWEAVE_CONV_SCALING_METHOD=per_channel
  #     export LMCACHE_MP_KVWEAVE_CONV_RH=0
  #     export LMCACHE_MP_KVWEAVE_SSM_SCALING_METHOD=per_channel
  #     export LMCACHE_MP_KVWEAVE_SSM_RH=1
  #     export LMCACHE_MP_KVWEAVE_LINEAR_ASYM=1

  #     # 同样不传 --l2-adapter，纯 L1
  #     lmcache server \
  #       --port 6555 \
  #       --http-port 8090 \
  #       --l1-size-gb 5 \
  #       --eviction-policy LRU \
  #       --eviction-trigger-watermark 0.7 \
  #       --eviction-ratio 0.3 \
  #       --chunk-size 1024 \
  #       --l2-adapter '{"type": "fs", "base_path": "/lmcache_disk"}'
  # start vllm:
  #     export VLLM_OFFLOAD_WEIGHTS_BEFORE_QUANT=1
  #     export TORCH_LLM_ALLREDUCE=1
  #     export VLLM_USE_V1=1
  #     export W_LONG_MAX_MODEL_LEN=1
  #     export VLLM_WORKER_MULTIPROC_METHOD=spawn
  #     export LMCACHE_LOG_LEVEL=INFO
  #     export LMCACHE_MP_L1_KVWEAVE_QUANT=1
  #     export LMCACHE_MP_KVWEAVE_NUM_KV_HEADS=4
  #     export LMCACHE_MP_KVWEAVE_HEAD_DIM=256
  #     export LMCACHE_MP_KVWEAVE_NUM_THREADS=8
  #     export LMCACHE_MP_KVWEAVE_PRECOND=1
  #     export LMCACHE_MP_KVWEAVE_SCALING_METHOD=per_channel

  #     export LMCACHE_MP_KVWEAVE_LINEAR_QUANT_ENABLED=1
  #     export LMCACHE_MP_KVWEAVE_CONV_SCALING_METHOD=per_channel
  #     export LMCACHE_MP_KVWEAVE_CONV_RH=0
  #     export LMCACHE_MP_KVWEAVE_SSM_SCALING_METHOD=per_channel
  #     export LMCACHE_MP_KVWEAVE_SSM_RH=1
  #     export LMCACHE_MP_KVWEAVE_LINEAR_ASYM=1

  #     VLLM_SERVER_DEV_MODE=1 python3 -m vllm.entrypoints.openai.api_server \
  #     --model /models/Qwen3.5-9B \
  #     --dtype=float16 \
  #     --enforce-eager \
  #     --port 8000 \
  #     --block-size 64 \
  #     --gpu-memory-util 0.3 \
  #     --trust-remote-code \
  #     --enable-prefix-caching \
  #     --mamba-cache-mode align \
  #     --max_num_batched_tokens=1024 \
  #     --max_model_len 100000 \
  #     -tp=1 \
  #     --quantization fp8 \
  #     --served-model-name Qwen3.5-9B \
  #     --kv-transfer-config '{"kv_connector":"LMCacheMPConnector","kv_role":"kv_both","kv_connector_extra_config":{"lmcache.mp.host":"tcp://localhost","lmcache.mp.port":6555}}'   --enable-prompt-tokens-details
  # trigger test:
  #     SEQ=1 WARMUP=1 NUM_REQUESTS=2 TOKENIZER_PATH=/models/Qwen3.5-9B INPUT_LEN=40960 MAX_TOKENS=128 bash ./vllm-bench-two-waves.sh           for 2 requests, 40960-token prompts, L1 cache test, will clear l0 cache between waves, running in seq.
  #     WARMUP=1 NUM_REQUESTS=2 TOKENIZER_PATH=/models/Qwen3.5-9B INPUT_LEN=40960 MAX_TOKENS=128 bash ./vllm-bench-two-waves.sh                 for 2 requests, 40960-token prompts, L1 cache test, will clear l0 cache between waves
  #     TEST_OBJECT=l2 WARMUP=1 NUM_REQUESTS=2 TOKENIZER_PATH=/models/Qwen3.5-9B INPUT_LEN=40960 MAX_TOKENS=128 bash ./vllm-bench-two-waves.sh  for 2 requests, 40960-token prompts, L2 cache test, will clear l0 and l1 cache between waves

# ---------------------------------------------------------------------------
# Usage
#
#   bash tests/vllm-bench-two-waves.sh
#
# Everything is configured through environment variables; there are no CLI
# flags. Common invocations:
#
#   # Defaults: 2 requests, 512-token prompts, L1 cache test.
#   bash tests/vllm-bench-two-waves.sh
#
#   # Heavier run against a specific served model.
#   MODEL=Qwen3.5-9B TOKENIZER_PATH=/models/Qwen3.5-9B \
#   NUM_REQUESTS=8 INPUT_LEN=2048 bash tests/vllm-bench-two-waves.sh
#
#   # Measure the L2 (disk) tier: clears vLLM prefix cache + LMCache L1
#   # between the waves so wave2 has to come from L2.
#   TEST_OBJECT=l2 bash tests/vllm-bench-two-waves.sh
#
#   # Skip the kernel-compilation warmup (faster, but wave1 TTFT is polluted).
#   WARMUP=0 bash tests/vllm-bench-two-waves.sh
#
# Key variables (default):
#   MODEL (Qwen3.5-9B)      Served model name; must match --served-model-name.
#   TOKENIZER_PATH ($MODEL) Local path AutoTokenizer can resolve, e.g.
#                           /models/Qwen3.5-9B. Set whenever it differs from
#                           the served name.
#   HOST/PORT (localhost/8000)  vLLM OpenAI API endpoint.
#   NUM_REQUESTS (2)        Concurrent requests per wave.
#   INPUT_LEN (512)         Exact prompt length in tokens.
#   MAX_TOKENS (256)        Max generated tokens per request.
#   SEQ (0)                 1 = send requests sequentially, not concurrently.
#   TEST_OBJECT (l1)        What to exercise between waves: l1 | l2 | l1_l0.
#   WARMUP (1)              1 = run a warmup request before wave1.
#   RESET_PREFIX_CACHE (1)  Reset vLLM prefix cache between waves (TEST_OBJECT=l1
#                           only; needs VLLM_SERVER_DEV_MODE=1 on the server).
#   LMCACHE_HTTP_URL (http://localhost:8090)  LMCache --http-port endpoint.
#   OUT_DIR (/tmp/vllm-bench-two-waves)       Where waveN.json is written.
#
# Output: per-request TTFT/TPOT/cached_tokens for both waves printed as a
# summary, with raw results in ${OUT_DIR}/wave1.json and wave2.json.
#
# Note: cached_tokens is null unless the vLLM server was started with
# --enable-prompt-tokens-details.
# ---------------------------------------------------------------------------
set -euo pipefail

# Served model name -- must match --served-model-name on the vLLM server,
# used as the "model" field in API requests.
MODEL=${MODEL:-Qwen3.5-9B}
# Local path/name AutoTokenizer can resolve (e.g. /models/Qwen3.5-9B).
# Defaults to $MODEL, but set this separately whenever the served model name
# differs from the tokenizer's local path (as with --served-model-name).
TOKENIZER_PATH=${TOKENIZER_PATH:-${MODEL}}
HOST=${HOST:-localhost}
PORT=${PORT:-8000}
KEY=${KEY:-sk-xxx}
MAX_TOKENS=${MAX_TOKENS:-256}
# Number of concurrent requests sent per wave.
NUM_REQUESTS=${NUM_REQUESTS:-2}
# When set to 1, send requests sequentially instead of starting them all at once.
SEQ=${SEQ:-0}
# Exact input length (in tokens) for every prompt, enforced via the model's
# own tokenizer (loaded from $TOKENIZER_PATH).
INPUT_LEN=${INPUT_LEN:-512}
OUT_DIR=${OUT_DIR:-/tmp/vllm-bench-two-waves}

# Whether to run a `vllm bench serve` warmup request before wave1, to trigger
# kernel compilation (e.g. torch.compile / Triton autotune) so it doesn't
# pollute wave1's TTFT measurement. Set to 0 to skip.
WARMUP=${WARMUP:-1}
# Whether to reset the vLLM prefix cache between waves.
# This only works when the server was started with VLLM_SERVER_DEV_MODE=1.
RESET_PREFIX_CACHE=${RESET_PREFIX_CACHE:-1}
# Test target: l1 by default. When set to l2, clear the LMCache L1 cache
# between warmup and waves so the cache state does not affect the run.
TEST_OBJECT=${TEST_OBJECT:-l1}
# LMCache HTTP server (http-port from `lmcache server ...`), used to clear
# the L1 cache after warmup so the warmup request's KV doesn't count as a
# cache hit in wave1.
LMCACHE_HTTP_URL=${LMCACHE_HTTP_URL:-http://localhost:8090}

maybe_clear_l1_cache() {
if [ "${TEST_OBJECT}" = "l2" ]; then
  curl -s -X POST 'http://localhost:8000/reset_prefix_cache' >/dev/null || \
  echo "=== reset_prefix_cache unavailable; start vLLM with VLLM_SERVER_DEV_MODE=1 to enable it ==="
  sleep 5
  curl -sf -X POST "${LMCACHE_HTTP_URL}/clear-cache"
  sleep 5
elif [ "${TEST_OBJECT}" = "l1_l0" ]; then
  sleep 5

  local metrics_url="http://${HOST}:${PORT}/metrics"
  local cache_info
  local num_gpu_blocks
  local block_size
  local blocks_per_req
  local flush_reqs
  local flush_conc

  cache_info=$(
    curl -sf "${metrics_url}" | python3 -c '
import re, sys

line_pat = re.compile(r"^(?:vllm:cache_config_info|vllm_cache_config_info)\{([^}]*)\}\s+")
kv_pat = re.compile(r"(\w+)\=\"([^\"]*)\"")
num_gpu_blocks = ""
block_size = ""

for line in sys.stdin:
  m = line_pat.match(line)
  if not m:
      continue
  labels = dict(kv_pat.findall(m.group(1)))
  if not num_gpu_blocks:
      num_gpu_blocks = labels.get("num_gpu_blocks", "")
  if not block_size:
      block_size = labels.get("block_size", "")
  if num_gpu_blocks and block_size:
      break

print(f"{num_gpu_blocks} {block_size}")
'
  ) || cache_info=""

  num_gpu_blocks=$(echo "${cache_info}" | awk '{print $1}')
  block_size=$(echo "${cache_info}" | awk '{print $2}')

  if ! [[ "${num_gpu_blocks}" =~ ^[0-9]+$ ]] || [ "${num_gpu_blocks}" -le 0 ]; then
    num_gpu_blocks=${VLLM_NUM_GPU_BLOCKS:-0}
  fi
  if ! [[ "${block_size}" =~ ^[0-9]+$ ]] || [ "${block_size}" -le 0 ]; then
    block_size=${VLLM_BLOCK_SIZE:-64}
  fi

  if ! [[ "${num_gpu_blocks}" =~ ^[0-9]+$ ]] || [ "${num_gpu_blocks}" -le 0 ]; then
    flush_reqs=${L0_FLUSH_REQUESTS:-64}
    echo "=== l1_l0: cannot infer num_gpu_blocks from ${metrics_url}, fallback flush requests=${flush_reqs} ==="
  else
    blocks_per_req=$(( (INPUT_LEN + block_size - 1) / block_size ))
    if [ "${blocks_per_req}" -le 0 ]; then
      blocks_per_req=1
    fi
    # +1 to push one more request beyond cache capacity and evict old prefixes.
    flush_reqs=$(( num_gpu_blocks / blocks_per_req + 1 ))
    if [ "${flush_reqs}" -le 0 ]; then
      flush_reqs=1
    fi
    echo "=== l1_l0: num_gpu_blocks=${num_gpu_blocks}, block_size=${block_size}, blocks_per_req=${blocks_per_req}, flush_requests=${flush_reqs} ==="
  fi

  flush_conc=${L0_FLUSH_MAX_CONCURRENCY:-16}
  if ! [[ "${flush_conc}" =~ ^[0-9]+$ ]] || [ "${flush_conc}" -le 0 ]; then
    flush_conc=16
  fi
  if [ "${flush_conc}" -gt "${flush_reqs}" ]; then
    flush_conc=${flush_reqs}
  fi

  vllm bench serve \
    --host "${HOST}" \
    --port "${PORT}" \
    --model "${TOKENIZER_PATH}" \
    --served-model-name "${MODEL}" \
    --dataset-name random \
    --random-input-len ${INPUT_LEN} \
    --random-output-len 1 \
    --num-prompts ${flush_reqs} \
    --max-concurrency ${flush_conc} \
    --ignore-eos

  sleep 5
elif [ "${TEST_OBJECT}" = "l1" ] && [ "${RESET_PREFIX_CACHE}" = "1" ]; then
  curl -s -X POST 'http://localhost:8000/reset_prefix_cache' >/dev/null || \
    echo "=== reset_prefix_cache unavailable; start vLLM with VLLM_SERVER_DEV_MODE=1 to enable it ==="
fi
}

mkdir -p "${OUT_DIR}"

# Seed text pool A: Harry Potter opening (same text used in vllm-curl.sh).
# The worker splits these seed texts into sentences and, per request index,
# deterministically shuffles them into a distinct prompt, then
# repeats/truncates it to exactly INPUT_LEN tokens.
export PROMPT_A="Mr. and Mrs. Dursley, of number four, Privet Drive, were proud to say that they were perfectly normal, thank you very much. They were the last people you'd expect to be involved in anything strange or mysterious, because they just didn't hold with such nonsense. Mr. Dursley was the director of a firm called Grunnings, which made drills. He was a big, beefy man with hardly any neck, although he did have a very large mustache. Mrs. Dursley was thin and blonde and had nearly twice the usual amount of neck, which came in very useful as she spent so much of her time craning over garden fences, spying on the neighbors. The Dursleys had a small son called Dudley and in their opinion there was no finer boy anywhere. The Dursleys had everything they wanted, but they also had a secret, and their greatest fear was that somebody would discover it. They didn't think they could bear it if anyone found out about the Potters. Mrs. Potter was Mrs. Dursley's sister, but they hadn't met for several years; in fact, Mrs. Dursley pretended she didn't have a sister, because her sister and her good-for-nothing husband were as unDursleyish as it was possible to be. The Dursleys shuddered to think what the neighbors would say if the Potters arrived in the street. The Dursleys knew that the Potters had a small son, too, but they had never even seen him. This boy was another good reason for keeping the Potters away; they didn't want Dudley mixing with a child like that. When Mr. and Mrs. Dursley woke up on the dull, gray Tuesday our story starts, there was nothing about the cloudy sky outside to suggest that strange and mysterious things would soon be happening all over the country. Mr. Dursley hummed as he picked out his most boring tie for work, and Mrs. Dursley gossiped away happily as she wrestled a screaming Dudley into his high chair. None of them noticed a large, tawny owl flutter past the window. At half past eight, Mr. Dursley picked up his briefcase, pecked Mrs. Dursley on the cheek, and tried to kiss Dudley good-bye but missed, because Dudley was now having a tantrum and throwing his cereal at the walls."

# Seed text pool B: Pride and Prejudice opening -- unrelated content, no
# shared sentences with pool A.
export PROMPT_B="It is a truth universally acknowledged, that a single man in possession of a good fortune must be in want of a wife. However little known the feelings or views of such a man may be on his first entering a neighbourhood, this truth is so well fixed in the minds of the surrounding families, that he is considered as the rightful property of some one or other of their daughters. My dear Mr. Bennet, said his lady to him one day, have you heard that Netherfield Park is let at last? Mr. Bennet replied that he had not. But it is, returned she; for Mrs. Long has just been here, and she told me all about it. Mr. Bennet made no answer. Do not you want to know who has taken it? cried his wife impatiently. You want to tell me, and I have no objection to hearing it. This was invitation enough. Why, my dear, you must know, Mrs. Long says that Netherfield is taken by a young man of large fortune from the north of England; that he came down on Monday in a chaise and four to see the place, and was so much delighted with it that he agreed with Mr. Morris immediately; that he is to take possession before Michaelmas, and some of his servants are to be in the house by the end of next week. What is his name? Bingley. Is he married or single? Oh! single, my dear, to be sure! A single man of large fortune; four or five thousand a year. What a fine thing for our girls!"

export MODEL TOKENIZER_PATH HOST PORT KEY MAX_TOKENS OUT_DIR INPUT_LEN NUM_REQUESTS SEQ

run_wave() {
local wave_name=$1
echo "=== ${wave_name}: sending ${NUM_REQUESTS} concurrent (distinct) requests ==="
WAVE_NAME="${wave_name}" python3 "$(dirname "$0")/vllm_two_waves_worker.py"
echo "=== ${wave_name}: done, result saved to ${OUT_DIR}/${wave_name}.json ==="
}

if [ "${WARMUP}" = "1" ]; then
echo "=== warmup: triggering kernel compilation via vllm bench serve ==="
vllm bench serve \
  --host "${HOST}" \
  --port "${PORT}" \
  --model "${TOKENIZER_PATH}" \
  --served-model-name "${MODEL}" \
  --dataset-name random \
  --random-input-len ${INPUT_LEN} \
  --random-output-len 64 \
  --num-prompts 1 \
  --max-concurrency 2 \
  --ignore-eos
echo "=== warmup: done, clearing LMCache L1 cache ==="
sleep 5
curl -sf -X POST "${LMCACHE_HTTP_URL}/clear-cache"
sleep 5
echo
echo "=== warmup: L1 cache cleared ==="
fi

run_wave "wave1"

maybe_clear_l1_cache

run_wave "wave2"

echo
echo "--- Summary ---"
for wave_name in wave1 wave2; do
echo "${wave_name}:"
python3 -c "
import json
with open('${OUT_DIR}/${wave_name}.json') as f:
  data = json.load(f)
def fmt(x):
  return f'{x:.2f}' if x is not None else 'None'
for req_id, m in sorted(data.items(), key=lambda kv: int(kv[0].removeprefix('req'))):
  print(f'  {req_id}: ttft_ms={fmt(m[\"ttft_ms\"])}  tpot_ms={fmt(m[\"tpot_ms\"])}  num_tokens={m[\"num_tokens\"]}  cached_tokens={m[\"cached_tokens\"]}  finish_reason={m.get(\"finish_reason\")}')
"
done
