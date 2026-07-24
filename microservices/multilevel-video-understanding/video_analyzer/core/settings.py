# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class PeltChunkingSettings(BaseSettings):
    model_config = SettingsConfigDict(env_nested_delimiter="__")
    initial_pen: float = 20
    max_iteration: int = 5
    max_frame_size: int = 512
    sample_fps: int = 1                     # In chunking algorithm, use a specific video sample fps, -1 use video's original fps
    min_avg_duration: float = 10            # Minimum average duration for chunks, unit: seconds
    max_avg_duration: float = 45            # Maximum average duration for chunks, unit: seconds
    min_chunk_duration: float = 1           # Minimum duration for each chunk: unit: seconds

class UniformChunkingSettings(BaseSettings):
    model_config = SettingsConfigDict(env_nested_delimiter="__")
    chunk_duration: float = 15

class Settings(BaseSettings):
    """
    Configuration settings used across whole application.
    
    These settings can be configured via environment variables on host or inside container.
    """
    model_config = SettingsConfigDict(env_nested_delimiter="__")
    
    DEBUG: bool = Field(False, env="DEBUG")                     # Debug flag to run API server with DEBUG logs. Used in Development only.

    # API configuration
    API_V1_PREFIX: str = Field("/v1", env="API_V1_PREFIX")      # API version prefix to be used with each endpoint route
    API_VER: str = Field("1.0.0", env="API_VER")
    APP_NAME: str = "Multi-level Video Understanding Service"
    API_DESCRIPTION: str = "API for intelligent video summarization based on Large Language Models and Vision Language Models."
    MAX_CONCURRENT_REQUESTS: int = Field(6, env="MAX_CONCURRENT_REQUESTS")
    REQUEST_TIMEOUT: int = Field(14400, env="REQUEST_TIMEOUT")        # Increase request timeout to support very long video processing (4 hours)

    # API Health check configuration
    API_STATUS: str = "healthy"
    API_STATUS_MSG: str = "Service is running smoothly." 

    # CORS configuration
    BACKEND_CORS_ORIGINS: List[str] = ["*"]

    # Video Chunking configs
    DEFAULT_VIDEO_CHUNKING_METHOD: str = "pelt"
    MAX_NUM_FRAMES_PER_CHUNK: int = Field(128, env="MAX_NUM_FRAMES_PER_CHUNK")
    PELT_CHUNK_CONFIG: PeltChunkingSettings = PeltChunkingSettings()
    UNIFORM_CHUNK_CONFIG: UniformChunkingSettings = UniformChunkingSettings()

    # Summarizer configs
    DEFAULT_SUMMARIZATION_METHOD: str = "USE_ALL_T-1"
    ## Default levels for multi-level description
    DEFAULT_LEVELS: int = 3                                 # Details: level 0: micro_chunks, level 2~(N-1): macro_chunks, level N: global
    DEFAULT_LEVEL_SIZES: List = [1, 6, -1]                  # chunk group size for each level, -1 means use single group
    ## Subtitle payload size limit (bytes) for inline text or decompressed b64gzip
    MAX_SUBTITLE_BYTES: int = Field(10 * 1024 * 1024, env="MAX_SUBTITLE_BYTES")  # default: 10MB
    
    ## Frame processing settings
    DEFAULT_PROCESS_FPS: float = Field(1, env="DEFAULT_PROCESS_FPS")
    VIDEO_FRAME_HEIGHT: int  = Field(270, env="VIDEO_FRAME_HEIGHT")             # Frame height for resizing
    VIDEO_FRAME_WIDTH: int = Field(480, env="VIDEO_FRAME_WIDTH")                # Frame width for resizing
    
    ## Model serving request settings
    MODEL_REQUEST_TIMEOUT: int = Field(300, env="MODEL_REQUEST_TIMEOUT")        # Seconds
    MODEL_MAX_RETRIES: int = Field(3, env="MODEL_MAX_RETRIES")
    
    # Inference parameters
    LLM_REMOVE_THINKING: bool = True
    VLM_REMOVE_THINKING: bool = True
    DEFAULT_TEMPERATURE: float = 0.2
    DEFAULT_MAX_TOKENS: int = Field(512, env="DEFAULT_MAX_TOKENS")
    ENABLE_THINKING: bool = Field(False, env="ENABLE_THINKING")
    JPEG_QUALITY: int = 90

    # Runtime prompt registry: persistent cache dir for dynamic video summary tasks.
    # Container bind-mount target; on the host this typically maps to
    # ~/.cache/.multilevel-video-understanding via docker compose.
    VIDEO_SUMMARY_CACHE: str = Field(
        default_factory=lambda: os.path.expanduser("~/.cache/.multilevel-video-understanding"),
        env="VIDEO_SUMMARY_CACHE",
    )

settings = Settings()