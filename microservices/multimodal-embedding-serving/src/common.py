# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

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
    Configuration settings for the application.

    Attributes:
        APP_NAME (str): Name of the application.
        APP_DISPLAY_NAME (str): Display name of the application.
        APP_DESC (str): Description of the application.
        MODEL_NAME (str): Name of the pre-trained model.
        http_proxy (str): HTTP proxy setting.
        https_proxy (str): HTTPS proxy setting.
        no_proxy_env (str): No proxy setting.
    """

    APP_NAME: str = "VClip-Embedding"
    APP_DISPLAY_NAME: str = "VClip Embedding serving"
    APP_DESC: str = (
        "The VClip Embedding serving is designed to generate embeddings for text, image URLs, base64 encoded images, video URLs, and base64 encoded videos. It leverages the CLIP (Contrastive Language-Image Pretraining) model to create these embeddings."
    )

    MODEL_NAME: str = "openai/clip-vit-base-patch32"
    http_proxy: str = Field(default=None, env="http_proxy")
    https_proxy: str = Field(default=None, env="https_proxy")
    no_proxy_env: str = Field(default=None, env="no_proxy_env")

    DEFAULT_START_OFFSET_SEC: int = Field(default=0, env="DEFAULT_START_OFFSET_SEC")
    DEFAULT_CLIP_DURATION: int = Field(default=-1, env="DEFAULT_CLIP_DURATION")
    DEFAULT_NUM_FRAMES: int = Field(default=64, env="DEFAULT_NUM_FRAMES")
    EMBEDDING_DEVICE: str = Field(default="CPU", env="EMBEDDING_DEVICE")
    EMBEDDING_MODEL_PATH: str = Field(
        default=str(Path(__file__).parent.parent / "ov-models"),
        env="EMBEDDING_MODEL_PATH",
    )
    EMBEDDING_USE_OV: bool = Field(default=False, env="EMBEDDING_USE_OV")

    @field_validator("http_proxy", "https_proxy", mode="before")
    def validate_proxy_url(cls, v):
        if v and not v.startswith(("http://", "https://")):
            raise ValueError(f"Invalid proxy URL: {v}")
        return v


settings = Settings()
logger.debug(f"Settings: {settings.model_dump()}")


class ErrorMessages:
    """
    Error messages used throughout the application.
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
