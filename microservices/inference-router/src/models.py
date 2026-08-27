# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Pydantic models for OpenAI-compatible chat completion API."""

from typing import Optional, List, Dict, Any, Union, Literal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ChatCompletionRole(str, Enum):
    """Valid roles in a chat message."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
    FUNCTION = "function"


class ChatCompletionMessage(BaseModel):
    """A message in a chat completion request or response."""

    role: ChatCompletionRole
    # Content can be a plain string or an OpenAI content-parts array
    # (e.g. ``[{"type": "text", "text": "..."}, {"type": "image_url", ...}]``).
    content: Union[str, List[Dict[str, Any]], None] = None
    name: Optional[str] = None
    # Some upstream models (e.g. Qwen3) emit ``reasoning_content`` natively
    # alongside ``content``. The gateway passes it through unchanged.
    reasoning_content: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    # Required on ``role: tool`` messages to bind the result to the assistant
    # tool_call that requested it.
    tool_call_id: Optional[str] = None

    @field_validator("content", mode="before")
    @classmethod
    def _normalize_content(cls, value):
        """Validate string / OpenAI content-parts array; pass through unchanged.

        The router treats content as pure pass-through, so we only assert
        structural validity (text parts have ``text``, image_url parts have
        ``image_url``) and reject foreign part types early.
        """
        if value is None or isinstance(value, str):
            return value

        if isinstance(value, list):
            for item in value:
                if not isinstance(item, dict):
                    raise ValueError("content parts must be objects")
                part_type = item.get("type")
                if part_type not in ("text", "image_url"):
                    raise ValueError(f"unsupported content part type: {part_type}")
                if part_type == "text" and "text" not in item:
                    raise ValueError("text content parts must include 'text' field")
                if part_type == "image_url" and "image_url" not in item:
                    raise ValueError("image_url content parts must include 'image_url' field")
            return value

        raise ValueError("content must be a string or a list of content parts")


class ChatCompletionRequest(BaseModel):
    """OpenAI-compatible chat completion request.

    ``model_config = extra="allow"`` so vLLM / provider-specific extensions
    (best_of, guided_json, etc.) round-trip through the router untouched.
    """

    model_config = ConfigDict(extra="allow")

    # ``auto`` selects the configured routing policy; a backend model name
    model: str = Field(default="auto", description="Model identifier")
    messages: List[ChatCompletionMessage] = Field(..., description="List of messages")

    # === Standard OpenAI parameters ===
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=None, ge=1)
    stream: Optional[bool] = None
    stream_options: Optional[Dict[str, Any]] = None
    top_p: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    n: Optional[int] = Field(default=None, ge=1)
    stop: Optional[Union[str, List[str]]] = None
    presence_penalty: Optional[float] = Field(default=None, ge=-2.0, le=2.0)
    frequency_penalty: Optional[float] = Field(default=None, ge=-2.0, le=2.0)
    logit_bias: Optional[Dict[str, float]] = None
    user: Optional[str] = None
    seed: Optional[int] = None
    logprobs: Optional[bool] = None
    top_logprobs: Optional[int] = Field(default=None, ge=0, le=20)

    # Tool calling
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[Union[str, Dict[str, Any]]] = None
    parallel_tool_calls: Optional[bool] = None

    # Structured outputs
    response_format: Optional[Dict[str, Any]] = None

    # # === vLLM-specific parameters ===
    # best_of: Optional[int] = None
    # repetition_penalty: Optional[float] = None
    # length_penalty: Optional[float] = None
    # early_stopping: Optional[bool] = None
    # ignore_eos: Optional[bool] = None
    # min_p: Optional[float] = None
    # top_k: Optional[int] = None
    # min_tokens: Optional[int] = None
    # stop_token_ids: Optional[List[int]] = None
    # skip_special_tokens: Optional[bool] = None
    # spaces_between_special_tokens: Optional[bool] = None

    # # Guided decoding
    # guided_json: Optional[Union[str, Dict[str, Any]]] = None
    # guided_regex: Optional[str] = None
    # guided_choice: Optional[List[str]] = None
    # guided_grammar: Optional[str] = None
    # guided_decoding_backend: Optional[str] = None
    # guided_whitespace_pattern: Optional[str] = None

    extra_body: Optional[Dict[str, Any]] = None


class ChatCompletionChoice(BaseModel):
    """A single choice in a chat completion response."""

    index: int
    message: ChatCompletionMessage
    finish_reason: str = "stop"
    logprobs: Optional[Dict[str, Any]] = None


class ChatCompletionUsage(BaseModel):
    """Token usage information for a chat completion."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatCompletionResponse(BaseModel):
    """OpenAI-compatible chat completion response."""

    model_config = ConfigDict(extra="allow")

    id: str
    object: Literal["chat.completion"] = "chat.completion"
    created: int
    model: str
    choices: List[ChatCompletionChoice]
    usage: Optional[ChatCompletionUsage] = None
    system_fingerprint: Optional[str] = None


class ChatCompletionStreamChunk(BaseModel):
    """A single chunk in a streaming chat completion response."""

    model_config = ConfigDict(extra="allow")

    id: str
    object: Literal["chat.completion.chunk"] = "chat.completion.chunk"
    created: int
    model: str
    choices: List[Dict[str, Any]]
    system_fingerprint: Optional[str] = None


