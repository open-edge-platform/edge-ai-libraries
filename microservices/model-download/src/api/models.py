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
    NPU = "NPU"

class ModelHub(str, Enum):
    HUGGINGFACE = "huggingface"
    ULTRALYTICS = "ultralytics"
    OLLAMA = "ollama"
    OPENVINO = "openvino"
    GETI = "geti"

class ModelType(str, Enum):
    LLM = "llm"
    VLM = "vlm"
    EMBEDDINGS = "embeddings"
    RERANKER = "rerank"
    VISION = "vision"

class Config(BaseModel):
    precision: Optional[ModelPrecision] = None
    device: Optional[DeviceType] = None
    cache_size: Optional[int] = Field(None, gt=0)
    model_group_id: Optional[str] = None
    export_type: Optional[str] = Field(None, description="For Geti: 'base' or 'optimized'")
    optimized_model_id: Optional[str] = None
    model_only: Optional[bool] = Field(None, description="For optimized Geti models: exclude code")
    class Config:
        extra = "allow"



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