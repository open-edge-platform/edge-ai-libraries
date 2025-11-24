# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from typing import List
from pydantic_settings import BaseSettings
from pydantic import Field


class PeltChunkingSettings(BaseSettings):
    initial_pen: float = 20
    max_iteration: int = 5
    max_frame_size: int = 512
    sample_fps: int = 1                     # In chunking algorithm, use a specific video sample fps, -1 use video's original fps
    min_avg_duration: float = 10            # Minimum average duration for chunks, unit: seconds
    max_avg_duration: float = 45            # Maximum average duration for chunks, unit: seconds
    min_chunk_duration: float = 1           # Minimum duration for each chunk: unit: seconds

class UniformChunkingSettings(BaseSettings):
    chunk_duration: float = 15

class Settings(BaseSettings):
    """
    Configuration settings used across whole application.
    
    These settings can be configured via environment variables on host or inside container.
    """
    DEBUG: bool = Field(False, env="DEBUG")             # Debug flag to run API server with DEBUG logs. Used in Development only.

    # API configuration
    API_V1_PREFIX: str = Field("/v1", env="API_V1_PREFIX")    # API version prefix to be used with each endpoint route
    API_VER: str = Field("1.0.0", env="API_VER")
    APP_NAME: str = "Multi-level Video Understanding Service"
    API_DESCRIPTION: str = "API for intelligent video summarization based on Large Language Models and Vision Language Models."
    MAX_CONCURRENT_REQUESTS: int = Field(6, env="MAX_CONCURRENT_REQUESTS")

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
    DEFAULT_LEVELS: int = 3                     # Details: level 0: micro_chunks, level 2~(N-1): macro_chunks, level N: global
    DEFAULT_LEVEL_SIZES: List = [1, 6, -1]      # chunk group size for each level, -1 means use single group
    
    ## Frame processing settings
    DEFAULT_PROCESS_FPS: float = Field(1, env="DEFAULT_PROCESS_FPS")
    VIDEO_FRAME_HEIGHT: int  = Field(270, env="VIDEO_FRAME_HEIGHT")             # Frame height for resizing
    VIDEO_FRAME_WIDTH: int = Field(480, env="VIDEO_FRAME_WIDTH")                # Frame width for resizing
    
    ## Request settings
    REQUEST_TIMEOUT: int = 300      # seconds
    MAX_RETRIES: int = 3
    
    # Inference parameters    
    LLM_REMOVE_THINKING: bool = True
    VLM_REMOVE_THINKING: bool = True
    DEFAULT_TEMPERATURE: float = 0.2
    JPEG_QUALITY: int = 90

settings = Settings()