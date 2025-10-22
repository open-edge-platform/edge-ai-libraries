# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pathlib
from typing import Any, List

from src.common import Strings, logger, settings
from src.core.db import VDMSClient
from src.core.util import read_config, store_video_metadata

from .embedding_api import QwenEmbeddings, vCLIPEmbeddings
from .embedding_model import Qwen3, vCLIP
from .embedding_service import EmbeddingServiceWrapper

# Cache to store a created vdms client and embedding model instances
_client_cache: dict[str, VDMSClient] = {}
_model_cache: dict[str, Any] = {}


def _get_client_key(
    video_metadata_path: pathlib.Path | None = None, endpoint: str | None = None
) -> str:
    """
    Generate a unique key for the VDMS client based on video metadata path or endpoint. Different keys are used
    to cache the VDMS Client Object based on use cases -
    a. When an external endpoint is used as an embedder service
    b. When a video metadata path is provided for local embedding generation
    c. When text metadata is provided for local embedding generation

    Args:
        video_metadata_path: Path to the video metadata file
        endpoint: Endpoint URL for the external embedding service

    Returns:
        A unique string key for the VDMS client
    """

    # Caching vdms client for each endpoint.
    # Different endpoints can have different configs (eg. embedding dimensions, model names, etc.)
    if endpoint:
        return f"vdms_client_{endpoint}"

    # Video and text usecase use different fixed keys.
    is_video = video_metadata_path is not None and video_metadata_path.exists()
    return "vdms_client_video" if is_video else "vdms_client_text"


def _setup_vdms_client(
    video_metadata_path: pathlib.Path | None = None, text_metadata: dict = {}
) -> VDMSClient:
    """
    Setup VDMS client with the provided video metadata path and text metadata.

    Args:
        video_metadata_path: Path to the video metadata file
        text_metadata: Metadata dictionary associated with the text

    Returns:
        An instance of VDMSClient
    """
    # Read configuration
    config = read_config(settings.CONFIG_FILEPATH, type="yaml")
    if config is None:
        raise Exception(Strings.config_error)

    client_key = _get_client_key(
        video_metadata_path=video_metadata_path, endpoint=settings.MULTIMODAL_EMBEDDING_ENDPOINT
    )

    if client_key in _client_cache:
        logger.debug(f"Using cached VDMS client for key: {client_key}")
        return _client_cache[client_key]

    # Setup embedding APIs
    if settings.MULTIMODAL_EMBEDDING_ENDPOINT:
        # Access the embedding API from an external REST microservice
        embedding_service = EmbeddingServiceWrapper(
            api_url=settings.MULTIMODAL_EMBEDDING_ENDPOINT,
            model_name=settings.MULTIMODAL_EMBEDDING_MODEL_NAME,
            num_frames=settings.MULTIMODAL_EMBEDDING_NUM_FRAMES,
        )
        vector_dimensions = embedding_service.get_embedding_length()
    else:
        # Set local embedder for creating text or video embeddings based on provided parameters
        model: Any = None
        if video_metadata_path:
            # Get the model from cache else update the cache with model instance
            model_key = config["embeddings"]["vclip_model_name"]
            if model_key in _model_cache:
                model = _model_cache[model_key]
                logger.debug(f"Using cached model for key: {model_key}")
            else:
                model = vCLIP(config["embeddings"])
                _model_cache[model_key] = model

            # Setup the embedding service corresponding to the model
            embedding_service = vCLIPEmbeddings(model=model)

        elif text_metadata:
            model_key = config["embeddings"]["qwen_model_name"]
            if model_key in _model_cache:
                model = _model_cache[model_key]
                logger.debug(f"Using cached model for key: {model_key}")
            else:
                model = Qwen3(config["embeddings"])
                _model_cache[model_key] = model

            # Setup the embedding service corresponding to the model
            embedding_service = QwenEmbeddings(model=model)
        else:
            logger.error(
                "Error: No video metadata or text metadata provided for embedding generation."
            )
            raise Exception(Strings.embedding_error)

        vector_dimensions = model.get_embedding_dimensions()

    # Initialize VDMS DB client
    client = VDMSClient(
        host=settings.VDMS_VDB_HOST,
        port=settings.VDMS_VDB_PORT,
        collection_name=settings.DB_COLLECTION,
        embedder=embedding_service,
        embedding_dimensions=vector_dimensions,
    )

    # Update the client cache with the created VDMS client
    _client_cache[client_key] = client
    logger.debug(f"VDMS client created and cached with key: {client_key}")
    return client


async def generate_video_embedding(
    bucket_name: str,
    video_id: str,
    filename: str,
    temp_video_path: pathlib.Path,
    metadata_temp_path: pathlib.Path,
    chunk_duration: int = None,
    clip_duration: int = None,
    tags: List[str] | str = [],
) -> List[str]:
    """
    Generate metadata and embeddings for a video file.

    Args:
        bucket_name: The bucket name where the video is stored or will be stored
        video_id: The video ID (directory) containing the video
        filename: The video filename
        temp_video_path: Temporary path where the video file is stored
        metadata_temp_path: Path where metadata will be stored
        chunk_duration: Interval of time in seconds for video chunking
        clip_duration: Length of clip in seconds for embedding selection

    Returns:
        List of IDs of the created embeddings

    Raises:
        Exception: If there is an error in the embedding generation process
    """

    # Generate metadata for the video
    metadata_path: pathlib.Path = store_video_metadata(
        bucket_name=bucket_name,
        video_id=video_id,
        video_filename=filename,
        temp_video_path=temp_video_path,
        chunk_duration=chunk_duration,
        clip_duration=clip_duration,
        metadata_temp_path=str(metadata_temp_path),
        tags=tags,
    )

    logger.debug(f"Metadata generated and saved to {metadata_path}")

    # Get vdms client
    vdms = _setup_vdms_client(video_metadata_path=metadata_path)
    if not vdms:
        raise Exception(Strings.vdms_client_error)

    # Store the video embeddings in VDMS vector DB
    ids = vdms.store_embeddings(video_metadata_path=metadata_path)
    logger.info(f"Embeddings created for videos: {ids}")

    return ids


async def generate_text_embedding(text: str, text_metadata: dict = {}) -> List[str]:
    """
    Generate embeddings for text with video reference.

    Args:
        text: The text content to embed
        text_metadata: Metadata associated with the text.

    Returns:
        List of IDs of the created embeddings

    Raises:
        Exception: If there is an error in the embedding generation process
    """
    logger.debug(f"Generating text embedding for: {text}")
    vdms = _setup_vdms_client(text_metadata=text_metadata)
    if not vdms:
        raise Exception(Strings.vdms_client_error)

    # Store the text embedding in VDMS vector DB
    ids = vdms.store_text_embedding(text, metadata=text_metadata)
    logger.debug(f"Embeddings for video summary created with ids: {ids}")

    return ids
