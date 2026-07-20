# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from enum import Enum
from typing import List, Optional, TypedDict, Dict, Any, Tuple
from pydantic import BaseModel, ConfigDict, Field, field_validator

# Parameter mapping for export_model.py command builder
# Format: {param_name: (flag_name, param_type)}
# param_type: 'string', 'int', 'bool'
# Used by OpenVINO plugin and other plugins for intelligent parameter handling
OPENVINO_EXPORT_PARAMS: Dict[str, Tuple[str, str]] = {
    "precision": ("--weight-format", "string"),
    "device": ("--target_device", "string"),
    "ov_cache_dir": ("--ov_cache_dir", "string"),
    "cache_size": ("--cache_size", "int"),
    "kv_cache_precision": ("--kv_cache_precision", "string"),
    "enable_prefix_caching": ("--enable_prefix_caching", "bool"),
    "dynamic_split_fuse": ("--disable_dynamic_split_fuse", "bool"),
    "max_num_batched_tokens": ("--max_num_batched_tokens", "int"),
    "max_num_seqs": ("--max_num_seqs", "int"),
    "draft_source_model": ("--draft_source_model", "string"),
    "max_prompt_len": ("--max_prompt_len", "int"),
    "prompt_lookup_decoding": ("--prompt_lookup_decoding", "bool"),
    "normalize": ("--skip_normalize", "bool"),
    "pooling": ("--pooling", "string"),
    "truncate": ("--truncate", "bool"),
    "num_streams": ("--num_streams", "int"),
    "max_doc_length": ("--max_doc_length", "int"),
    "overwrite_models": ("--overwrite_models", "bool"),
    "extra_quantization_params": ("--extra_quantization_params", "string"),
}

# Export type specific parameters mapping
# Defines which parameters are valid for each export type
EXPORT_TYPE_PARAMS: Dict[str, set] = {
    "text_generation": {
        "precision", "device", "ov_cache_dir", "cache_size", "kv_cache_precision",
        "enable_prefix_caching", "dynamic_split_fuse", "max_num_batched_tokens",
        "max_num_seqs", "draft_source_model", "draft_model_name", "max_prompt_len",
        "prompt_lookup_decoding", "reasoning_parser", "tool_parser",
        "enable_tool_guided_generation", "pipeline_type", "overwrite_models",
        "extra_quantization_params", "config_file_path", "model_repository_path",
        "model_name", "source_model", "target_device"
    },
    "embeddings_ov": {
        "precision", "device", "ov_cache_dir", "normalize", "pooling", "truncate",
        "num_streams", "overwrite_models", "extra_quantization_params",
        "config_file_path", "model_repository_path", "model_name", "source_model",
        "target_device"
    },
    "rerank_ov": {
        "precision", "device", "ov_cache_dir", "num_streams", "max_doc_length",
        "overwrite_models", "extra_quantization_params", "config_file_path",
        "model_repository_path", "model_name", "source_model", "target_device"
    },
}

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
    PIPELINE_ZOO_MODELS = "pipeline-zoo-models"
    OLLAMA = "ollama"
    OPENVINO = "openvino"
    GETI = "geti"
    HLS = "hls"
    REMOTE_URL = "remote-url"
    OMZ = "omz"

class ModelType(str, Enum):
    LLM = "llm"
    VLM = "vlm"
    EMBEDDINGS = "embeddings"
    RERANKER = "rerank"
    IMAGE_GENERATION = "image_generation"
    TEXT2SPEECH = "text2speech"
    SPEECH2TEXT = "speech2text"
    VISION = "vision"
    THREE_D_POSE = "3d-pose"
    RPPG = "rppg"
    AI_ECG = "ai-ecg"


