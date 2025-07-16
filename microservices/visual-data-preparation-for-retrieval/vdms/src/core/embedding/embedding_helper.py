# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pathlib
from typing import List

from src.common import Strings, logger, settings
from src.core.db import VDMSClient
from src.core.util import read_config, store_video_metadata

from .embedding_api import QwenEmbeddings, vCLIPEmbeddings
from .embedding_model import Qwen3, vCLIP
from .embedding_service import vCLIPEmbeddingServiceWrapper


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

    # Setup embedding APIs
    if settings.MULTIMODAL_EMBEDDING_ENDPOINT:
        # Access the embedding API from an external REST microservice
        embedding_service = vCLIPEmbeddingServiceWrapper(
            api_url=settings.MULTIMODAL_EMBEDDING_ENDPOINT,
            model_name=settings.MULTIMODAL_EMBEDDING_MODEL_NAME,
            num_frames=settings.MULTIMODAL_EMBEDDING_NUM_FRAMES,
        )
        vector_dimensions = embedding_service.get_embedding_length()
    else:
        # Set local embedder for creating text or video embeddings based on provided parameters
        if video_metadata_path:
            embedding_service = vCLIPEmbeddings(model=vCLIP(config["embeddings"]))
            vector_dimensions = config["embeddings"]["clip_vector_dimensions"]
        elif text_metadata:
            embedding_service = QwenEmbeddings(model=Qwen3(config["embeddings"]))
            vector_dimensions = config["embeddings"]["qwen_vector_dimensions"]
        else:
            logger.error(
                "Error: No video metadata or text metadata provided for embedding generation."
            )
            raise Exception(Strings.embedding_error)

    # Initialize VDMS db client
    vdms = VDMSClient(
        host=settings.VDMS_VDB_HOST,
        port=settings.VDMS_VDB_PORT,
        collection_name=settings.DB_COLLECTION,
        embedder=embedding_service,
        video_metadata_path=video_metadata_path,
        text_metadata=text_metadata,
        embedding_dimensions=vector_dimensions,
    )

    return vdms


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
    metadata_file = store_video_metadata(
        bucket_name=bucket_name,
        video_id=video_id,
        video_filename=filename,
        temp_video_path=temp_video_path,
        chunk_duration=chunk_duration,
        clip_duration=clip_duration,
        metadata_temp_path=str(metadata_temp_path),
        tags=tags,
    )

    logger.debug(f"Metadata generated and saved to {metadata_file}")

    # Get vdms client
    vdms = _setup_vdms_client(video_metadata_path=metadata_file)
    if not vdms:
        raise Exception(Strings.vdms_client_error)

    # Store the video embeddings in VDMS vector DB
    ids = vdms.store_embeddings()
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
    ids = vdms.store_text_embedding(text)
    logger.debug(f"Embeddings for video summary created with ids: {ids}")

    return ids
