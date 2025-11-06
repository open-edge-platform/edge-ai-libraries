# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Common utilities and configuration management for multimodal embedding serving.

This module provides centralized configuration management, logging setup, and
common error message definitions. It uses Pydantic for robust configuration
validation and supports both environment variables and .env file configuration.

Key components:
- Settings class for application configuration
- Environment variable handling with defaults
- Proxy configuration management  
- Model parameter validation
- Centralized error message definitions
- Logging configuration

The module ensures consistent configuration across the application and provides
fallback mechanisms for different deployment scenarios.
"""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings

# Configure logger
logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Load environment variables from .env file if it exists
env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
if os.path.exists(env_path):
    load_dotenv(env_path)
    logger.info(f"Loaded environment variables from {env_path}")
else:
    logger.info(
        f".env file not found at {env_path}. Using environment variables from docker-compose."
    )


class Settings(BaseSettings):
    """
    Application configuration settings with environment variable support.

    This class defines all configuration parameters for the multimodal embedding
    serving application. It uses Pydantic for validation and supports loading
    from environment variables or .env files.

    The settings include model configuration, device selection, proxy settings,
    and video processing parameters. All settings have sensible defaults and
    can be overridden via environment variables.

    Attributes:
        APP_NAME: Internal application name identifier
        APP_DISPLAY_NAME: Human-readable application name
        APP_DESC: Application description for API documentation
        EMBEDDING_MODEL_NAME: Default model to load for embedding generation
        EMBEDDING_DEVICE: Target device for model inference (CPU/GPU)  
        EMBEDDING_USE_OV: Whether to use OpenVINO optimization
        EMBEDDING_OV_MODELS_DIR: Directory for OpenVINO model storage
        http_proxy: HTTP proxy server URL
        https_proxy: HTTPS proxy server URL
        no_proxy_env: Domains to bypass proxy
        DEFAULT_START_OFFSET_SEC: Default video start offset
        DEFAULT_CLIP_DURATION: Default video clip duration  
        DEFAULT_NUM_FRAMES: Default number of frames to extract
    """

    APP_NAME: str = "Multimodal-Embedding-Serving"
    APP_DISPLAY_NAME: str = "Multimodal Embedding Serving"
    APP_DESC: str = (
        "The Multimodal Embedding Serving is designed to generate embeddings for text, image URLs, base64 encoded images, video URLs, and base64 encoded videos. It supports multiple models including CLIP, MobileCLIP, SigLIP, and BLIP-2."
    )

    # Generic model configuration - supports all model types from config
    EMBEDDING_MODEL_NAME: str = Field(default="", env="EMBEDDING_MODEL_NAME")
    EMBEDDING_DEVICE: str = Field(default="CPU", env="EMBEDDING_DEVICE")
    EMBEDDING_USE_OV: bool = Field(default=False, env="EMBEDDING_USE_OV")  # Default to False for SDK usage
    EMBEDDING_OV_MODELS_DIR: str = Field(
        default=str(Path(__file__).parent.parent / "ov-models"),
        env="EMBEDDING_OV_MODELS_DIR",
    )

    http_proxy: str = Field(default="", env="http_proxy")
    https_proxy: str = Field(default="", env="https_proxy")
    no_proxy_env: str = Field(default="", env="no_proxy_env")

    DEFAULT_START_OFFSET_SEC: int = Field(default=0, env="DEFAULT_START_OFFSET_SEC")
    DEFAULT_CLIP_DURATION: int = Field(default=-1, env="DEFAULT_CLIP_DURATION")
    DEFAULT_NUM_FRAMES: int = Field(default=64, env="DEFAULT_NUM_FRAMES")

    @field_validator("EMBEDDING_USE_OV", mode="before")
    @classmethod
    def validate_embedding_use_ov(cls, v):
        """Handle empty string for EMBEDDING_USE_OV"""
        if v == "" or v is None:
            return False
        if isinstance(v, str):
            return v.lower() in ("true", "1", "yes", "on")
        return bool(v)

    @field_validator("DEFAULT_START_OFFSET_SEC", mode="before")
    @classmethod
    def validate_default_start_offset_sec(cls, v):
        """Handle empty string for DEFAULT_START_OFFSET_SEC"""
        if v == "" or v is None:
            return 0
        return int(v)

    @field_validator("DEFAULT_NUM_FRAMES", mode="before")
    @classmethod
    def validate_default_num_frames(cls, v):
        """Handle empty string for DEFAULT_NUM_FRAMES"""
        if v == "" or v is None:
            return 64
        return int(v)

    @field_validator("http_proxy", "https_proxy", mode="before")
    @classmethod
    def validate_proxy_url(cls, v):
        """
        Validate proxy URL format.
        
        Ensures that proxy URLs start with http:// or https:// if they are provided.
        Empty strings or None values are allowed.
        
        Args:
            v: The proxy URL value to validate
            
        Returns:
            The validated proxy URL
            
        Raises:
            ValueError: If the proxy URL format is invalid
        """
        if v and v != "" and not v.startswith(("http://", "https://")):
            raise ValueError(f"Invalid proxy URL: {v}")
        return v


# Create settings instance with error handling for SDK usage
try:
    settings = Settings()
    logger.debug(f"Settings: {settings.model_dump()}")
except Exception as e:
    logger.warning(f"Failed to load settings completely: {e}")
    # Fallback settings for SDK usage
    settings = Settings(_env_file=None)
    logger.info("Using fallback settings for SDK usage")


class ErrorMessages:
    """
    Centralized error message definitions for the application.
    
    This class provides a single location for all error messages used throughout
    the multimodal embedding serving application. Using constants for error
    messages ensures consistency and makes maintenance easier.
    
    The messages are organized by functional area and provide descriptive
    error descriptions for different failure scenarios including text processing,
    image handling, video processing, and file operations.
    """

    GET_TEXT_FEATURES_ERROR = "Error in get_text_features"
    EMBED_DOCUMENTS_ERROR = "Error in embed_documents"
    EMBED_QUERY_ERROR = "Error in generating text embeddings"
    GET_IMAGE_EMBEDDINGS_ERROR = "Error in generating image embeddings"
    GET_VIDEO_EMBEDDINGS_ERROR = "Error in generating video embeddings"
    GET_IMAGE_EMBEDDING_FROM_URL_ERROR = "Error in get_image_embedding_from_url"
    GET_IMAGE_EMBEDDING_FROM_BASE64_ERROR = "Error in get_image_embedding_from_base64"
    GET_VIDEO_EMBEDDING_FROM_URL_ERROR = "Error in get_video_embedding_from_url"
    GET_VIDEO_EMBEDDING_FROM_BASE64_ERROR = "Error in get_video_embedding_from_base64"
    CREATE_EMBEDDING_ERROR = "Error creating embedding"
    EMBED_VIDEO_ERROR = "Error in embed_video"
    LOAD_VIDEO_FOR_VCLIP_ERROR = "Error in load_video_for_vclip"
    DELETE_FILE_ERROR = "Error deleting file"
    DOWNLOAD_FILE_ERROR = "Error downloading file"
    DECODE_BASE64_VIDEO_ERROR = "Error decoding base64 video"
    DECODE_BASE64_IMAGE_ERROR = "Error decoding base64 image"
    EXTRACT_VIDEO_FRAMES_ERROR = "Error extracting video frames"
    GET_VIDEO_EMBEDDING_FROM_FILE_ERROR = "Error in get_video_embedding_from_file"
