# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

#!/bin/bash
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
# Exact input length (in tokens) for every prompt, enforced via the model's
# own tokenizer (loaded from $TOKENIZER_PATH).
INPUT_LEN=${INPUT_LEN:-512}
OUT_DIR=${OUT_DIR:-/tmp/vllm-bench-two-waves}

mkdir -p "${OUT_DIR}"

# Seed text pool A: Harry Potter opening (same text used in vllm-curl.sh).
# The worker splits these seed texts into sentences and, per request index,
# deterministically shuffles them into a distinct prompt, then
# repeats/truncates it to exactly INPUT_LEN tokens.
export PROMPT_A="Mr. and Mrs. Dursley, of number four, Privet Drive, were proud to say that they were perfectly normal, thank you very much. They were the last people you'd expect to be involved in anything strange or mysterious, because they just didn't hold with such nonsense. Mr. Dursley was the director of a firm called Grunnings, which made drills. He was a big, beefy man with hardly any neck, although he did have a very large mustache. Mrs. Dursley was thin and blonde and had nearly twice the usual amount of neck, which came in very useful as she spent so much of her time craning over garden fences, spying on the neighbors. The Dursleys had a small son called Dudley and in their opinion there was no finer boy anywhere. The Dursleys had everything they wanted, but they also had a secret, and their greatest fear was that somebody would discover it. They didn't think they could bear it if anyone found out about the Potters. Mrs. Potter was Mrs. Dursley's sister, but they hadn't met for several years; in fact, Mrs. Dursley pretended she didn't have a sister, because her sister and her good-for-nothing husband were as unDursleyish as it was possible to be. The Dursleys shuddered to think what the neighbors would say if the Potters arrived in the street. The Dursleys knew that the Potters had a small son, too, but they had never even seen him. This boy was another good reason for keeping the Potters away; they didn't want Dudley mixing with a child like that. When Mr. and Mrs. Dursley woke up on the dull, gray Tuesday our story starts, there was nothing about the cloudy sky outside to suggest that strange and mysterious things would soon be happening all over the country. Mr. Dursley hummed as he picked out his most boring tie for work, and Mrs. Dursley gossiped away happily as she wrestled a screaming Dudley into his high chair. None of them noticed a large, tawny owl flutter past the window. At half past eight, Mr. Dursley picked up his briefcase, pecked Mrs. Dursley on the cheek, and tried to kiss Dudley good-bye but missed, because Dudley was now having a tantrum and throwing his cereal at the walls."

# Seed text pool B: Pride and Prejudice opening -- unrelated content, no
# shared sentences with pool A.
export PROMPT_B="It is a truth universally acknowledged, that a single man in possession of a good fortune must be in want of a wife. However little known the feelings or views of such a man may be on his first entering a neighbourhood, this truth is so well fixed in the minds of the surrounding families, that he is considered as the rightful property of some one or other of their daughters. My dear Mr. Bennet, said his lady to him one day, have you heard that Netherfield Park is let at last? Mr. Bennet replied that he had not. But it is, returned she; for Mrs. Long has just been here, and she told me all about it. Mr. Bennet made no answer. Do not you want to know who has taken it? cried his wife impatiently. You want to tell me, and I have no objection to hearing it. This was invitation enough. Why, my dear, you must know, Mrs. Long says that Netherfield is taken by a young man of large fortune from the north of England; that he came down on Monday in a chaise and four to see the place, and was so much delighted with it that he agreed with Mr. Morris immediately; that he is to take possession before Michaelmas, and some of his servants are to be in the house by the end of next week. What is his name? Bingley. Is he married or single? Oh! single, my dear, to be sure! A single man of large fortune; four or five thousand a year. What a fine thing for our girls!"

export MODEL TOKENIZER_PATH HOST PORT KEY MAX_TOKENS OUT_DIR INPUT_LEN NUM_REQUESTS

run_wave() {
  local wave_name=$1
  echo "=== ${wave_name}: sending ${NUM_REQUESTS} concurrent (distinct) requests ==="
  WAVE_NAME="${wave_name}" python3 "$(dirname "$0")/vllm_two_waves_worker.py"
  echo "=== ${wave_name}: done, result saved to ${OUT_DIR}/${wave_name}.json ==="
}

run_wave "wave1"
run_wave "wave2"

echo
echo "--- Summary ---"
for wave_name in wave1 wave2; do
  echo "${wave_name}:"
  python3 -c "
import json
with open('${OUT_DIR}/${wave_name}.json') as f:
    data = json.load(f)
for req_id, m in sorted(data.items(), key=lambda kv: int(kv[0].removeprefix('req'))):
    print(f'  {req_id}: ttft_ms={m[\"ttft_ms\"]:.2f}  tpot_ms={m[\"tpot_ms\"]:.2f}  num_tokens={m[\"num_tokens\"]}  cached_tokens={m[\"cached_tokens\"]}')
"
done
