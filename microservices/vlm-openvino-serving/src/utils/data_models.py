# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field

from .common import settings


class MessageContentText(BaseModel):
    """
    Represents a text message content.

    Attributes:
        type (str): The type of the content (e.g., "text").
        text (str): The text content.
    """

    type: str
    text: str


class MessageContentImageUrl(BaseModel):
    """
    Represents an image URL message content.

    Attributes:
        type (str): The type of the content (e.g., "image_url").
        image_url (Dict[str, str]): A dictionary containing the image URL.
    """

    type: str
    image_url: Dict[str, str]


class MessageContentVideo(BaseModel):
    """
    Represents a video message content.

    Attributes:
        type (str): The type of the content (e.g., "video").
        video (List[str]): A list of video frames.
    """

    type: str
    video: List[str]


class MessageContentVideoUrl(BaseModel):
    """
    Represents a video URL message content.

    Attributes:
        type (str): The type of the content (e.g., "video_url").
        video_url (Dict[str, str]): A dictionary containing the video URL.
        max_pixels (Optional[Union[int, str]]): The maximum number of pixels for the video.
        fps (Optional[float]): The frames per second for the video.
    """

    type: str
    video_url: Dict[str, str]
    max_pixels: Optional[Union[int, str]] = None
    fps: Optional[float] = None


class Message(BaseModel):
    """
    Represents a message in a chat.

    Attributes:
        role (str): The role of the message sender (e.g., "user").
        content (Union[str, List[Union[str, MessageContentText, MessageContentImageUrl, MessageContentVideo, MessageContentVideoUrl]]]):
            The content of the message.
    """

    role: str
    content: Union[
        str,
        List[
            Union[
                str,
                MessageContentText,
                MessageContentImageUrl,
                MessageContentVideo,
                MessageContentVideoUrl,
            ]
        ],
    ]


class ChatRequest(BaseModel):
    """
    Represents a chat request.

    Attributes:
        messages (List[Message]): A list of messages in the chat.
        model (str): The model to be used for the chat.
        repetition_penalty (Optional[float]): The penalty for repetition.
        presence_penalty (Optional[float]): The penalty for presence.
        frequency_penalty (Optional[float]): The penalty for frequency.
        max_completion_tokens (Optional[int]): The maximum number of completion tokens.
        temperature (Optional[float]): The temperature for randomness.
        top_p (Optional[float]): The top-p sampling value.
        stream (Optional[bool]): Whether to stream the response.
        top_k (Optional[int]): The top-k sampling value.
        do_sample (Optional[bool]): Whether to sample.
        seed (Optional[int]): The seed for reproducibility.
    """

    messages: List[Message] = Field(...)
    model: str = Field(
        ...,
        description="Model identifier. Must match the configured VLM_MODEL_NAME on the running service.",
    )
    repetition_penalty: Optional[float] = Field(
        None, description="Optional repetition penalty override."
    )
    presence_penalty: Optional[float] = Field(
        None, description="Optional presence penalty override."
    )
    frequency_penalty: Optional[float] = Field(
        None, description="Optional frequency penalty override."
    )
    max_completion_tokens: Optional[int] = Field(
        settings.VLM_MAX_COMPLETION_TOKENS,
        description=(
            "Optional max completion token override. Defaults to VLM_MAX_COMPLETION_TOKENS "
            "when configured; otherwise model/runtime defaults apply."
        ),
    )
    temperature: Optional[float] = Field(
        None, description="Optional temperature override."
    )
    top_p: Optional[float] = Field(None, description="Optional top-p override.")
    stream: Optional[bool] = Field(
        False, description="When true, returns server-sent events."
    )
    top_k: Optional[int] = Field(None, description="Optional top-k override.")
    do_sample: Optional[bool] = Field(None, description="Optional sampling override.")
    seed: Optional[int] = Field(
        None,
        description="Optional seed override. Defaults to setup/runtime VLM_SEED (or SEED) value.",
    )


class ChatCompletionDelta(BaseModel):
    """
    Represents a delta in chat completion.

    Attributes:
        role (Optional[str]): The role of the message sender.
        content (Optional[str]): The content of the message.
    """

    role: Optional[str] = None
    content: Optional[str] = None


class ChatUsageStats(BaseModel):
    """
    Represents usage statistics for a chat.

    Attributes:
        prompt_tokens (Optional[int]): The number of prompt tokens.
        completion_tokens (Optional[int]): The number of completion tokens.
        total_tokens (Optional[int]): The total number of tokens.
        tps (Optional[float]): The tokens per second.
        time_to_first_token (Optional[float]): The time to the first token.
        latency (Optional[float]): The latency of the response.
        completion_tokens_details (Optional[dict]): Details of completion tokens.
    """

    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    tps: Optional[float] = None
    time_to_first_token: Optional[float] = None
    latency: Optional[float] = None
    completion_tokens_details: Optional[dict] = None


