# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""LLM client for okf_producer. Same wire shape as extract_okf.call_llm, plus:
  - proxy isolation (trust_env=False) — the corporate proxy turns 127.0.0.1 into
    403 otherwise; the CLI also sets no_proxy in-process (belt AND suspenders);
  - OpenAI tool-calling (tools=[...] / tool_choice), returning the whole choice so
    the agent loop can branch on finish_reason and read message.tool_calls.
"""
from __future__ import annotations

import json
import re

import httpx


class ContextOverflowError(Exception):
    """Raised when the model rejects the request because the prompt (accumulated
    conversation history) exceeds its context window. The driver catches this to
    shrink the batch budget and retry, rather than crashing the whole run."""


# substrings vLLM / OpenAI-compatible servers use in the 400 body when the prompt
# is too long. Matched case-insensitively against the error text.
_OVERFLOW_MARKERS = (
    "maximum context length",
    "context length",
    "context window",
    "too long",
    "reduce the length",
    "max_model_len",
    "longer than the maximum",
)


class LLMClient:
    def __init__(self, cfg_llm: dict):
        # trust_env=False: do NOT apply http(s)_proxy env to the 127.0.0.1 call.
        self._http = httpx.Client(
            trust_env=False, timeout=float(cfg_llm.get("timeout", 600.0))
        )
        self._llm = cfg_llm

    def close(self) -> None:
        self._http.close()

    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        tool_choice: str = "auto",
        max_tokens: int | None = None,
    ) -> dict:
        """POST /chat/completions. Returns choices[0] = {message:{content,tool_calls},
        finish_reason}."""
        llm = self._llm
        body: dict = {
            "model": llm["model"],
            "messages": messages,
            "temperature": llm.get("temperature", 0.0),
            "max_tokens": max_tokens or llm.get("max_tokens", 4096),
        }
        # Qwen3.5-122B thinks first by default and can burn the whole budget on
        # <think>. vLLM's chat_template_kwargs turns it off so tool calls come out
        # directly (faster, no timeout). Honor the config's enable_thinking knob.
        if not llm.get("enable_thinking", False):
            body["chat_template_kwargs"] = {"enable_thinking": False}
        if tools:
            body["tools"] = tools
            body["tool_choice"] = tool_choice
        resp = self._http.post(
            f"{llm['base_url'].rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {llm.get('api_key', 'EMPTY')}"},
            json=body,
        )
        if resp.status_code >= 400:
            text = resp.text or ""
            if resp.status_code == 400 and any(
                m in text.lower() for m in _OVERFLOW_MARKERS
            ):
                raise ContextOverflowError(text[:500])
            resp.raise_for_status()
        return resp.json()["choices"][0]


def parse_json(text: str) -> dict:
    """Tolerant: strip code fences / prose / <think>, grab the first {...} block.
    Copied from extract_okf.parse_json (L160-170)."""
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object found")
    return json.loads(text[start : end + 1])


def approx_tokens(messages: list[dict], chars_per_token: float = 3.0) -> int:
    """Cheap estimate of a message list's token size (for the history soft-gate).
    Serializes to JSON and divides by chars_per_token — no tokenizer call."""
    try:
        n = len(json.dumps(messages, ensure_ascii=False))
    except Exception:
        n = sum(len(str(m.get("content", ""))) for m in messages)
    return int(n / (chars_per_token or 3.0))
