# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import logging
import os

from dotenv import load_dotenv
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings
from typing import Optional, Any

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
    Represents the application settings loaded from environment variables.
    """

    APP_NAME: str = "vlm-ov-serving"
    APP_DISPLAY_NAME: str = "vlm-ov-serving"
    APP_DESC: str = (
        "Fastapi server wrapping Openvino runtime to serve /chat/completion endpoint to consume text and image and serve inference with LLM/VLM models"
    )

    http_proxy: str = Field(default=None, json_schema_extra={"env": "http_proxy"})
    https_proxy: str = Field(default=None, json_schema_extra={"env": "https_proxy"})
    no_proxy_env: str = Field(default=None, json_schema_extra={"env": "no_proxy_env"})
    VLM_MODEL_NAME: str = Field(
        default=None,
        json_schema_extra={"env": "VLM_MODEL_NAME"},
    )
    VLM_COMPRESSION_WEIGHT_FORMAT: str = Field(
        default="int8", json_schema_extra={"env": "VLM_COMPRESSION_WEIGHT_FORMAT"}
    )
    VLM_DEVICE: str = Field(default="CPU", json_schema_extra={"env": "VLM_DEVICE"})
    SEED: int = Field(default=42, json_schema_extra={"env": "SEED"})
    VLM_MAX_COMPLETION_TOKENS: Optional[int] = Field(
        default=None,
        json_schema_extra={"env": "VLM_MAX_COMPLETION_TOKENS"},
    )

    @field_validator("VLM_MAX_COMPLETION_TOKENS", mode="before")
    @classmethod
    def validate_max_completion_tokens(cls, v: Any) -> Optional[int]:
        if v is None or v == "":
            return None
        try:
            return int(v)
        except (ValueError, TypeError):
            return None


class ErrorMessages:
    """
    Contains error messages used throughout the application.
    """

    CONVERT_MODEL_ERROR = "Error occurred in convert_model function"
    REQUEST_ERROR = "Request error occurred"
    LOAD_IMAGE_ERROR = "Error occurred while loading image"
    CHAT_COMPLETION_ERROR = "Error occurred in chat_completions endpoint"
    GET_MODELS_ERROR = "Error occurred in get_models endpoint"
    GPU_OOM_ERROR_MESSAGE = "error code: -5"
    UNSUPPORTED_VIDEO_INPUT = "Video input is not supported for this model."
    UNSUPPORTED_VIDEO_URL_INPUT = "Video URL input is not supported for this model."


class ModelNames:
    """
    Contains constants for model names.
    """

    QWEN = "qwen2"
    PHI = "phi-3.5-vision"


settings = Settings()
logger.debug(f"Settings: {settings.model_dump()}")
