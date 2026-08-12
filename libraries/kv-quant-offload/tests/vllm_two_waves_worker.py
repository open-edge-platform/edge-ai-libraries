# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Worker invoked by vllm-bench-two-waves.sh.

Sends NUM_REQUESTS concurrent streaming chat-completion requests against a
running vLLM server, measuring each request's own TTFT (time to first
content token) and TPOT (mean inter-token latency over the remaining
tokens).

Each request gets a distinct, deterministically generated prompt: sentences
from two fixed seed texts (Harry Potter / Pride and Prejudice openings) are
pooled together and shuffled with a per-request-index seed, so within one
wave every request's prompt is different (no shared prefix -> no prefix/KV
cache hits between them), while the same request index produces the exact
same prompt on every invocation (wave) -- letting you compare wave1 (cold)
vs wave2 (e.g. KV-cache-warmed) latency for "the same" request. Each
generated prompt is then repeated/truncated (via the model's own tokenizer,
loaded from $MODEL) to exactly INPUT_LEN tokens.

Also reports each request's cached_tokens (vLLM local prefix cache + LMCache
external cache hits, combined -- the server does not split the two out), via
usage.prompt_tokens_details.cached_tokens. This requires vLLM to be started
with --enable-prompt-tokens-details (that flag is off by default; without it
cached_tokens will be reported as None).
"""

import json
import os
import random
import re
import threading
import time
import urllib.request

from transformers import AutoTokenizer

BASE_URL = f"http://{os.environ['HOST']}:{os.environ['PORT']}"
# Served model name, used as the "model" field in API requests.
MODEL = os.environ["MODEL"]
# Local path/name AutoTokenizer can resolve; defaults to MODEL for backward
# compatibility, but should be set separately whenever MODEL is a
# served-model-name that differs from the tokenizer's local path.
TOKENIZER_PATH = os.environ.get("TOKENIZER_PATH", MODEL)
KEY = os.environ["KEY"]
MAX_TOKENS = int(os.environ["MAX_TOKENS"])
OUT_DIR = os.environ["OUT_DIR"]
WAVE_NAME = os.environ["WAVE_NAME"]
INPUT_LEN = int(os.environ["INPUT_LEN"])
NUM_REQUESTS = int(os.environ["NUM_REQUESTS"])
SEQ = os.environ.get("SEQ", "0") not in {"", "0", "false", "False"}

_tokenizer = AutoTokenizer.from_pretrained(TOKENIZER_PATH, trust_remote_code=True)

_SEED_TEXTS = [os.environ["PROMPT_A"], os.environ["PROMPT_B"]]


def _split_sentences(text: str) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    return [s for s in sentences if s]


_SENTENCE_POOL = [s for text in _SEED_TEXTS for s in _split_sentences(text)]


def _prompt_for_request(req_index: int) -> str:
    """Deterministically build a distinct base prompt for one request index."""
    rng = random.Random(f"vllm-two-waves-{req_index}")
    sentences = _SENTENCE_POOL[:]
    rng.shuffle(sentences)
    return " ".join(sentences)


def _to_exact_token_len(base_text: str, num_tokens: int) -> str:
    """Repeat base_text as needed, then truncate to exactly num_tokens tokens."""
    ids = _tokenizer.encode(base_text, add_special_tokens=False)
    if not ids:
        raise ValueError("base_text encoded to zero tokens")
    while len(ids) < num_tokens:
        ids += _tokenizer.encode(" " + base_text, add_special_tokens=False)
    ids = ids[:num_tokens]
    return _tokenizer.decode(ids)


PROMPTS = {
    f"req{i}": _to_exact_token_len(_prompt_for_request(i), INPUT_LEN)
    for i in range(NUM_REQUESTS)
}

results = {}
lock = threading.Lock()


def run_one(req_id, prompt):
    body = json.dumps(
        {
            "model": MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "stream": True,
            "stream_options": {"include_usage": True},
            "max_tokens": MAX_TOKENS,
            "min_tokens": MAX_TOKENS,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE_URL}/v1/chat/completions",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {KEY}",
        },
    )
    start = time.perf_counter()
    token_times = []
    cached_tokens = None
    finish_reason = None
    generated_text = []
    with urllib.request.urlopen(req) as resp:
        for raw_line in resp:
            line = raw_line.decode("utf-8").strip()
            if not line or not line.startswith("data:"):
                continue
            payload = line[len("data:"):].strip()
            if payload == "[DONE]":
                break
            chunk = json.loads(payload)
            choices = chunk.get("choices") or []
            if choices:
                delta = choices[0].get("delta") or {}
                if delta.get("content"):
                    token_times.append(time.perf_counter())
                    generated_text.append(delta["content"])
                if choices[0].get("finish_reason"):
                    finish_reason = choices[0]["finish_reason"]
            usage = chunk.get("usage")
            if usage:
                details = usage.get("prompt_tokens_details") or {}
                cached_tokens = details.get("cached_tokens")
    with lock:
        results[req_id] = {
            "start": start,
            "token_times": token_times,
            "cached_tokens": cached_tokens,
            "finish_reason": finish_reason,
            "generated_text": "".join(generated_text),
        }


def main():
    if SEQ:
        for rid, p in PROMPTS.items():
            run_one(rid, p)
    else:
        threads = [
            threading.Thread(target=run_one, args=(rid, p))
            for rid, p in PROMPTS.items()
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    out = {}
    for req_id, data in results.items():
        start = data["start"]
        tt = data["token_times"]
        if not tt:
            out[req_id] = {
                "ttft_ms": None,
                "tpot_ms": None,
                "num_tokens": 0,
                "cached_tokens": data.get("cached_tokens"),
                "finish_reason": data.get("finish_reason"),
                "generated_text": data.get("generated_text"),
            }
            continue
        ttft_ms = (tt[0] - start) * 1000.0
        if len(tt) > 1:
            itls = [(tt[i] - tt[i - 1]) * 1000.0 for i in range(1, len(tt))]
            tpot_ms = sum(itls) / len(itls)
        else:
            tpot_ms = 0.0
        out[req_id] = {
            "ttft_ms": ttft_ms,
            "tpot_ms": tpot_ms,
            "num_tokens": len(tt),
            "cached_tokens": data.get("cached_tokens"),
            "finish_reason": data.get("finish_reason"),
            "generated_text": data.get("generated_text"),
        }

    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, f"{WAVE_NAME}.json")
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
