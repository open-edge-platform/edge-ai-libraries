# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from typing import Dict, List, Optional, Union

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
    model: str = Field(..., json_schema_extra={"example": "llama-2-13b"})
    repetition_penalty: Optional[float] = Field(
        None, json_schema_extra={"example": 1.15}
    )
    presence_penalty: Optional[float] = Field(None, json_schema_extra={"example": 1.15})
    frequency_penalty: Optional[float] = Field(
        None, json_schema_extra={"example": 1.15}
    )
    max_completion_tokens: Optional[int] = Field(
        settings.VLM_MAX_COMPLETION_TOKENS, json_schema_extra={"example": 1000}
    )
    temperature: Optional[float] = Field(None, json_schema_extra={"example": 0.3})
    top_p: Optional[float] = Field(None, json_schema_extra={"example": 0.5})
    stream: Optional[bool] = Field(False, json_schema_extra={"example": True})
    top_k: Optional[int] = Field(None, json_schema_extra={"example": 40})
    do_sample: Optional[bool] = Field(None, json_schema_extra={"example": True})
    seed: Optional[int] = Field(
        None,
        json_schema_extra={"example": 42, "description": "Seed for reproducibility"},
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
    """

    id: str
    object: str = "chat.completion"
    created: int
    model: str
    system_fingerprint: Optional[str] = None
    choices: List[ChatCompletionChoice]
    usage: Optional[ChatUsageStats] = None


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
    usage: Optional[ChatUsageStats] = {}


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
    """

    id: str
    object: str = "chat.completion.chunk"
    created: int
    model: str
    system_fingerprint: str
    choices: List[ChatCompletionStreamingChoice]


class ModelData(BaseModel):
    """
    Represents data for a model.

    Attributes:
        id (str): The ID of the model.
        object (str): The type of the object.
        created (Optional[int]): The creation timestamp.
        owned_by (Optional[str]): The owner of the model.
    """

    id: str
    object: str = "model"
    created: Optional[int] = None
    owned_by: Optional[str] = None


class ModelsResponse(BaseModel):
    """
    Represents a response containing a list of models.

    Attributes:
        object (str): The type of the object.
        data (List[ModelData]): A list of model data.
    """

    object: str = "list"
    data: List[ModelData]
