# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""LLM client — thin wrapper over OpenAI-compatible API (vlm-openvino-serving)."""

import os
import json
import logging
from typing import Optional

log = logging.getLogger(__name__)

# Runtime env vars
_LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "http://apm-vlm:8000/v1")
_LLM_MODEL_NAME = os.environ.get("LLM_MODEL_NAME", "Phi-4-mini-instruct")
_LLM_API_KEY = os.environ.get("LLM_API_KEY", "no-key-needed")
_LLM_MODE = os.environ.get("LLM_MODE", "llm")  # "llm" | "fallback"
_FALLBACK_POLICY_PATH = os.environ.get(
    "FALLBACK_POLICY_PATH",
    os.path.join(os.environ.get("USE_CASE_CONFIGS_DIR", "/configs"), "policy_fallback.json"),
)


def create_client():
    """Return an OpenAI client pointed at the vlm-openvino-serving endpoint."""
    from openai import OpenAI  # lazy import — not required in fallback mode
    import httpx
    # trust_env=False prevents httpx from picking up HTTP_PROXY env vars
    # (vlm-openvino-serving is an internal Docker service, no proxy needed)
    return OpenAI(
        base_url=_LLM_BASE_URL,
        api_key=_LLM_API_KEY,
        http_client=httpx.Client(trust_env=False),
    )


def is_fallback_mode() -> bool:
    return _LLM_MODE.lower() == "fallback"


def load_fallback_policy(path: str | None = None) -> dict:
    target = path or _FALLBACK_POLICY_PATH
    with open(target, "r") as f:
        return json.load(f)


def call_llm(
    system_prompt: str,
    user_message: str,
    model: str | None = None,
    max_tokens: int = 2048,
    temperature: float = 0.2,
) -> str:
    """Send a prompt to the LLM and return the response text.

    In fallback mode this is not called — agents use rule-based logic instead.
    """
    client = create_client()
    response = client.chat.completions.create(
        model=model or _LLM_MODEL_NAME,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_message},
        ],
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return response.choices[0].message.content
