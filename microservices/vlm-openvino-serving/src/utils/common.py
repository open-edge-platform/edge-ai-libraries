# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import logging
import os
import time
from datetime import datetime

from dotenv import load_dotenv
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings
from typing import Optional, Any, Dict

# Load environment variables from .env file if it exists
env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
if os.path.exists(env_path):
    load_dotenv(env_path)

# Temporary logger for validators (will be reconfigured after Settings instantiation)
_temp_logger = logging.getLogger(__name__)


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
    VLM_LOG_LEVEL: str = Field(
        default="info", json_schema_extra={"env": "VLM_LOG_LEVEL"}
    )
    VLM_MAX_COMPLETION_TOKENS: Optional[int] = Field(
        default=None,
        json_schema_extra={"env": "VLM_MAX_COMPLETION_TOKENS"},
    )
    OV_CONFIG: Optional[str] = Field(
        default=None,
        json_schema_extra={"env": "OV_CONFIG"},
    )

    @field_validator("VLM_LOG_LEVEL", mode="before")
    @classmethod
    def validate_log_level(cls, v: Any) -> str:
        if v is None or v == "":
            return "info"
        valid_levels = ["debug", "info", "warning", "error"]
        if v.lower() in valid_levels:
            return v.lower()
        _temp_logger.warning(f"Invalid VLM_LOG_LEVEL '{v}'. Using default 'info'.")
        return "info"

    @field_validator("VLM_MAX_COMPLETION_TOKENS", mode="before")
    @classmethod
    def validate_max_completion_tokens(cls, v: Any) -> Optional[int]:
        if v is None or v == "":
            return None
        try:
            return int(v)
        except (ValueError, TypeError):
            return None

    @field_validator("OV_CONFIG", mode="before")
    @classmethod
    def validate_ov_config(cls, v: Any) -> Optional[str]:
        if v is None or v == "":
            return None
        # Validate that it's a valid JSON string
        try:
            json.loads(v)
            return v
        except (json.JSONDecodeError, TypeError):
            _temp_logger.warning(
                f"Invalid OV_CONFIG JSON format: {v}. Using default configuration."
            )
            return None

    def get_ov_config_dict(self) -> Dict[str, Any]:
        """
        Parse OV_CONFIG JSON string into a dictionary.
        Returns default configuration if OV_CONFIG is not set or invalid.
        """
        if self.OV_CONFIG:
            try:
                return json.loads(self.OV_CONFIG)
            except json.JSONDecodeError:
                # Use the main logger if available, otherwise use temp logger
                try:
                    logger.warning(
                        "Failed to parse OV_CONFIG. Using default configuration."
                    )
                except NameError:
                    _temp_logger.warning(
                        "Failed to parse OV_CONFIG. Using default configuration."
                    )

        # Default OpenVINO configuration
        return {"PERFORMANCE_HINT": "LATENCY"}


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


# Configure logger with dynamic level based on VLM_LOG_LEVEL
def get_log_level():
    """Get the appropriate logging level based on VLM_LOG_LEVEL environment variable."""
    vlm_log_level = settings.VLM_LOG_LEVEL.lower()
    level_mapping = {
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warning": logging.WARNING,
        "error": logging.ERROR,
    }
    return level_mapping.get(vlm_log_level, logging.INFO)


class GunicornStyleFormatter(logging.Formatter):
    """Custom formatter to match Gunicorn's log format."""

    def format(self, record):
        # Get current time in UTC with timezone info
        utc_time = datetime.utcnow()
        timestamp = utc_time.strftime("[%Y-%m-%d %H:%M:%S +0000]")

        # Get process ID
        pid = os.getpid()

        # Format: [YYYY-MM-DD HH:MM:SS +0000] [PID] [LEVEL] Message
        formatted_message = (
            f"{timestamp} [{pid}] [{record.levelname}] {record.getMessage()}"
        )

        return formatted_message


# Configure logging with Gunicorn-style format
logging.basicConfig(
    level=get_log_level(),
    format="%(message)s",  # We'll handle formatting in our custom formatter
    handlers=[logging.StreamHandler()],
)

# Apply custom formatter to all handlers
for handler in logging.root.handlers:
    handler.setFormatter(GunicornStyleFormatter())

logger = logging.getLogger(__name__)

# Log environment file loading status
if os.path.exists(env_path):
    logger.info(f"Loaded environment variables from {env_path}")
else:
    logger.info(
        f".env file not found at {env_path}. Using environment variables from docker-compose."
    )

logger.debug(f"Settings: {settings.model_dump()}")
