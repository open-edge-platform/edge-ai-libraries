# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from enum import Enum
from typing import List, Optional, TypedDict, Dict, Any
from pydantic import BaseModel, Field

class ModelPrecision(str, Enum):
    INT4 = "int4"
    INT8 = "int8"
    FP16 = "fp16"
    FP32 = "fp32"


class DeviceType(str, Enum):
    CPU = "CPU"
    GPU = "GPU"

class ModelHub(str, Enum):
    HUGGINGFACE = "huggingface"
    ULTRALYTICS = "ultralytics"
    OLLAMA = "ollama"
    OPENVINO = "openvino"

class ModelType(str, Enum):
    LLM = "llm"
    EMBEDDINGS = "embeddings"
    RERANKER = "rerank"
    VISION = "vision"

class Config(BaseModel):
    precision: ModelPrecision = ModelPrecision.INT8
    device: DeviceType = DeviceType.CPU
    cache_size: Optional[int] = Field(None, gt=0)


class ModelResult(TypedDict):
    status: str  # 'success' or 'error'
    model_name: str
    model_path: Optional[str]
    error: Optional[str]
    is_ovms: Optional[bool]


class DownloadResponse(BaseModel):
    message: str
    results: List[Dict[str, Any]]
    model_path: Optional[str] = None


class ModelRequest(BaseModel):
    name: str = Field(
        ...,
        min_length=1
    )
    hub: ModelHub
    type: Optional[ModelType] = None
    is_ovms: bool = False
    revision: Optional[str] = None
    config: Optional[Config] = None


class ModelDownloadRequest(BaseModel):
    models: List[ModelRequest]
    parallel_downloads: Optional[bool] = False