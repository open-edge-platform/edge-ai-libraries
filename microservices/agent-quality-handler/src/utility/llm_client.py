# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""LLM client — thin wrapper over OpenAI-compatible API (openvino-serving)."""

import json
import logging

from .runtime_config import load_runtime_settings

log = logging.getLogger(__name__)


def create_client():
    """Return an OpenAI client pointed at the openvino-serving endpoint."""
    from openai import OpenAI  # lazy import — not required in fallback mode
    import httpx
    settings = load_runtime_settings()
    return OpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        http_client=httpx.Client(trust_env=False),
    )


def is_fallback_mode() -> bool:
    return load_runtime_settings().llm_mode == "fallback"


def load_fallback_policy(path: str | None = None) -> dict:
    target = path or load_runtime_settings().fallback_policy_path
    with open(target, "r", encoding="utf-8") as f:
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
    settings = load_runtime_settings()
    client = create_client()
    response = client.chat.completions.create(
        model=model or settings.llm_model_name,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_message},
        ],
        max_tokens=max_tokens,
        temperature=temperature,
    )
    content = response.choices[0].message.content
    if not isinstance(content, str) or not content:
        raise ValueError("LLM returned an empty response")
    return content