class ModelListResponse(BaseModel):
    """Response for list models endpoint."""

    object: Literal["list"] = "list"
    data: List[Dict[str, Any]]


class PluginSettingsResponse(BaseModel):
    """Plugin settings response."""

    model_config = ConfigDict(extra="allow")


class PluginResponse(BaseModel):
    """Response for a single plugin configuration."""

    name: str = Field(..., description="Plugin name")
    node: str = Field(..., description="Plugin node selector")
    enabled: bool = Field(default=True, description="Whether plugin is enabled")
    trigger: str = Field(
        default="prerouting",
        description="Trigger phase: prerouting, postrouting, or postresponse",
    )
    settings: PluginSettingsResponse = Field(default_factory=PluginSettingsResponse)


class PluginListResponse(BaseModel):
    """Response for list plugins endpoint."""

    object: Literal["list"] = "list"
    data: List[PluginResponse]


class PluginNodeResponse(BaseModel):
    """A registered plugin type (node) available in code."""

    node: str = Field(..., description="Plugin type key (plugin_type())")
    plugin_group: str = Field(default="", description="Plugin family/group key")
    description: str = Field(default="", description="Plugin class docstring")
    settings_schema: Dict[str, Any] = Field(
        default_factory=dict, description="JSON schema for this node's settings"
    )


class PluginNodeListResponse(BaseModel):
    """Response for the registered plugin nodes endpoint."""

    object: Literal["list"] = "list"
    data: List[PluginNodeResponse]


class PluginConfigUpdateRequest(BaseModel):
    """Request to update plugin configuration.

    ``extra="ignore"`` so the body returned by ``GET /plugins/{node}/{name}``
    round-trips as a ``POST`` payload: the extra keys a GET carries (``name``,
    ``node``, ``metrics``, ...) are silently dropped rather than rejected.
    """

    model_config = ConfigDict(extra="ignore")

    enabled: Optional[bool] = None
    trigger: Optional[Literal["prerouting", "postrouting", "postresponse"]] = None
    settings: Optional[PluginSettingsResponse] = None


class ProviderSettingsResponse(BaseModel):
    """Provider settings response (endpoint, timeout, auth, ...)."""

    model_config = ConfigDict(extra="allow")


class ProviderMetadataResponse(BaseModel):
    """Provider metadata response (labels, cost, performance, capability, ...)."""

    model_config = ConfigDict(extra="allow")


class ProviderResponse(BaseModel):
    """Response for a single provider configuration."""

    name: str = Field(..., description="Provider name (unique identifier)")
    type: str = Field(..., description="Provider type, e.g. 'hosted_vllm', 'openai'")
    model: str = Field(..., description="Backend model identifier")
    enabled: bool = Field(default=True, description="Whether provider is enabled")
    metadata: ProviderMetadataResponse = Field(default_factory=ProviderMetadataResponse)
    settings: ProviderSettingsResponse = Field(default_factory=ProviderSettingsResponse)
    extra: Dict[str, Any] = Field(
        default_factory=dict,
        description="Generic passthrough config (e.g. extra.management_endpoint)",
    )


class ProviderListResponse(BaseModel):
    """Response for list providers endpoint."""

    object: Literal["list"] = "list"
    data: List[ProviderResponse]


class ProviderConfigUpdateRequest(BaseModel):
    """Request to create or update provider configuration.

    ``type`` and ``model`` are optional here so partial updates (e.g. toggling
    ``enabled``) need not resend them, but they are required when creating a
    brand new provider — the endpoint enforces that.

    ``extra="ignore"`` so the body returned by ``GET /providers/{name}``
    round-trips as a ``POST`` payload: the extra ``name`` key (and any others)
    a GET carries are silently dropped rather than rejected. Note ``GET``
    redacts secrets (``api_key: "***REDACTED***"``), so on round-trip omit or
    re-supply secret fields — re-POSTing verbatim would persist the mask.
    """

    model_config = ConfigDict(extra="ignore")

    type: Optional[str] = None
    model: Optional[str] = None
    enabled: Optional[bool] = None
    metadata: Optional[ProviderMetadataResponse] = None
    settings: Optional[ProviderSettingsResponse] = None
    # Replaced wholesale (like ``settings``/``metadata``) when present.
    extra: Optional[Dict[str, Any]] = None


class ConfigResponse(BaseModel):
    """Response for configuration management endpoints."""

    object: Literal["config"] = "config"
    data: Dict[str, Any]
    path: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)


class RoutingConfigResponse(BaseModel):
    """Response for the routing section of the configuration.

    Only ``policy`` is exposed: it is the documented routing knob (must name an
    entry in ``policy.yaml``). The lower-level ``strategy`` fallback is preserved
    on disk but not managed through this API.
    """

    policy: Optional[str] = Field(default=None, description="Routing policy name (must exist in policy.yaml)")


class RoutingConfigUpdateRequest(BaseModel):
    """Request to update the routing policy.

    ``extra="ignore"`` so the body returned by ``GET /routing`` round-trips as a
    ``POST`` payload.
    """

    model_config = ConfigDict(extra="ignore")

    policy: Optional[str] = None
