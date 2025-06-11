# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import datetime
import pathlib
from typing import List

from src.common import settings, Strings, logger
from src.core.db import VDMSClient
from src.core.util import read_config, store_video_metadata
from .embedding_model import vCLIP
from .embedding_service import vCLIPEmbeddingServiceWrapper

async def generate_video_embedding(
    bucket_name: str,
    video_id: str,
    filename: str,
    temp_video_path: pathlib.Path,
    metadata_temp_path: pathlib.Path,
    chunk_duration: int = None,
    clip_duration: int = None,
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
    # Read configuration
    config = read_config(settings.CONFIG_FILEPATH, type="yaml")
    if config is None:
        raise Exception(Strings.config_error)

    vector_dimension = config["embeddings"]["vector_dimensions"]

    # Setup embedding model
    if settings.MULTIMODAL_EMBEDDING_ENDPOINT:
        embedding_model = vCLIPEmbeddingServiceWrapper(
            api_url=settings.MULTIMODAL_EMBEDDING_ENDPOINT,
            model_name=settings.MULTIMODAL_EMBEDDING_MODEL_NAME,
            num_frames=settings.MULTIMODAL_EMBEDDING_NUM_FRAMES,
        )
    else:
        # Get the vclip model
        embedding_model = vCLIP(config["embeddings"])

    # Generate metadata for the video
    metadata_file = store_video_metadata(
        bucket_name=bucket_name,
        video_id=video_id,
        video_filename=filename,
        temp_video_path=temp_video_path,
        chunk_duration=chunk_duration,
        clip_duration=clip_duration,
        metadata_temp_path=str(metadata_temp_path),
    )

    logger.info(f"Metadata generated and saved to {metadata_file}")

    # Initialize VDMS db client for video
    vdms = VDMSClient(
        host=settings.VDMS_VDB_HOST,
        port=settings.VDMS_VDB_PORT,
        collection_name=settings.DB_COLLECTION,
        model=embedding_model,
        video_metadata_path=metadata_file,
        embedding_dimensions=vector_dimension,
    )

    # Store the video embeddings in VDMS vector DB
    ids = vdms.store_embeddings()
    logger.info(f"Embeddings created for videos: {ids}")

    return ids


async def generate_text_embedding(
    bucket_name: str,
    video_id: str,
    text_summary: str,
    video_start_time: float,
    video_end_time: float,
) -> List[str]:
    """
    Generate embeddings for text with video reference.

    Args:
        bucket_name: The bucket name where the referenced video is stored
        video_id: The video ID (directory) containing the referenced video
        text_summary: The text content to embed
        video_start_time: Start timestamp in seconds of the video segment referenced by the text
        video_end_time: End timestamp in seconds of the video segment referenced by the text

    Returns:
        List of IDs of the created embeddings

    Raises:
        Exception: If there is an error in the embedding generation process
    """
    # Read configuration
    config = read_config(settings.CONFIG_FILEPATH, type="yaml")
    if config is None:
        raise Exception(Strings.config_error)

    vector_dimension = config["embeddings"]["vector_dimensions"]

    # Setup embedding model
    if settings.MULTIMODAL_EMBEDDING_ENDPOINT:
        embedding_model = vCLIPEmbeddingServiceWrapper(
            api_url=settings.MULTIMODAL_EMBEDDING_ENDPOINT,
            model_name=settings.MULTIMODAL_EMBEDDING_MODEL_NAME,
            num_frames=settings.MULTIMODAL_EMBEDDING_NUM_FRAMES,
        )
    else:
        # Get the vclip model
        embedding_model = vCLIP(config["embeddings"])

    # Create metadata for text
    text_metadata = {
        "bucket_name": bucket_name,
        "video_id": video_id,
        "video_start_time": video_start_time,
        "video_end_time": video_end_time,
        "content_type": "text",
        "timestamp": datetime.datetime.now().isoformat()
    }

    # Initialize VDMS db client for text
    # Pass None as video_metadata_path since we're not using it for text
    vdms = VDMSClient(
        host=settings.VDMS_VDB_HOST,
        port=settings.VDMS_VDB_PORT,
        collection_name=settings.DB_COLLECTION,
        model=embedding_model,
        video_metadata_path=None,  # Not used for text embeddings
        embedding_dimensions=vector_dimension,
    )

    # Store the text embedding in VDMS vector DB
    ids = vdms.store_text_embedding(text_summary, text_metadata)
    logger.info(f"Text embedding created with ids: {ids}")

    return ids
