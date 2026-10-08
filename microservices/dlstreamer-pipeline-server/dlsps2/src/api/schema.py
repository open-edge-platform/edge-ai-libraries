# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
from typing import Any, List, Optional, Union

from pydantic import BaseModel, Field, field_validator


def _validate_cpu_cores(value: Optional[List[int]]) -> Optional[List[int]]:
    if not value:
        return None
    allowed = os.sched_getaffinity(0)
    invalid = sorted(set(value) - allowed)
    if invalid:
        raise ValueError(f"cpu_cores {invalid} not available; allowed cores: {sorted(allowed)}")
    return value


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------

class StartPipelineRequest(BaseModel):
    pipeline: str
    cpu_cores: Optional[List[int]] = None  # CPU core indices to pin this pipeline to (e.g., [0, 1, 2])

    _check_cpu_cores = field_validator("cpu_cores")(_validate_cpu_cores)


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
    cpu_cores: Optional[List[int]] = None  # CPU core indices to pin this pipeline to (e.g., [0, 1, 2])

    _check_cpu_cores = field_validator("cpu_cores")(_validate_cpu_cores)

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


class PipelineSummaryResponse(PipelineStatusResponse):
    """GET /pipelines/{instance_id} (legacy API parity): status fields PLUS the
    pipeline config/request data ("summary"). See
    PipelineStatusResponse for the status-only shape used by
    GET /pipelines/status and GET /pipelines/{instance_id}/status.
    """

    type: str = "GStreamer"
    launch_command: Optional[str] = None
    name: Optional[str] = None
    version: Optional[str] = None
    request: Optional[dict] = None
    cpu_cores: Optional[List[int]] = None


class PipelineDefinitionResponse(BaseModel):
    """One entry of GET /pipelines (legacy API parity: the loaded pipeline
    "catalog" from config.json, NOT running instances — see GET /pipelines/status
    for the list of instances).

    ``type``/``description`` match the literal values DLSPS 1.0 writes into each
    pipeline's generated ``pipeline.json`` (``server/manager.py``'s ``Pipeline.__init__``) —
    ``"GStreamer"`` (capitalized) and the fixed string "DL Streamer Pipeline Server
    pipeline", respectively. These are NOT derived from config.json in 1.0 either.
    """

    name: str
    version: str
    type: str = "GStreamer"
    description: Optional[str] = "DL Streamer Pipeline Server pipeline"
    parameters: Optional[dict] = None


class StartPipelineResponse(BaseModel):
    instance_id: str


class StopPipelineResponse(BaseModel):
    instance_id: str
