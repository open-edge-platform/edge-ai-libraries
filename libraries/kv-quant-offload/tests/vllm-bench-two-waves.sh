#!/bin/bash
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Run inside the vllm-kvweave container (see integration/lmcache/vllm/vllm-start.sh DEBUG=1).
#
# Sends NUM_REQUESTS distinct concurrent requests (wave 1), then the exact same
# requests again (wave 2), and reports per-request TTFT/TPOT/cached_tokens for both.
# cached_tokens needs the vLLM server started with --enable-prompt-tokens-details.
# Requires python3 with transformers (exact-token-length prompts via the model tokenizer).
#
# Example (2 requests, 40960-token prompts, L1 test):
#   WARMUP=1 NUM_REQUESTS=2 TOKENIZER_PATH=/models/Qwen3.5-9B INPUT_LEN=40960 MAX_TOKENS=128 bash ./vllm-bench-two-waves.sh

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
#   SERVE=Qwen3.5-9B TOKENIZER_PATH=/models MODEL=Qwen3.5-9B \
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
#   SERVE (Qwen3.5-9B)      Served model name; must match --served-model-name.
#   MODEL (Qwen3.5-9B)      Model name/subdir under TOKENIZER_PATH; must match
#                           the vLLM server's --model basename.
#   TOKENIZER_PATH (/models)  Directory containing MODEL. Joined as
#                           $TOKENIZER_PATH/$MODEL to form the path
#                           AutoTokenizer and `vllm bench serve` resolve.
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
# ---------------------------------------------------------------------------
set -euo pipefail

SERVE=${SERVE:-Qwen3.5-9B}
MODEL=${MODEL:-Qwen3.5-9B}
TOKENIZER_PATH=${TOKENIZER_PATH:-/models}
HOST=${HOST:-localhost}
PORT=${PORT:-8000}
KEY=${KEY:-sk-xxx}
MAX_TOKENS=${MAX_TOKENS:-256}
NUM_REQUESTS=${NUM_REQUESTS:-2}
SEQ=${SEQ:-0}
INPUT_LEN=${INPUT_LEN:-512}
OUT_DIR=${OUT_DIR:-/tmp/vllm-bench-two-waves}

WARMUP=${WARMUP:-1}
RESET_PREFIX_CACHE=${RESET_PREFIX_CACHE:-1}
TEST_OBJECT=${TEST_OBJECT:-l1}
LMCACHE_HTTP_URL=${LMCACHE_HTTP_URL:-http://localhost:8090}

maybe_clear_l1_cache() {
if [ "${TEST_OBJECT}" = "l2" ]; then
  curl -s -X POST 'http://localhost:8000/reset_prefix_cache' >/dev/null || \
  echo "=== reset_prefix_cache unavailable; start vLLM with VLLM_SERVER_DEV_MODE=1 to enable it ==="
  sleep 5
  curl -sf -X POST "${LMCACHE_HTTP_URL}/cache/clear" || \
    echo "=== clear-cache unavailable; continuing without clearing LMCache L1 ==="
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
    # +1 request to force eviction of earlier prefixes.
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
    --model "${TOKENIZER_PATH}/${MODEL}" \
    --served-model-name "${SERVE}" \
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

# Seed texts A (Harry Potter) and B (Pride and Prejudice); see vllm_two_waves_worker.py.
export PROMPT_A="Mr. and Mrs. Dursley, of number four, Privet Drive, were proud to say that they were perfectly normal, thank you very much. They were the last people you'd expect to be involved in anything strange or mysterious, because they just didn't hold with such nonsense. Mr. Dursley was the director of a firm called Grunnings, which made drills. He was a big, beefy man with hardly any neck, although he did have a very large mustache. Mrs. Dursley was thin and blonde and had nearly twice the usual amount of neck, which came in very useful as she spent so much of her time craning over garden fences, spying on the neighbors. The Dursleys had a small son called Dudley and in their opinion there was no finer boy anywhere. The Dursleys had everything they wanted, but they also had a secret, and their greatest fear was that somebody would discover it. They didn't think they could bear it if anyone found out about the Potters. Mrs. Potter was Mrs. Dursley's sister, but they hadn't met for several years; in fact, Mrs. Dursley pretended she didn't have a sister, because her sister and her good-for-nothing husband were as unDursleyish as it was possible to be. The Dursleys shuddered to think what the neighbors would say if the Potters arrived in the street. The Dursleys knew that the Potters had a small son, too, but they had never even seen him. This boy was another good reason for keeping the Potters away; they didn't want Dudley mixing with a child like that. When Mr. and Mrs. Dursley woke up on the dull, gray Tuesday our story starts, there was nothing about the cloudy sky outside to suggest that strange and mysterious things would soon be happening all over the country. Mr. Dursley hummed as he picked out his most boring tie for work, and Mrs. Dursley gossiped away happily as she wrestled a screaming Dudley into his high chair. None of them noticed a large, tawny owl flutter past the window. At half past eight, Mr. Dursley picked up his briefcase, pecked Mrs. Dursley on the cheek, and tried to kiss Dudley good-bye but missed, because Dudley was now having a tantrum and throwing his cereal at the walls."

export PROMPT_B="It is a truth universally acknowledged, that a single man in possession of a good fortune must be in want of a wife. However little known the feelings or views of such a man may be on his first entering a neighbourhood, this truth is so well fixed in the minds of the surrounding families, that he is considered as the rightful property of some one or other of their daughters. My dear Mr. Bennet, said his lady to him one day, have you heard that Netherfield Park is let at last? Mr. Bennet replied that he had not. But it is, returned she; for Mrs. Long has just been here, and she told me all about it. Mr. Bennet made no answer. Do not you want to know who has taken it? cried his wife impatiently. You want to tell me, and I have no objection to hearing it. This was invitation enough. Why, my dear, you must know, Mrs. Long says that Netherfield is taken by a young man of large fortune from the north of England; that he came down on Monday in a chaise and four to see the place, and was so much delighted with it that he agreed with Mr. Morris immediately; that he is to take possession before Michaelmas, and some of his servants are to be in the house by the end of next week. What is his name? Bingley. Is he married or single? Oh! single, my dear, to be sure! A single man of large fortune; four or five thousand a year. What a fine thing for our girls!"

export MODEL SERVE TOKENIZER_PATH HOST PORT KEY MAX_TOKENS OUT_DIR INPUT_LEN NUM_REQUESTS SEQ

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
  --model "${TOKENIZER_PATH}/${MODEL}" \
  --served-model-name "${SERVE}" \
  --dataset-name random \
  --random-input-len ${INPUT_LEN} \
  --random-output-len 64 \
  --num-prompts 1 \
  --max-concurrency 2 \
  --ignore-eos
echo "=== warmup: done, clearing LMCache L1 cache ==="
sleep 5
curl -sf -X POST "${LMCACHE_HTTP_URL}/cache/clear" || \
  echo "=== clear-cache unavailable; continuing without clearing LMCache L1 ==="
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