class OpenVINOOptimizationConfig(BaseModel):
    """
    OpenVINO-specific optimization parameters aligned with export_model.py arguments.
    
    **Future-Proof Design:**
    - Uses Pydantic's extra="allow" to accept any new arguments without schema changes
    - Unknown parameters are passed transparently to export_model.py
    - New Optimum CLI/export_model.py arguments are automatically supported
    - No code changes needed when new arguments are added
    
    Reference: https://github.com/openvinotoolkit/model_server/tree/main/demos/common/export_models
    """
    model_config = ConfigDict(extra="allow")
    
    # Core parameters (common to all export tasks)
    precision: Optional[ModelPrecision] = Field(
        None,
        description="Weight format (int4, int8, fp16, fp32). Maps to export_model.py: --weight-format"
    )
    device: Optional[DeviceType] = Field(
        None,
        description="Target device (CPU, GPU, NPU, HETERO). Maps to export_model.py: --target_device"
    )
    
    # Optional common parameters
    ov_cache_dir: Optional[str] = Field(
        None,
        description="OpenVINO compilation cache directory. Maps to export_model.py: --ov_cache_dir"
    )
    overwrite_models: Optional[bool] = Field(
        None,
        description="Overwrite model if already exists. Maps to export_model.py: --overwrite_models"
    )
    extra_quantization_params: Optional[str] = Field(
        None,
        description="Advanced quantization parameters (e.g., '--sym --group-size -1 --ratio 1.0 --awq'). "
                    "Maps to export_model.py: --extra_quantization_params"
    )
    
    # Text generation specific (text_generation, VLM)
    cache_size: Optional[int] = Field(
        None,
        gt=0,
        description="KV cache size in GB. Maps to export_model.py: --cache_size"
    )
    pipeline_type: Optional[str] = Field(
        None,
        description="Pipeline type: LM, LM_CB, VLM, VLM_CB, AUTO. Maps to export_model.py: --pipeline_type"
    )
    kv_cache_precision: Optional[str] = Field(
        None,
        description="KV cache precision: u8 or empty for model default. Maps to export_model.py: --kv_cache_precision"
    )
    enable_prefix_caching: Optional[bool] = Field(
        None,
        description="Enable prefix caching for prompt tokens. Maps to export_model.py: --enable_prefix_caching"
    )
    dynamic_split_fuse: Optional[bool] = Field(
        None,
        description="Enable dynamic split fuse. Maps to export_model.py: --disable_dynamic_split_fuse (inverted logic)"
    )
    max_num_batched_tokens: Optional[int] = Field(
        None,
        description="Maximum tokens batched together. Maps to export_model.py: --max_num_batched_tokens"
    )
    max_num_seqs: Optional[int] = Field(
        None,
        description="Maximum sequences to process together. Maps to export_model.py: --max_num_seqs"
    )
    draft_source_model: Optional[str] = Field(
        None,
        description="Draft model for speculative decoding. Maps to export_model.py: --draft_source_model"
    )
    max_prompt_len: Optional[int] = Field(
        None,
        description="NPU specific: max tokens in prompt. Maps to export_model.py: --max_prompt_len"
    )
    prompt_lookup_decoding: Optional[bool] = Field(
        None,
        description="Use prompt lookup decoding. Maps to export_model.py: --prompt_lookup_decoding"
    )
    
    # Embeddings specific
    normalize: Optional[bool] = Field(
        None,
        description="Normalize embeddings. Maps to export_model.py: --skip_normalize (inverted logic)"
    )
    pooling: Optional[str] = Field(
        None,
        description="Embeddings pooling mode: CLS, LAST, MEAN. Maps to export_model.py: --pooling"
    )
    truncate: Optional[bool] = Field(
        None,
        description="Truncate prompts to fit model. Maps to export_model.py: --truncate"
    )
    
    # Multi-stream/performance optimization
    num_streams: Optional[int] = Field(
        None,
        gt=0,
        description="Parallel execution streams. Maps to export_model.py: --num_streams"
    )
    
    # Reranking specific
    max_doc_length: Optional[int] = Field(
        None,
        gt=0,
        description="Max document length in tokens. Maps to export_model.py: --max_doc_length"
    )