class TelemetryMetrics(BaseModel):
    """Detailed performance telemetry captured from ov_genai PerfMetrics."""

    prompt_tokens: Optional[int] = None  # Total tokens provided in the prompt for this request.
    completion_tokens: Optional[int] = None  # Tokens generated by the model.
    total_tokens: Optional[int] = None  # Sum of prompt and completion tokens.
    load_time_ms: Optional[float] = None  # Model load/initialization time in milliseconds.
    generate_time_ms: Optional[float] = None  # Mean time spent generating tokens (ms).
    generate_time_std_ms: Optional[float] = None  # Standard deviation for generation time (ms).
    tokenization_time_ms: Optional[float] = None  # Mean tokenizer encode duration (ms).
    tokenization_time_std_ms: Optional[float] = None  # Std-dev for tokenization duration (ms).
    detokenization_time_ms: Optional[float] = None  # Mean decode duration after generation (ms).
    detokenization_time_std_ms: Optional[float] = None  # Std-dev for detokenization duration (ms).
    embeddings_prep_time_ms: Optional[float] = None  # Mean time to build multimodal embeddings (ms).
    embeddings_prep_time_std_ms: Optional[float] = None  # Std-dev for embedding prep duration (ms).
    ttft_ms: Optional[float] = None  # Time-to-first-token mean in milliseconds.
    ttft_std_ms: Optional[float] = None  # Std-dev for TTFT (ms).
    tpot_ms: Optional[float] = None  # Time-per-output-token mean in milliseconds/token.
    tpot_std_ms: Optional[float] = None  # Std-dev for TPOT (ms/token).
    throughput_tps: Optional[float] = None  # Mean throughput in tokens per second.
    throughput_std_tps: Optional[float] = None  # Std-dev for throughput (tokens/s).


class TelemetryRequestMetadata(BaseModel):
    """Metadata describing the original request parameters (without sensitive payloads)."""

    message_count: int
    media: Dict[str, int]
    parameters: Dict[str, Any]


class TelemetryRecord(BaseModel):
    """Single telemetry entry exposed via /telemetry endpoint."""

    id: str
    timestamp: str
    status: str
    request: TelemetryRequestMetadata
    usage: Optional[ChatUsageStats] = None
    telemetry: Optional[TelemetryMetrics] = None
    error: Optional[str] = None


class TelemetryListResponse(BaseModel):
    """Envelope for telemetry history API."""

    count: int
    items: List[TelemetryRecord]


class ChatCompletionChoice(BaseModel):
    """
    Represents a choice in chat completion.

    Attributes:
        index (int): The index of the choice.
        message (ChatCompletionDelta): The message delta.
        finish_reason (Optional[str]): The reason for finishing.
    """

    index: int
    message: ChatCompletionDelta
    finish_reason: Optional[str] = None


class ChatCompletionResponse(BaseModel):
    """
    Represents a response for chat completion.

    Attributes:
        id (str): The ID of the response.
        object (str): The type of the object.
        created (int): The creation timestamp.
        model (str): The model used for the response.
        system_fingerprint (Optional[str]): The system fingerprint.
        choices (List[ChatCompletionChoice]): A list of completion choices.
        usage (Optional[ChatUsageStats]): The usage statistics.
        telemetry (Optional[TelemetryMetrics]): Detailed telemetry information.
    """

    id: str
    object: str = "chat.completion"
    created: int
    model: str
    system_fingerprint: Optional[str] = None
    choices: List[ChatCompletionChoice]
    usage: Optional[ChatUsageStats] = None
    telemetry: Optional[TelemetryMetrics] = None


class ChatCompletionStreamingChoice(BaseModel):
    """
    Represents a streaming choice in chat completion.

    Attributes:
        index (int): The index of the choice.
        delta (ChatCompletionDelta): The message delta.
        finish_reason (Optional[str]): The reason for finishing.
        usage (Optional[ChatUsageStats]): The usage statistics.
    """

    index: int
    delta: ChatCompletionDelta
    finish_reason: Optional[str] = None
    usage: Optional[ChatUsageStats] = None


class ChatCompletionStreamingResponse(BaseModel):
    """
    Represents a streaming response for chat completion.

    Attributes:
        id (str): The ID of the response.
        object (str): The type of the object.
        created (int): The creation timestamp.
        model (str): The model used for the response.
        system_fingerprint (str): The system fingerprint.
        choices (List[ChatCompletionStreamingChoice]): A list of streaming choices.
        telemetry (Optional[TelemetryMetrics]): Detailed telemetry information.
    """

    id: str
    object: str = "chat.completion.chunk"
    created: int
    model: str
    system_fingerprint: str
    choices: List[ChatCompletionStreamingChoice]
    telemetry: Optional[TelemetryMetrics] = None


class ModelData(BaseModel):
    """
    Represents data for a model.

    Attributes:
        id (str): The ID of the model.
        object (str): The type of the object.
        device (str): The runtime device used by the loaded model.
    """

    id: str
    object: str = "model"
    device: str


class ModelsResponse(BaseModel):
    """
    Represents a response containing a list of models.

    Attributes:
        object (str): The type of the object.
        data (List[ModelData]): A list of model data.
    """

    object: str = "list"
    data: List[ModelData]


class QueueStatusResponse(BaseModel):
    """Response payload for request queue status endpoint."""

    active_requests: int
    queued_requests: int


class DeviceListResponse(BaseModel):
    """Response payload listing available OpenVINO devices."""

    devices: List[str]


class HealthResponse(BaseModel):
    """Response payload for service health endpoint."""

    status: str


class ErrorResponse(BaseModel):
    """Generic error payload used by API endpoints."""

    error: str
