# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from typing import Any, List, Optional, Union

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------

class StartPipelineRequest(BaseModel):
    pipeline: str


class SourceConfig(BaseModel):
    uri: Optional[str] = None
    type: Optional[str] = None

    model_config = {"extra": "allow"}


class MetadataDestinationConfig(BaseModel):
    type: str  # "file", "mqtt", "kafka", …
    path: Optional[str] = None    # file path
    topic: Optional[str] = None   # mqtt/kafka topic
    format: Optional[str] = None  # "json-lines", …
    publish_frame: bool = False   # include raw frame bytes in the message (mqtt)

    model_config = {"extra": "allow"}


class FrameDestinationConfig(BaseModel):
    type: str   # "rtsp", "webrtc", …
    path: Optional[str] = None  # stream identifier / RTSP mount-point
    peer_id: Optional[str] = Field(default=None, alias="peer-id")
    bitrate: int = 2048            # WebRTC H.264 encoder bitrate
    overlay: bool = True           # draw detections (gvawatermark) before streaming

    model_config = {"extra": "allow", "populate_by_name": True}


class DestinationConfig(BaseModel):
    metadata: Optional[MetadataDestinationConfig] = None
    # A single frame destination, or a list of them to fan the pipeline out
    # to multiple frame sinks at once (e.g. webrtc preview + s3_write
    # archive). See config.compat.apply_destination()/_replace_appsink_with_chains()
    # for how these are combined with each other and with a Python-element
    # metadata destination (mqtt/opcua/influx_write) via a shared `tee`.
    frame: Optional[Union[FrameDestinationConfig, List[FrameDestinationConfig]]] = None

    model_config = {"extra": "allow"}


class StartNamedPipelineRequest(BaseModel):
    """Request body for POST /pipelines/{name}/{version} (legacy API)."""

    source: Optional[SourceConfig] = None
    destination: Optional[DestinationConfig] = None
    parameters: Optional[dict[str, Any]] = None
    tags: Optional[dict[str, Any]] = None

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------

class PipelineStatusResponse(BaseModel):
    id: str
    state: str
    avg_fps: float
    frame_fps: float
    start_time: Optional[float]
    elapsed_time: Optional[float]
    message: str


class StartPipelineResponse(BaseModel):
    instance_id: str


class StopPipelineResponse(BaseModel):
    instance_id: str
