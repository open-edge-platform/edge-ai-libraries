# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""OpenAI-compatible chat client with tool calling for the OKF extractor."""
from __future__ import annotations

import json
import re

import httpx


class ContextOverflowError(Exception):
    """Raised when the prompt exceeds the model's context window."""


# Lowercase substrings OpenAI-compatible servers put in a 400 body for an over-long prompt.
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
        # trust_env=False: proxy env vars would break calls to 127.0.0.1.
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
        """POST /chat/completions and return ``choices[0]``."""
        llm = self._llm
        body: dict = {
            "model": llm["model"],
            "messages": messages,
            "temperature": llm.get("temperature", 0.0),
            "max_tokens": max_tokens or llm.get("max_tokens", 4096),
        }
        # Disable vLLM thinking mode unless configured, so the token budget is not spent on <think>.
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
    """Strip code fences and <think> blocks, then parse the outermost {...} block."""
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object found")
    return json.loads(text[start : end + 1])


def approx_tokens(messages: list[dict], chars_per_token: float = 3.0) -> int:
    """Rough token count of a message list from its JSON length, without a tokenizer."""
    try:
        n = len(json.dumps(messages, ensure_ascii=False))
    except Exception:
        n = sum(len(str(m.get("content", ""))) for m in messages)
    return int(n / (chars_per_token or 3.0))
