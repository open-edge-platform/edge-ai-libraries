from enum import Enum
from typing import List, Optional, TypedDict
from pydantic import BaseModel, Field

class ModelPrecision(str, Enum):
    INT8 = "int8"
    FP16 = "fp16"
    FP32 = "fp32"


class DeviceType(str, Enum):
    CPU = "CPU"
    GPU = "GPU"


class Config(BaseModel):
    precision: ModelPrecision = ModelPrecision.INT8
    device: DeviceType = DeviceType.CPU
    cache_size: Optional[int] = Field(None, gt=0)


class ModelResult(TypedDict):
    status: str
    model_name: str
    model_path: Optional[str]
    error: Optional[str]
    is_ovms: Optional[bool]


class ModelRequest(BaseModel):
    name: str
    hub: str
    type: Optional[str] = None
    is_ovms: bool = False
    revision: Optional[str] = None
    config: Optional[Config] = None


class ModelDownloadRequest(BaseModel):
    models: List[ModelRequest]
    parallel_downloads: Optional[bool] = False