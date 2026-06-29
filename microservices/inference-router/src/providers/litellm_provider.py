# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Litellm-based provider adapter.

Uses litellm to call any provider it natively supports (``hosted_vllm``,
``openai``, ``ollama``, ``minimax``, ``anthropic``, ...). The chat/stream
logic that previously lived in RouterLLM + local_client/cloud_client is
collapsed into this single adapter, since DecisionEngine now handles routing.
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Any, AsyncIterator, Dict, Iterator, List

import litellm

from src.config.base import ProviderConfig
from src.exceptions import ProviderError
from src.models import (
    ChatCompletionChoice,
    ChatCompletionMessage,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionStreamChunk,
    ChatCompletionUsage,
)
from src.providers.base import ProviderAdapter, ProviderMetadata


logger = logging.getLogger(__name__)

# Preserve pass-through of provider-specific extension params (e.g. vLLM's
# best_of, repetition_penalty, guided_json). Without this, litellm would
# silently drop unrecognised fields.
litellm.drop_params = False

# Request fields handled by the adapter directly; everything else is passed
# through to litellm verbatim (preserves OpenAI / vLLM extensions).
_RESERVED_REQUEST_FIELDS = frozenset({"model", "messages", "stream"})


class LitellmProvider(ProviderAdapter):
    """ProviderAdapter that delegates chat completions to litellm."""

    def __init__(self, provider_config: ProviderConfig):
        super().__init__(
            name=provider_config.name,
            metadata=ProviderMetadata.from_mapping(provider_config.metadata or {}),
        )
        settings = provider_config.settings or {}
        auth = settings.get("auth") or {}

        self.provider_type = provider_config.type
        # `model` is the backend model identifier passed to litellm
        self.model = provider_config.model
        self.endpoint = settings.get("endpoint")
        self.timeout = settings.get("timeout")
        # Auth: scheme ∈ {"bearer" (default), "api_key", "none"}.
        # For "none" we explicitly drop any api_key so we never authenticate.
        self.auth_scheme = (auth.get("scheme") or "bearer").lower()
        self.api_key = None if self.auth_scheme == "none" else auth.get("api_key")
        self.custom_headers = dict(auth.get("custom_headers") or {})

    async def chat(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        messages, kwargs = self._prepare_call(request)
        try:
            raw = self._call_litellm(messages, stream=False, **kwargs)
        except Exception as exc:
            logger.error(f"litellm chat failed for provider={self.name}: {exc}")
            raise ProviderError(f"Litellm chat failed: {exc}") from exc
        return self._to_chat_response(raw)

    async def chat_stream(
        self, request: ChatCompletionRequest
    ) -> AsyncIterator[ChatCompletionStreamChunk]:
        messages, kwargs = self._prepare_call(request)
        try:
            stream_iter = self._call_litellm(messages, stream=True, **kwargs)
        except Exception as exc:
            logger.error(f"litellm stream failed for provider={self.name}: {exc}")
            raise ProviderError(f"Litellm stream failed: {exc}") from exc

        for chunk in stream_iter:
            yield self._to_stream_chunk(chunk)

    async def list_models(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": self.model,
                "object": "model",
                "created": int(time.time()),
                "owned_by": self.name,
            }
        ]

    def _call_litellm(
        self, messages: list[dict], *, stream: bool, **kwargs
    ) -> dict | Iterator[dict]:
        """Invoke litellm.completion and return raw OpenAI-format dict(s).

        The model identifier passed to litellm is composed as
        ``<provider_type>/<model>`` directly from config. For self-hosted
        OpenAI-compatible servers, set ``type: openai`` in config and point
        ``settings.endpoint`` at the server's ``/v1`` base.
        """
        model = f"{self.provider_type}/{self.model}"
        api_base = self.endpoint.rstrip("/") if self.endpoint else None

        # Self-hosted OpenAI-compatible servers (vLLM, OpenVINO, ...) often
        # don't require auth, but litellm's OpenAI client expects an api_key
        # — supply a placeholder so the request goes through. Skip the
        # placeholder when auth.scheme is explicitly "none".
        api_key = self.api_key
        if self.provider_type == "openai" and not api_key and self.auth_scheme != "none":
            api_key = "fake"

        completion_kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": stream,
            **kwargs,
        }
        if api_base:
            completion_kwargs["api_base"] = api_base
        if api_key:
            completion_kwargs["api_key"] = api_key
        if self.timeout is not None:
            # litellm reads ``timeout`` (seconds) per request.
            completion_kwargs.setdefault("timeout", self.timeout)
        if self.custom_headers:
            # Merge configured auth headers with any caller-supplied extra_headers.
            existing = completion_kwargs.get("extra_headers") or {}
            merged = {**self.custom_headers, **existing}
            completion_kwargs["extra_headers"] = merged
        if stream:
            completion_kwargs.setdefault("stream_options", {"include_usage": True})

        logger.debug(f"litellm.completion model={model} api_base={api_base} stream={stream}")
        result = litellm.completion(**completion_kwargs)

        if stream:
            return self._iter_stream_chunks(result)
        return self._to_dict(result)

    def _prepare_call(self, request: ChatCompletionRequest) -> tuple[list[dict], dict]:
        """Serialize request into (messages, kwargs) for litellm."""
        data = request.model_dump(exclude_none=True)
        messages = data.pop("messages", [])
        for key in _RESERVED_REQUEST_FIELDS:
            data.pop(key, None)
        return messages, data

    @staticmethod
    def _to_dict(response) -> dict:
        if isinstance(response, dict):
            return response
        if hasattr(response, "model_dump"):
            return response.model_dump()
        if hasattr(response, "dict"):
            return response.dict()
        return dict(response)

    def _iter_stream_chunks(self, stream) -> Iterator[dict]:
        for chunk in stream:
            yield self._patch_delta_role(self._to_dict(chunk))

    @staticmethod
    def _patch_delta_role(chunk: dict) -> dict:
        """Force delta.role to 'assistant' when litellm emits role=None.

        Some providers/litellm versions emit role=None on streaming deltas,
        which downstream OpenAI clients reject. Coerce to 'assistant'.
        """
        for choice in chunk.get("choices") or ():
            delta = choice.get("delta")
            if isinstance(delta, dict) and delta.get("role") is None:
                delta["role"] = "assistant"
        return chunk

    def _to_chat_response(self, raw: dict) -> ChatCompletionResponse:
        choices = []
        for ch in raw.get("choices") or []:
            message_data = ch.get("message") or {}
            choices.append(
                ChatCompletionChoice(
                    index=ch.get("index", 0),
                    message=ChatCompletionMessage(
                        role=message_data.get("role") or "assistant",
                        content=message_data.get("content"),
                        name=message_data.get("name"),
                        tool_calls=message_data.get("tool_calls"),
                    ),
                    finish_reason=ch.get("finish_reason"),
                    logprobs=ch.get("logprobs"),
                )
            )

        usage_data = raw.get("usage") or {}
        usage = ChatCompletionUsage(
            prompt_tokens=usage_data.get("prompt_tokens", 0),
            completion_tokens=usage_data.get("completion_tokens", 0),
            total_tokens=usage_data.get(
                "total_tokens",
                usage_data.get("prompt_tokens", 0) + usage_data.get("completion_tokens", 0),
            ),
        )

        return ChatCompletionResponse(
            id=raw.get("id") or f"chatcmpl-{uuid.uuid4().hex[:24]}",
            created=raw.get("created") or int(time.time()),
            model=raw.get("model") or self.model,
            choices=choices,
            usage=usage,
            system_fingerprint=raw.get("system_fingerprint"),
        )

    def _to_stream_chunk(self, raw: dict) -> ChatCompletionStreamChunk:
        # Forward ``usage`` (and any other backend-emitted fields like
        # ``service_tier``) untouched. ``ChatCompletionStreamChunk`` has
        # ``extra="allow"`` so they survive the round-trip via model_dump().
        kwargs = {
            "id": raw.get("id") or f"chatcmpl-{uuid.uuid4().hex[:24]}",
            "created": raw.get("created") or int(time.time()),
            "model": raw.get("model") or self.model,
            "choices": raw.get("choices") or [],
            "system_fingerprint": raw.get("system_fingerprint"),
        }
        for key, value in raw.items():
            if key not in kwargs and value is not None:
                kwargs[key] = value
        return ChatCompletionStreamChunk(**kwargs)