class Config(BaseModel):
    """
    General model configuration supporting multiple plugins.
    
    **Design:**
    - Common parameters (precision, device, cache_size) apply to all plugins
    - Plugin-specific configs nested within plugin-specific fields (openvino_config, etc.)
    - extra="allow" enables future parameters without schema changes
    - Backward compatible: supports both nested and flat parameter access
    
    **Usage Examples:**
    
    1. Backward compatible (flat structure):
       config={'precision': 'int8', 'device': 'CPU'}
    
    2. New nested structure (Optimum CLI aligned):
       config={
           'openvino_config': {
               'precision': 'int4',
               'device': 'CPU',
               'cache_size': 20,
               'kv_cache_precision': 'u8'
           }
       }
    
    3. Mixed (both common and plugin-specific):
       config={
           'precision': 'int8',  # common default
           'openvino_config': {
               'precision': 'int4',  # override for OpenVINO
               'cache_size': 20
           }
       }
    """
    model_config = ConfigDict(extra="allow")
    
    # Common parameters (plugin-agnostic)
    precision: Optional[ModelPrecision] = Field(
        None,
        description="Weight format for optimization (applies to compatible plugins)"
    )
    device: Optional[DeviceType] = Field(
        None,
        description="Target device (applies to compatible plugins)"
    )
    cache_size: Optional[int] = Field(
        None,
        gt=0,
        description="Cache size parameter (applies to relevant plugins)"
    )
    
    # Ultralytics INT8 quantization
    quantize: Optional[str] = None  # quantization dataset (for example: coco) used to enable INT8 export

    # Other plugin-specific common parameters
    model_group_id: Optional[str] = None
    export_type: Optional[str] = Field(None, description="For Geti: 'base' or 'optimized'")
    optimized_model_id: Optional[str] = None
    model_only: Optional[bool] = Field(None, description="For optimized Geti models: exclude code")
    
    # Plugin-specific configurations
    openvino_config: Optional[OpenVINOOptimizationConfig] = Field(
        None,
        description="OpenVINO/Optimum CLI specific parameters. Aligned with export_model.py arguments."
    )
    post_processing: Optional[Dict[str, Any]] = Field(
        None,
        description="Optional post-processing overrides for model-specific workflows"
    )



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
    override_credentials: Optional[Dict[str, str]] = Field(
        default=None,
        description=(
            "Optional per-request overrides for the target plugin's connection "
            "keys (for example HF_TOKEN, or GETI_HOST/GETI_TOKEN/GETI_WORKSPACE_ID). "
            "Values provided here take precedence over the service's environment "
            "variables for this request only and are never stored or logged. Use "
            "GET /plugins to discover the keys each plugin understands."
        ),
    )

    @field_validator("hub", mode="before")
    @classmethod
    def _normalize_hub(cls, v):
        # Accept hub names case-insensitively (e.g. 'Geti', 'GETI', 'HuggingFace').
        return v.lower() if isinstance(v, str) else v



class ModelDownloadRequest(BaseModel):
    models: List[ModelRequest]
    parallel_downloads: Optional[bool] = False


class ModelListRequest(BaseModel):
    """Request body for listing models from a hub."""
    model_config = ConfigDict(extra="allow")

    hub: str = Field(
        ...,
        description="The hub to list models from, e.g. 'huggingface', 'ultralytics', 'pipeline-zoo-models', or 'geti'.",
    )
    filters: Dict[str, Any] = Field(
        default_factory=dict,
        description="Hub-specific listing filters such as author, search, filter, tags, and gated.",
    )
    limit: int = Field(50, ge=1, le=200, description="Maximum models to return.")
    offset: int = Field(0, ge=0, description="Number of models to skip.")
    override_credentials: Optional[Dict[str, str]] = Field(
        default=None,
        description=(
            "Optional per-request overrides for the hub plugin's connection keys "
            "(for example HF_TOKEN, or GETI_HOST/GETI_TOKEN/GETI_WORKSPACE_ID). "
            "Values take precedence over environment variables for this request "
            "only and are never stored or logged."
        ),
    )


class ModelListItem(BaseModel):
    """A single model entry returned by a hub listing."""
    model_config = ConfigDict(extra="allow", protected_namespaces=())

    name: str = Field(
        ..., description="Model name to pass as 'name' in POST /api/v1/models/download."
    )
    owner: Optional[str] = Field(
        None, description="Owner / organization / project (whatever applies to the hub)."
    )
    precisions: Optional[List[str]] = Field(
        None,
        description="Available precisions / formats / variants.",
    )
    tags: Optional[List[str]] = Field(None, description="Tags associated with the model.")
    model_type: Optional[str] = Field(None, description="Model type/task, if available.")
    last_modified: Optional[str] = Field(
        None, description="Last update timestamp (ISO 8601), if available."
    )
    metadata: Optional[Dict[str, Any]] = Field(None, description="Extra hub-specific metadata.")


class ModelListResponse(BaseModel):
    """Response body for a hub model listing."""

    hub: str = Field(..., description="The hub the models were listed from.")
    items: List[ModelListItem] = Field(
        default_factory=list, description="Models discovered on the hub."
    )
    count: int = Field(..., description="Number of models returned in this response.")
    total: Optional[int] = Field(
        None, description="Total number of matching models, if the hub reports it."
    )
    limit: int = Field(..., description="Applied page size.")
    offset: int = Field(..., description="Applied offset.")
    has_more: Optional[bool] = Field(
        None, description="Whether another page is available, if known."
    )
    next_offset: Optional[int] = Field(
        None, description="Offset to request the next page, when another page is available."
    )